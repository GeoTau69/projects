#!/usr/bin/env python3
"""
Token Tracker — SQLite účetnictví + prompt cache Anthropic API volání.

Databáze:  ~/.ai-agent/tokens.db
CLI:       ~/bin/agent

Použití (CLI):
  agent log --project X --operation doc_update --model sonnet --in 5000 --out 1200
  agent billing [--today|--week|--month] [--project X] [--model X] [--top]
  agent cache --stats
  agent cache --list
  agent cache --clear [--all]
  agent init

Použití (Python import):
  from _meta.token_tracker import call_api
  text = call_api('my-project', 'doc_update', 'sonnet', [
      {'role': 'user', 'content': 'Vygeneruj dokumentaci pro ...'}
  ])
  # Automaticky: cache lookup → API call → log + uložení do cache
"""

import sqlite3
import argparse
import hashlib
import json
import datetime
from pathlib import Path

# ─── Konfigurace ─────────────────────────────────────────────────────────────

DB_DIR  = Path.home() / '.ai-agent'
DB_PATH = DB_DIR / 'tokens.db'

# Ceny v USD za 1M tokenů — aktualizovat dle anthropic.com/pricing
MODEL_PRICES: dict[str, dict] = {
    'claude-opus-4-6':   {'in': 15.00, 'out': 75.00},
    'claude-sonnet-4-6': {'in':  3.00, 'out': 15.00},
    'claude-haiku-4-5':  {'in':  0.80, 'out':  4.00},
    # Aliasy (zkrácené názvy)
    'opus':              {'in': 15.00, 'out': 75.00},
    'sonnet':            {'in':  3.00, 'out': 15.00},
    'haiku':             {'in':  0.80, 'out':  4.00},
}

MODEL_ALIASES = {
    'opus':   'claude-opus-4-6',
    'sonnet': 'claude-sonnet-4-6',
    'haiku':  'claude-haiku-4-5',
}

# Cache TTL v hodinách per typ operace. 0 = cache zakázána.
CACHE_TTL: dict[str, int] = {
    'doc_update':   24,
    'boilerplate':  48,
    'info_sync':    12,
    'code_review':   0,   # žádná cache — vždy čerstvá analýza
    'architecture':  0,   # žádná cache
    'debug':         0,   # žádná cache
    '_default':     24,
}

# ─── ANSI barvy ───────────────────────────────────────────────────────────────

R = '\033[0m'
B = '\033[94m'
G = '\033[92m'
Y = '\033[93m'
C = '\033[96m'
D = '\033[90m'


def bold(s: str) -> str:
    return f'\033[1m{s}{R}'


# ─── DB ───────────────────────────────────────────────────────────────────────

def init_db() -> sqlite3.Connection:
    """Inicializuje ~/.ai-agent/tokens.db, provede migraci nových sloupců."""
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_log (
            id            INTEGER PRIMARY KEY,
            timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
            project       VARCHAR(50),
            operation     VARCHAR(50),
            model         VARCHAR(30),
            tokens_in     INTEGER,
            tokens_out    INTEGER,
            cost_usd      DECIMAL(10,6),
            prompt_hash   VARCHAR(64),
            notes         TEXT,
            response_text TEXT,
            cache_hit     INTEGER DEFAULT 0
        )
    """)
    # Migrace: přidej nové sloupce pokud DB existovala bez nich
    for sql in [
        "ALTER TABLE token_log ADD COLUMN response_text TEXT",
        "ALTER TABLE token_log ADD COLUMN cache_hit INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # sloupec již existuje
    conn.commit()
    return conn


def normalize_model(model: str) -> str:
    """Převede alias na plný název modelu."""
    return MODEL_ALIASES.get(model.lower(), model)


def calc_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Vypočítá cenu v USD podle cen modelu."""
    prices = MODEL_PRICES.get(model) or MODEL_PRICES.get(model.lower())
    if not prices:
        for part in model.lower().split('-'):
            if part in MODEL_PRICES:
                prices = MODEL_PRICES[part]
                break
    if not prices:
        return 0.0
    return (tokens_in * prices['in'] + tokens_out * prices['out']) / 1_000_000


# ─── Cache — knihovní funkce ──────────────────────────────────────────────────

def get_cache_ttl(operation: str) -> int:
    """Vrátí TTL v hodinách pro danou operaci. 0 = žádná cache."""
    return CACHE_TTL.get(operation, CACHE_TTL['_default'])


