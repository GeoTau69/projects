"""
Billing — správa DB, ceny modelů, hash cache.

Extrahováno z token_tracker.py.
"""

import sqlite3
import hashlib
import json
from pathlib import Path

# ─── Konfigurace ─────────────────────────────────────────────────────────────

DB_DIR  = Path.home() / '.ai-agent'
DB_PATH = DB_DIR / 'tokens.db'

MODEL_PRICES: dict[str, dict] = {
    'claude-opus-4-6':   {'in': 15.00, 'out': 75.00},
    'claude-sonnet-4-6': {'in':  3.00, 'out': 15.00},
    'claude-haiku-4-5':  {'in':  0.80, 'out':  4.00},
    'opus':              {'in': 15.00, 'out': 75.00},
    'sonnet':            {'in':  3.00, 'out': 15.00},
    'haiku':             {'in':  0.80, 'out':  4.00},
}

MODEL_ALIASES = {
    'opus':   'claude-opus-4-6',
    'sonnet': 'claude-sonnet-4-6',
    'haiku':  'claude-haiku-4-5',
}


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
    for sql in [
        "ALTER TABLE token_log ADD COLUMN response_text TEXT",
        "ALTER TABLE token_log ADD COLUMN cache_hit INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    return conn


# ─── Pomocné funkce ───────────────────────────────────────────────────────────

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


def hash_prompt(messages: list[dict], system: str | None = None) -> str:
    """SHA-256 hash obsahu promptu (deterministický, bez metadat)."""
    content = json.dumps(
        {'system': system or '', 'messages': messages},
        sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(content.encode()).hexdigest()


# ─── Hash cache ───────────────────────────────────────────────────────────────

def cache_lookup(conn: sqlite3.Connection, prompt_hash: str,
                 operation: str, ttl: int) -> str | None:
    """
    Hledá platnou cached odpověď v DB.
    ttl: TTL v hodinách (0 = cache zakázána).
    """
    if ttl == 0:
        return None

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
