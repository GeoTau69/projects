#!/usr/bin/env python3
"""
Token Tracker — SQLite účetnictví + prompt cache + model routing.

Databáze:  ~/.ai-agent/tokens.db
CLI:       ~/bin/agent

Použití (CLI):
  agent log --project X --operation doc_update --model sonnet --in 5000 --out 1200
  agent billing [--today|--week|--month] [--project X] [--model X] [--top]
  agent cache --stats | --list | --clear [--all]
  agent route --show
  agent route --test doc_update
  agent ask "prompt" --operation code_review --project X [--model auto]
  agent init

Použití (Python import):
  from _meta.token_tracker import call_api
  text = call_api('my-project', 'doc_update', 'auto', [
      {'role': 'user', 'content': 'Vygeneruj dokumentaci pro ...'}
  ])
"""

import sqlite3
import argparse
import hashlib
import json
import datetime
from pathlib import Path

# ─── Importy z nových modulů ─────────────────────────────────────────────────

from _meta.billing import (
    DB_DIR, DB_PATH,
    MODEL_PRICES, MODEL_ALIASES,
    init_db, normalize_model, calc_cost, hash_prompt,
    cache_lookup, cache_store, log_cache_hit,
)
from _meta.router import (
    ROUTING_RULES, CACHE_TTL, LOCAL_MODEL, OLLAMA_CHAT_URL,
    resolve_model, get_cache_ttl,
)

# ─── ANSI barvy ───────────────────────────────────────────────────────────────

R = '\033[0m'
B = '\033[94m'
G = '\033[92m'
Y = '\033[93m'
C = '\033[96m'
D = '\033[90m'


def bold(s: str) -> str:
    return f'\033[1m{s}{R}'


# ─── Zpětně kompatibilní call_api wrapper ────────────────────────────────────

def call_api(project: str, operation: str, model: str,
             messages: list[dict], system: str | None = None,
             max_tokens: int = 4096, notes: str = '') -> str:
    """
    Volá API s automatickým routingem, cache a logováním.
    Zachováno pro zpětnou kompatibilitu — deleguje na Orchestrator.
    """
    from _meta.orchestrator import Orchestrator
    from _meta.plugins.claude import ClaudeBackend
    from _meta.plugins.ollama import OllamaBackend

    orch = Orchestrator()
    orch.register(ClaudeBackend())
    orch.register(OllamaBackend())
    resp = orch.request(messages, operation, project, model, system, max_tokens, notes)
    return resp.text


# ─── Příkaz: log ─────────────────────────────────────────────────────────────