def hash_prompt(messages: list[dict], system: str | None = None) -> str:
    """SHA-256 hash obsahu promptu (deterministický, bez metadat)."""
    content = json.dumps(
        {'system': system or '', 'messages': messages},
        sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(content.encode()).hexdigest()


def cache_lookup(conn: sqlite3.Connection, prompt_hash: str,
                 operation: str) -> str | None:
    """
    Hledá platnou cached odpověď v DB.
    Vrátí response_text pokud nalezena a v rámci TTL, jinak None.
    """
    ttl = get_cache_ttl(operation)
    if ttl == 0:
        return None  # cache zakázána pro tuto operaci

    row = conn.execute("""
        SELECT response_text FROM token_log
        WHERE prompt_hash = ?
          AND operation   = ?
          AND (cache_hit = 0 OR cache_hit IS NULL)
          AND response_text IS NOT NULL
          AND response_text != ''
          AND timestamp >= DATETIME('now', ? || ' hours')
        ORDER BY timestamp DESC
        LIMIT 1
    """, (prompt_hash, operation, f'-{ttl}')).fetchone()

    return row['response_text'] if row else None


def cache_store(conn: sqlite3.Connection, project: str, operation: str,
                model: str, tokens_in: int, tokens_out: int, cost: float,
                prompt_hash: str, response_text: str, notes: str = '') -> None:
    """Uloží výsledek reálného API volání (cache_hit=0) včetně textu odpovědi."""
    conn.execute(
        """INSERT INTO token_log
           (project, operation, model, tokens_in, tokens_out, cost_usd,
            prompt_hash, notes, response_text, cache_hit)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (project, operation, model, tokens_in, tokens_out, cost,
         prompt_hash, notes, response_text)
    )
    conn.commit()


def log_cache_hit(conn: sqlite3.Connection, project: str, operation: str,
                  model: str, prompt_hash: str) -> None:
    """Zaznamená cache hit — 0 tokenů, $0, cache_hit=1."""
    conn.execute(
        """INSERT INTO token_log
           (project, operation, model, tokens_in, tokens_out, cost_usd,
            prompt_hash, cache_hit)
           VALUES (?, ?, ?, 0, 0, 0.0, ?, 1)""",
        (project, operation, model, prompt_hash)
    )
    conn.commit()


# ─── API wrapper ─────────────────────────────────────────────────────────────

def call_api(project: str, operation: str, model: str,
             messages: list[dict], system: str | None = None,
             max_tokens: int = 4096, notes: str = '') -> str:
    """
    Volá Anthropic API s automatickou cache a logováním.

    Postup:
      1. Spočítá SHA-256 hash promptu
      2. Zkontroluje cache (TTL dle operace z CACHE_TTL)
      3a. Cache hit  → zaloguje hit ($0), vrátí uloženou odpověď
      3b. Cache miss → zavolá API, zaloguje + uloží odpověď do cache

    Vyžaduje: pip install anthropic + ANTHROPIC_API_KEY v prostředí.
    """
    try:
        import anthropic as ant
    except ImportError:
        raise ImportError(
            "Chybí balíček 'anthropic'.\n"
            "  pip install anthropic\n"
            "  export ANTHROPIC_API_KEY=sk-ant-..."
        )

    full_model = normalize_model(model)
    phash      = hash_prompt(messages, system)
    conn       = init_db()

    # ── Cache lookup ──────────────────────────────────────────────────────────
    cached = cache_lookup(conn, phash, operation)
    if cached:
        log_cache_hit(conn, project, operation, full_model, phash)
        conn.close()
        return cached

    # ── Reálné API volání ─────────────────────────────────────────────────────
    kwargs: dict = dict(model=full_model, max_tokens=max_tokens, messages=messages)
    if system:
        kwargs['system'] = system

    client   = ant.Anthropic()
    response = client.messages.create(**kwargs)

    text       = response.content[0].text
    tokens_in  = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    cost       = calc_cost(full_model, tokens_in, tokens_out)

    cache_store(conn, project, operation, full_model,
                tokens_in, tokens_out, cost, phash, text, notes)
    conn.close()
    return text


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

    # Sestavení WHERE podmínek (vždy vyloučit cache_hit=1)
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

    # Stejné podmínky pro cache hity (bez cache_hit=0 filtru)
    hit_conds = [c for c in conditions if 'cache_hit' not in c]
    hit_conds.append("cache_hit = 1")
    hit_where = 'WHERE ' + ' AND '.join(hit_conds)

    # ── Top operace ───────────────────────────────────────────────────────────
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

    # ── Souhrn ────────────────────────────────────────────────────────────────
    summary = conn.execute(f"""
        SELECT COUNT(*)        AS calls,
               SUM(tokens_in)  AS t_in,
               SUM(tokens_out) AS t_out,
               SUM(cost_usd)   AS cost
        FROM token_log {where}
    """, params).fetchone()

    # ── Cache hity + odhad úspor ──────────────────────────────────────────────
    cache_stats = conn.execute(f"""
        SELECT COUNT(*) AS hits FROM token_log {hit_where}
    """, params).fetchone()

    # Odhad úspor: pro každý hit najít odpovídající reálné volání a sečíst jeho cenu
    saved = conn.execute(f"""
        SELECT COALESCE(SUM(orig.cost_usd), 0.0) AS saved_cost
        FROM token_log AS hit
        JOIN token_log AS orig
          ON orig.prompt_hash = hit.prompt_hash
         AND (orig.cache_hit = 0 OR orig.cache_hit IS NULL)
         AND orig.response_text IS NOT NULL
        {hit_where.replace('WHERE', 'WHERE hit.')}
    """, params).fetchone()

    # ── Po modelu ─────────────────────────────────────────────────────────────
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

    # ── Poslední záznamy ──────────────────────────────────────────────────────
    recent = conn.execute(f"""
        SELECT timestamp, project, operation, model,
               tokens_in, tokens_out, cost_usd
        FROM token_log {where}
        ORDER BY timestamp DESC
        LIMIT 15
    """, params).fetchall()

    conn.close()

    # ── Výpis ─────────────────────────────────────────────────────────────────
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

    # ── Statistiky ────────────────────────────────────────────────────────────
    if getattr(args, 'stats', False):
        total_cached = conn.execute("""
            SELECT COUNT(*) AS n FROM token_log
            WHERE (cache_hit = 0 OR cache_hit IS NULL)
              AND response_text IS NOT NULL AND response_text != ''
        """).fetchone()['n']

        # Platné (v rámci TTL) — approximace: záznamy mladší než nejkratší nenulové TTL
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

        # Ušetřené tokeny + cena (lookup přes prompt_hash)
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

    # ── Seznam cached odpovědí ────────────────────────────────────────────────
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

    # ── Smazání ───────────────────────────────────────────────────────────────
    if getattr(args, 'clear', False):
        if getattr(args, 'all', False):
            # Smazat text ze všech záznamů (zachovat logy)
            c = conn.execute("""
                UPDATE token_log SET response_text = NULL
                WHERE response_text IS NOT NULL
            """)
            conn.commit()
            print(f"{Y}✓ Cache vymazána:{R} {c.rowcount} záznamů")
        else:
            # Smazat pouze expirované záznamy (starší než nejdelší TTL)
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

    # Žádný flag → help
    print(f"Použití: agent cache --stats | --list | --clear [--all]")
    conn.close()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='agent',
        description='AI Dev Agent — správa a účetnictví workspace'
    )
    sub = parser.add_subparsers(dest='cmd')

    # ── agent log ─────────────────────────────────────────────────────────────
    p_log = sub.add_parser('log', help='Manuální záznam spotřeby tokenů')
    p_log.add_argument('--project',   required=True, help='Název projektu')
    p_log.add_argument('--operation', required=True, help='Typ operace (doc_update, code_review…)')
    p_log.add_argument('--model',     required=True, help='Model: sonnet/opus/haiku nebo plný název')
    p_log.add_argument('--in',        dest='tokens_in',  type=int, required=True, help='Vstupní tokeny')
    p_log.add_argument('--out',       dest='tokens_out', type=int, required=True, help='Výstupní tokeny')
    p_log.add_argument('--notes',     default='', help='Volitelná poznámka')

    # ── agent billing ─────────────────────────────────────────────────────────
    p_bill = sub.add_parser('billing', help='Přehled spotřeby a nákladů')
    p_bill.add_argument('--today',   action='store_true', help='Jen dnešní záznamy')
    p_bill.add_argument('--week',    action='store_true', help='Posledních 7 dní')
    p_bill.add_argument('--month',   action='store_true', help='Posledních 30 dní')
    p_bill.add_argument('--project', help='Filtrovat projekt')
    p_bill.add_argument('--model',   help='Filtrovat model (sonnet/opus/haiku)')
    p_bill.add_argument('--top',     action='store_true', help='Top operace dle ceny')

    # ── agent cache ───────────────────────────────────────────────────────────
    p_cache = sub.add_parser('cache', help='Správa prompt cache')
    p_cache.add_argument('--stats', action='store_true', help='Statistiky cache a TTL pravidla')
    p_cache.add_argument('--list',  action='store_true', help='Seznam cached odpovědí')
    p_cache.add_argument('--clear', action='store_true', help='Smazat expirovanou cache')
    p_cache.add_argument('--all',   action='store_true', help='S --clear: smazat veškerou cache')

    # ── agent init ────────────────────────────────────────────────────────────
    sub.add_parser('init', help='Inicializovat ~/.ai-agent/ a databázi')

    args = parser.parse_args()

    if args.cmd == 'log':
        cmd_log(args)
    elif args.cmd == 'billing':
        cmd_billing(args)
    elif args.cmd == 'cache':
        cmd_cache(args)
    elif args.cmd == 'init':
        conn = init_db()
        conn.close()
        print(f"{G}✓ Inicializováno:{R} {DB_PATH}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
