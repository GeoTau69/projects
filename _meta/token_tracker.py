#!/usr/bin/env python3
"""
Token Tracker — SQLite účetnictví Anthropic API volání.

Databáze:  ~/.ai-agent/tokens.db
CLI:       ~/bin/agent

Použití:
  agent log --project X --operation doc_update --model sonnet --in 5000 --out 1200
  agent billing --week
  agent billing --project backup-dashboard
  agent billing --today
  agent billing --top
  agent init
"""

import sqlite3
import argparse
import hashlib
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
    """Inicializuje ~/.ai-agent/tokens.db, vrátí připojení."""
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_log (
            id          INTEGER PRIMARY KEY,
            timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
            project     VARCHAR(50),
            operation   VARCHAR(50),
            model       VARCHAR(30),
            tokens_in   INTEGER,
            tokens_out  INTEGER,
            cost_usd    DECIMAL(10,6),
            prompt_hash VARCHAR(64),
            notes       TEXT
        )
    """)
    conn.commit()
    return conn


def normalize_model(model: str) -> str:
    """Převede alias na plný název modelu."""
    return MODEL_ALIASES.get(model.lower(), model)


def calc_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Vypočítá cenu v USD podle cen modelu."""
    prices = MODEL_PRICES.get(model) or MODEL_PRICES.get(model.lower())
    if not prices:
        # Zkusit alias z části názvu (claude-sonnet-4-6 → sonnet)
        for part in model.lower().split('-'):
            if part in MODEL_PRICES:
                prices = MODEL_PRICES[part]
                break
    if not prices:
        return 0.0
    return (tokens_in * prices['in'] + tokens_out * prices['out']) / 1_000_000


# ─── Příkaz: log ─────────────────────────────────────────────────────────────

def cmd_log(args: argparse.Namespace) -> None:
    """Přidá manuální záznam do DB."""
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

    # Sestavení WHERE podmínek
    conditions: list[str] = []
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

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

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

    t_in  = summary['t_in']  or 0
    t_out = summary['t_out'] or 0
    cost  = summary['cost']  or 0.0
    calls = summary['calls'] or 0

    print(f"\n  {D}Volání:{R} {calls:,}   "
          f"{D}Tokeny in:{R} {t_in:,}   "
          f"{D}Tokeny out:{R} {t_out:,}   "
          f"{bold(Y + f'Cena: ${cost:.4f}' + R)}\n")

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

    # ── agent init ────────────────────────────────────────────────────────────
    sub.add_parser('init', help='Inicializovat ~/.ai-agent/ a databázi')

    args = parser.parse_args()

    if args.cmd == 'log':
        cmd_log(args)
    elif args.cmd == 'billing':
        cmd_billing(args)
    elif args.cmd == 'init':
        conn = init_db()
        conn.close()
        print(f"{G}✓ Inicializováno:{R} {DB_PATH}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