def cmd_log(args: argparse.Namespace) -> None:
    """Přidá manuální záznam do DB (bez cache_hit, bez response_text)."""
    model = normalize_model(args.model)
    cost  = calc_cost(model, args.tokens_in, args.tokens_out)

    hashsrc = f"{args.project}:{args.operation}:{args.tokens_in}:{datetime.datetime.now().isoformat()}"
    phash   = hashlib.sha256(hashsrc.encode()).hexdigest()[:16]

    conn = init_db()
    conn.execute(
        """INSERT INTO token_log
           (project, operation, model, tokens_in, tokens_out, cost_usd, prompt_hash, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (args.project, args.operation, model,
         args.tokens_in, args.tokens_out, cost, phash,
         args.notes or '')
    )
    conn.commit()
    conn.close()

    print(f"{G}✓ Zaznamenáno{R}  {C}{args.project}{R} / {args.operation}  "
          f"{D}in:{R} {args.tokens_in:,}  {D}out:{R} {args.tokens_out:,}  "
          f"{Y}${cost:.4f}{R}")


# ─── Příkaz: billing ─────────────────────────────────────────────────────────

def cmd_billing(args: argparse.Namespace) -> None:
    conn = init_db()

    conditions: list[str] = ["(cache_hit = 0 OR cache_hit IS NULL)"]
    params: list = []

    if getattr(args, 'today', False):
        conditions.append("DATE(timestamp) = DATE('now')")
    elif getattr(args, 'week', False):
        conditions.append("timestamp >= DATETIME('now', '-7 days')")
    elif getattr(args, 'month', False):
        conditions.append("timestamp >= DATETIME('now', '-30 days')")

    if getattr(args, 'project', None):
        conditions.append("project = ?")
        params.append(args.project)

    if getattr(args, 'model', None):
        model = normalize_model(args.model)
        conditions.append("(model = ? OR model LIKE ?)")
        params.extend([model, f'%{args.model}%'])

    where = 'WHERE ' + ' AND '.join(conditions)

    hit_conds = [c for c in conditions if 'cache_hit' not in c]
    hit_conds.append("cache_hit = 1")
    hit_where = 'WHERE ' + ' AND '.join(hit_conds)

    if getattr(args, 'top', False):
        rows = conn.execute(f"""
            SELECT operation, project,
                   COUNT(*)        AS calls,
                   SUM(tokens_in)  AS t_in,
                   SUM(tokens_out) AS t_out,
                   SUM(cost_usd)   AS cost
            FROM token_log {where}
            GROUP BY operation, project
            ORDER BY cost DESC
            LIMIT 20
        """, params).fetchall()

        print(f"\n{bold('TOP OPERACE')}")
        print(f"{D}{'Operace':<28} {'Projekt':<22} {'Volání':>6} {'In':>11} {'Out':>8} {'Cena':>10}{R}")
        print(D + '─' * 92 + R)
        for r in rows:
            print(f"  {C}{r['operation']:<26}{R}  {r['project']:<22}"
                  f"{r['calls']:>6}  {r['t_in'] or 0:>10,}  {r['t_out'] or 0:>7,}  "
                  f"{Y}${r['cost'] or 0:>8.4f}{R}")
        conn.close()
        return

    summary = conn.execute(f"""
        SELECT COUNT(*)        AS calls,
               SUM(tokens_in)  AS t_in,
               SUM(tokens_out) AS t_out,
               SUM(cost_usd)   AS cost
        FROM token_log {where}
    """, params).fetchone()

    cache_stats = conn.execute(f"""
        SELECT COUNT(*) AS hits FROM token_log {hit_where}
    """, params).fetchone()

    saved = conn.execute(f"""
        SELECT COALESCE(SUM(cost_usd), 0.0) AS saved_cost
        FROM token_log
        WHERE prompt_hash IN (SELECT prompt_hash FROM token_log {hit_where})
          AND (cache_hit = 0 OR cache_hit IS NULL)
          AND response_text IS NOT NULL
    """, params).fetchone()

    by_model = conn.execute(f"""
        SELECT model,
               COUNT(*)        AS calls,
               SUM(tokens_in)  AS t_in,
               SUM(tokens_out) AS t_out,
               SUM(cost_usd)   AS cost
        FROM token_log {where}
        GROUP BY model
        ORDER BY cost DESC
    """, params).fetchall()

    recent = conn.execute(f"""
        SELECT timestamp, project, operation, model,
               tokens_in, tokens_out, cost_usd
        FROM token_log {where}
        ORDER BY timestamp DESC
        LIMIT 15
    """, params).fetchall()

    conn.close()

    period = ''
    if getattr(args, 'today', False):   period = '(dnes)'
    elif getattr(args, 'week', False):  period = '(posledních 7 dní)'
    elif getattr(args, 'month', False): period = '(posledních 30 dní)'

    print(f"\n{bold('TOKENOVÉ ÚČETNICTVÍ')} {D}{period}{R}")
    if getattr(args, 'project', None):
        print(f"  Projekt: {C}{args.project}{R}")
    if getattr(args, 'model', None):
        print(f"  Model:   {C}{args.model}{R}")

    t_in   = summary['t_in']  or 0
    t_out  = summary['t_out'] or 0
    cost   = summary['cost']  or 0.0
    calls  = summary['calls'] or 0
    hits   = cache_stats['hits'] or 0
    saved_cost = (saved['saved_cost'] or 0.0) if saved else 0.0

    print(f"\n  {D}Volání:{R} {calls:,}   "
          f"{D}Tokeny in:{R} {t_in:,}   "
          f"{D}Tokeny out:{R} {t_out:,}   "
          f"{bold(Y + f'Cena: ${cost:.4f}' + R)}")
    if hits:
        print(f"  {G}Cache hity:{R} {hits}   "
              f"{G}Ušetřeno: ~${saved_cost:.4f}{R}")
    print()

    if by_model:
        print(f"{bold('PODLE MODELU')}")
        print(f"{D}  {'Model':<26} {'Volání':>6} {'In':>12} {'Out':>10} {'Cena':>12}{R}")
        print(D + '  ' + '─' * 70 + R)
        for r in by_model:
            print(f"  {C}{r['model']:<26}{R} {r['calls']:>6}  "
                  f"{r['t_in'] or 0:>11,}  {r['t_out'] or 0:>9,}  "
                  f"{Y}${r['cost'] or 0:>10.4f}{R}")
        print()

    if recent:
        print(f"{bold('POSLEDNÍ ZÁZNAMY')}")
        print(f"{D}  {'Čas':<17} {'Projekt':<20} {'Operace':<22} {'Model':<20} {'In':>7} {'Out':>6} {'Cena':>9}{R}")
        print(D + '  ' + '─' * 107 + R)
        for r in recent:
            ts = r['timestamp'][:16].replace('T', ' ')
            print(f"  {D}{ts}{R}  {C}{r['project']:<18}{R}  "
                  f"{r['operation']:<22}  {r['model']:<20}  "
                  f"{r['tokens_in'] or 0:>6,}  {r['tokens_out'] or 0:>5,}  "
                  f"{Y}${r['cost_usd'] or 0:>7.4f}{R}")
        print()


# ─── Příkaz: cache ────────────────────────────────────────────────────────────

def cmd_cache(args: argparse.Namespace) -> None:
    conn = init_db()

    if getattr(args, 'stats', False):
        total_cached = conn.execute("""
            SELECT COUNT(*) AS n FROM token_log
            WHERE (cache_hit = 0 OR cache_hit IS NULL)
              AND response_text IS NOT NULL AND response_text != ''
        """).fetchone()['n']

        min_ttl = min(v for v in CACHE_TTL.values() if v > 0)
        valid_cached = conn.execute(f"""
            SELECT COUNT(*) AS n FROM token_log
            WHERE (cache_hit = 0 OR cache_hit IS NULL)
              AND response_text IS NOT NULL AND response_text != ''
              AND timestamp >= DATETIME('now', '-{min_ttl} hours')
        """).fetchone()['n']

        total_hits = conn.execute("""
            SELECT COUNT(*) AS n FROM token_log WHERE cache_hit = 1
        """).fetchone()['n']

        total_real = conn.execute("""
            SELECT COUNT(*) AS n FROM token_log
            WHERE (cache_hit = 0 OR cache_hit IS NULL)
        """).fetchone()['n']

        saved = conn.execute("""
            SELECT COALESCE(SUM(orig.tokens_in),  0) AS t_in,
                   COALESCE(SUM(orig.tokens_out), 0) AS t_out,
                   COALESCE(SUM(orig.cost_usd),   0) AS cost
            FROM token_log AS hit
            JOIN token_log AS orig
              ON orig.prompt_hash = hit.prompt_hash
             AND (orig.cache_hit = 0 OR orig.cache_hit IS NULL)
             AND orig.response_text IS NOT NULL
            WHERE hit.cache_hit = 1
        """).fetchone()

        hit_rate = (total_hits / (total_real + total_hits) * 100) if (total_real + total_hits) > 0 else 0.0

        print(f"\n{bold('CACHE STATISTIKY')}")
        print(f"  {D}Uložené odpovědi:{R}  {total_cached} celkem  {D}(z toho ~{valid_cached} v rámci TTL){R}")
        print(f"  {D}Cache hity:{R}        {total_hits}")
        print(f"  {D}Hit rate:{R}          {hit_rate:.1f}%")
        if saved and saved['cost']:
            saved_str = f"~${saved['cost']:.4f}"
            print(f"  {G}Ušetřeno:{R}          ~{saved['t_in']:,} in + ~{saved['t_out']:,} out tokenů  "
                  f"{bold(G + saved_str + R)}")
        print(f"\n{bold('TTL PRAVIDLA')}")
        for op, ttl in CACHE_TTL.items():
            key = f"  {C}{op:<18}{R}"
            val = f"{Y}{ttl}h{R}" if ttl > 0 else f"{D}vypnuto{R}"
            print(f"{key}  {val}")
        print()
        conn.close()
        return

    if getattr(args, 'list', False):
        rows = conn.execute("""
            SELECT timestamp, project, operation, model,
                   tokens_in, tokens_out, cost_usd,
                   prompt_hash,
                   LENGTH(response_text) AS resp_len
            FROM token_log
            WHERE (cache_hit = 0 OR cache_hit IS NULL)
              AND response_text IS NOT NULL AND response_text != ''
            ORDER BY timestamp DESC
            LIMIT 30
        """).fetchall()

        print(f"\n{bold('CACHED ODPOVĚDI')}")
        if not rows:
            print(f"  {D}Žádné záznamy.{R}\n")
            conn.close()
            return
        print(f"{D}  {'Čas':<17} {'Projekt':<18} {'Operace':<20} {'Hash':<10} {'Velikost':>8} {'Cena':>9}{R}")
        print(D + '  ' + '─' * 90 + R)
        for r in rows:
            ts  = r['timestamp'][:16].replace('T', ' ')
            h   = r['prompt_hash'][:8] if r['prompt_hash'] else '????????'
            kb  = (r['resp_len'] or 0) / 1024
            print(f"  {D}{ts}{R}  {C}{r['project']:<16}{R}  "
                  f"{r['operation']:<20}  {D}{h}{R}  "
                  f"{kb:>6.1f} kB  {Y}${r['cost_usd'] or 0:>7.4f}{R}")
        print()
        conn.close()
        return

    if getattr(args, 'clear', False):
        if getattr(args, 'all', False):
            c = conn.execute("""
                UPDATE token_log SET response_text = NULL
                WHERE response_text IS NOT NULL
            """)
            conn.commit()
            print(f"{Y}✓ Cache vymazána:{R} {c.rowcount} záznamů")
        else:
            max_ttl = max(v for v in CACHE_TTL.values() if v > 0)
            c = conn.execute(f"""
                UPDATE token_log SET response_text = NULL
                WHERE response_text IS NOT NULL
                  AND timestamp < DATETIME('now', '-{max_ttl} hours')
            """)
            conn.commit()
            print(f"{Y}✓ Expirovaná cache vymazána:{R} {c.rowcount} záznamů "
                  f"{D}(starší než {max_ttl}h){R}")
        conn.close()
        return

    print(f"Použití: agent cache --stats | --list | --clear [--all]")
    conn.close()


# ─── Příkaz: route ───────────────────────────────────────────────────────────

def cmd_route(args: argparse.Namespace) -> None:
    if getattr(args, 'test', None):
        op    = args.test
        dest  = resolve_model(op, 'auto')
        label = f"{G}Ollama / {dest.removeprefix('ollama/')}{R}" \
                if dest.startswith('ollama/') \
                else f"{C}Claude API / {dest}{R}"
        source = ROUTING_RULES.get(op)
        note   = f"{D}(z pravidla '{op}'){R}" if source else f"{D}(výchozí pravidlo){R}"
        print(f"\n  {D}Operace:{R} {Y}{op}{R}  →  {label}  {note}\n")
        return

    print(f"\n{bold('ROUTING TABULKA')}")
    print(f"  {D}Lokální model: {R}{C}{LOCAL_MODEL}{R}")
    print()
    print(f"{D}  {'Operace':<20} {'Cíl':<12} {'Model'}{R}")
    print(D + '  ' + '─' * 58 + R)
    for op, dest in ROUTING_RULES.items():
        if op == '_default':
            continue
        resolved = resolve_model(op, 'auto')
        if resolved.startswith('ollama/'):
            dest_label  = f"{G}local{R}"
            model_label = f"{G}{resolved.removeprefix('ollama/')}{R}"
        else:
            dest_label  = f"{C}cloud{R}"
            model_label = f"{C}{resolved}{R}"
        print(f"  {Y}{op:<20}{R} {dest_label:<20}  {model_label}")

    default_resolved = resolve_model('unknown_op', 'auto')
    if default_resolved.startswith('ollama/'):
        dl = f"{G}local{R}"; ml = f"{G}{default_resolved.removeprefix('ollama/')}{R}"
    else:
        dl = f"{C}cloud{R}"; ml = f"{C}{default_resolved}{R}"
    print(f"  {D}{'_default (ostatní)':<20}{R} {dl:<20}  {ml}")
    print()

    conn = init_db()
    local_calls = conn.execute("""
        SELECT COUNT(*) AS n, COALESCE(SUM(tokens_in+tokens_out),0) AS tokens
        FROM token_log WHERE model LIKE 'ollama/%'
          AND (cache_hit = 0 OR cache_hit IS NULL)
    """).fetchone()
    cloud_calls = conn.execute("""
        SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd),0) AS cost
        FROM token_log WHERE model NOT LIKE 'ollama/%'
          AND (cache_hit = 0 OR cache_hit IS NULL)
    """).fetchone()
    conn.close()

    if local_calls['n'] or cloud_calls['n']:
        print(f"{bold('HISTORICKÁ VYUŽITÍ')}")
        print(f"  {G}Ollama (lokální):{R} {local_calls['n']:,} volání  "
              f"{D}{local_calls['tokens']:,} tokenů  $0.00{R}")
        print(f"  {C}Claude API:{R}      {cloud_calls['n']:,} volání  "
              f"{Y}${cloud_calls['cost']:.4f}{R}")
        print()


# ─── Spinner ─────────────────────────────────────────────────────────────────

import threading
import sys
import time
import itertools


class Spinner:
    """Blokující spinner — zobrazuje se dokud neběží API volání."""
    _FRAMES = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'

    def __init__(self, label: str) -> None:
        self._label   = label
        self._stop    = threading.Event()
        self._thread  = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        for frame in itertools.cycle(self._FRAMES):
            if self._stop.is_set():
                break
            sys.stderr.write(f'\r{C}{frame}{R} {self._label}')
            sys.stderr.flush()
            time.sleep(0.08)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        sys.stderr.write('\r' + ' ' * (len(self._label) + 4) + '\r')
        sys.stderr.flush()


# ─── Příkaz: ask ─────────────────────────────────────────────────────────────

def cmd_ask(args: argparse.Namespace) -> None:
    """Zavolá AI model přes Orchestrator a vypíše odpověď."""
    from _meta.orchestrator import Orchestrator
    from _meta.plugins.claude import ClaudeBackend
    from _meta.plugins.ollama import OllamaBackend
    from _meta.router import resolve_model

    orch = Orchestrator()
    orch.register(ClaudeBackend())
    orch.register(OllamaBackend())

    messages  = [{'role': 'user', 'content': args.prompt}]
    dest      = resolve_model(args.operation, args.model)
    label     = f"Zpracovávám... [{dest.removeprefix('ollama/')}]"

    with Spinner(label):
        resp = orch.request(
            messages=messages,
            operation=args.operation,
            project=args.project,
            model=args.model,
            system=getattr(args, 'system', None),
            max_tokens=getattr(args, 'max_tokens', 4096),
        )

    print(resp.text)
    print(f"\n{D}[{resp.model}  in:{resp.tokens_in:,}  out:{resp.tokens_out:,}  ${resp.cost:.4f}]{R}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='agent',
        description='AI Dev Agent — správa a účetnictví workspace'
    )
    sub = parser.add_subparsers(dest='cmd')

    # ── agent log ─────────────────────────────────────────────────────────────
    p_log = sub.add_parser('log', help='Manuální záznam spotřeby tokenů')
    p_log.add_argument('--project',   required=True)
    p_log.add_argument('--operation', required=True)
    p_log.add_argument('--model',     required=True)
    p_log.add_argument('--in',        dest='tokens_in',  type=int, required=True)
    p_log.add_argument('--out',       dest='tokens_out', type=int, required=True)
    p_log.add_argument('--notes',     default='')

    # ── agent billing ─────────────────────────────────────────────────────────
    p_bill = sub.add_parser('billing', help='Přehled spotřeby a nákladů')
    p_bill.add_argument('--today',   action='store_true')
    p_bill.add_argument('--week',    action='store_true')
    p_bill.add_argument('--month',   action='store_true')
    p_bill.add_argument('--project', help='Filtrovat projekt')
    p_bill.add_argument('--model',   help='Filtrovat model')
    p_bill.add_argument('--top',     action='store_true')

    # ── agent cache ───────────────────────────────────────────────────────────
    p_cache = sub.add_parser('cache', help='Správa prompt cache')
    p_cache.add_argument('--stats', action='store_true')
    p_cache.add_argument('--list',  action='store_true')
    p_cache.add_argument('--clear', action='store_true')
    p_cache.add_argument('--all',   action='store_true')

    # ── agent route ───────────────────────────────────────────────────────────
    p_route = sub.add_parser('route', help='Zobrazit nebo otestovat model routing')
    p_route.add_argument('--show', action='store_true')
    p_route.add_argument('--test', metavar='OPERATION')

    # ── agent ask ─────────────────────────────────────────────────────────────
    p_ask = sub.add_parser('ask', help='Zavolat AI model s promptem')
    p_ask.add_argument('prompt',      help='Prompt text')
    p_ask.add_argument('--operation', default='_default', help='Typ operace (code_review, doc_update…)')
    p_ask.add_argument('--project',   default='cli',      help='Název projektu pro billing')
    p_ask.add_argument('--model',     default='auto',     help='Model: auto/local/sonnet/opus/haiku')
    p_ask.add_argument('--system',    default=None,       help='System prompt')
    p_ask.add_argument('--max-tokens', dest='max_tokens', type=int, default=4096)

    # ── agent init ────────────────────────────────────────────────────────────
    sub.add_parser('init', help='Inicializovat ~/.ai-agent/ a databázi')

    args = parser.parse_args()

    if args.cmd == 'log':
        cmd_log(args)
    elif args.cmd == 'billing':
        cmd_billing(args)
    elif args.cmd == 'cache':
        cmd_cache(args)
    elif args.cmd == 'route':
        cmd_route(args)
    elif args.cmd == 'ask':
        cmd_ask(args)
    elif args.cmd == 'init':
        conn = init_db()
        conn.close()
        print(f"{G}✓ Inicializováno:{R} {DB_PATH}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
