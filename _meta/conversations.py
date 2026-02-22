"""Conversations, Messages, Templates, Summaries — DB layer.

Používá stejný soubor ~/.ai-agent/tokens.db jako billing.
"""

import sqlite3
from _meta.billing import DB_DIR, DB_PATH


def init_conv_db() -> sqlite3.Connection:
    """Inicializuje tabulky konverzací, zpráv, šablon a souhrnů."""
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS templates (
            id         INTEGER PRIMARY KEY,
            name       VARCHAR(100) NOT NULL,
            content    TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY,
            name       VARCHAR(200),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closed_at  DATETIME,
            is_closed  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id               INTEGER PRIMARY KEY,
            conversation_id  INTEGER REFERENCES conversations(id),
            parent_id        INTEGER REFERENCES messages(id),
            role             VARCHAR(20) NOT NULL,
            content          TEXT,
            is_template      INTEGER DEFAULT 0,
            model            VARCHAR(50),
            backend          VARCHAR(30),
            tokens_in        INTEGER DEFAULT 0,
            tokens_out       INTEGER DEFAULT 0,
            cost_usd         DECIMAL(10,6) DEFAULT 0.0,
            response_time_ms INTEGER,
            timestamp        DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS conv_summaries (
            id               INTEGER PRIMARY KEY,
            conversation_id  INTEGER REFERENCES conversations(id),
            model            VARCHAR(50),
            content          TEXT,
            word_count       INTEGER DEFAULT 0,
            char_count       INTEGER DEFAULT 0,
            gen_time_ms      INTEGER,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    return conn


# ─── Templates ────────────────────────────────────────────────────────────────

def template_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, content, created_at FROM templates ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def template_get(conn: sqlite3.Connection, tid: int) -> dict | None:
    row = conn.execute("SELECT * FROM templates WHERE id = ?", (tid,)).fetchone()
    return dict(row) if row else None


def template_create(conn: sqlite3.Connection, name: str, content: str) -> int:
    cur = conn.execute(
        "INSERT INTO templates (name, content) VALUES (?, ?)", (name, content)
    )
    conn.commit()
    return cur.lastrowid


def template_update(conn: sqlite3.Connection, tid: int, name: str, content: str) -> None:
    conn.execute(
        "UPDATE templates SET name = ?, content = ? WHERE id = ?", (name, content, tid)
    )
    conn.commit()


def template_delete(conn: sqlite3.Connection, tid: int) -> None:
    conn.execute("DELETE FROM templates WHERE id = ?", (tid,))
    conn.commit()


# ─── Conversations ────────────────────────────────────────────────────────────

def conv_list(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute("""
        SELECT c.id, c.name, c.created_at, c.closed_at, c.is_closed,
               COUNT(m.id) AS msg_count
        FROM conversations c
        LEFT JOIN messages m ON m.conversation_id = c.id AND m.is_template = 0
        GROUP BY c.id
        ORDER BY c.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def conv_get(conn: sqlite3.Connection, cid: int) -> dict | None:
    row = conn.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()
    return dict(row) if row else None


def conv_create(conn: sqlite3.Connection, name: str = '') -> int:
    cur = conn.execute(
        "INSERT INTO conversations (name) VALUES (?)", (name or None,)
    )
    conn.commit()
    return cur.lastrowid


def conv_rename(conn: sqlite3.Connection, cid: int, name: str) -> None:
    conn.execute("UPDATE conversations SET name = ? WHERE id = ?", (name, cid))
    conn.commit()


def conv_close(conn: sqlite3.Connection, cid: int) -> None:
    conn.execute(
        "UPDATE conversations SET is_closed = 1, closed_at = CURRENT_TIMESTAMP "
        "WHERE id = ?", (cid,)
    )
    conn.commit()


# ─── Messages ─────────────────────────────────────────────────────────────────

def msg_list(conn: sqlite3.Connection, cid: int) -> list[dict]:
    rows = conn.execute("""
        SELECT * FROM messages
        WHERE conversation_id = ?
        ORDER BY timestamp ASC, id ASC
    """, (cid,)).fetchall()
    return [dict(r) for r in rows]


def msg_last_id(conn: sqlite3.Connection, cid: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
        (cid,)
    ).fetchone()
    return row['id'] if row else None


def msg_save_user(conn: sqlite3.Connection, cid: int, content: str,
                  parent_id: int | None = None,
                  is_template: bool = False) -> int:
    cur = conn.execute("""
        INSERT INTO messages (conversation_id, parent_id, role, content, is_template)
        VALUES (?, ?, 'user', ?, ?)
    """, (cid, parent_id, content, 1 if is_template else 0))
    conn.commit()
    return cur.lastrowid


def msg_save_assistant(conn: sqlite3.Connection, cid: int, parent_id: int,
                       content: str, model: str, backend: str,
                       tokens_in: int, tokens_out: int,
                       cost_usd: float, response_time_ms: int) -> int:
    cur = conn.execute("""
        INSERT INTO messages
            (conversation_id, parent_id, role, content, model, backend,
             tokens_in, tokens_out, cost_usd, response_time_ms)
        VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?)
    """, (cid, parent_id, content, model, backend,
          tokens_in, tokens_out, cost_usd, response_time_ms))
    conn.commit()
    return cur.lastrowid


def msg_get_unanswered(conn: sqlite3.Connection, cid: int) -> dict | None:
    """Vrátí poslední unanswered user message (bez navazující assistant odpovědi)."""
    row = conn.execute("""
        SELECT m.* FROM messages m
        WHERE m.conversation_id = ?
          AND m.role = 'user'
          AND m.is_template = 0
          AND NOT EXISTS (
              SELECT 1 FROM messages a
              WHERE a.parent_id = m.id AND a.role = 'assistant'
          )
        ORDER BY m.timestamp DESC
        LIMIT 1
    """, (cid,)).fetchone()
    return dict(row) if row else None


# ─── Summaries ────────────────────────────────────────────────────────────────

def summary_list(conn: sqlite3.Connection, cid: int) -> list[dict]:
    rows = conn.execute("""
        SELECT * FROM conv_summaries
        WHERE conversation_id = ?
        ORDER BY created_at ASC
    """, (cid,)).fetchall()
    return [dict(r) for r in rows]


def summary_save(conn: sqlite3.Connection, cid: int, model: str,
                 content: str, gen_time_ms: int) -> int:
    words = len(content.split())
    chars = len(content)
    cur = conn.execute("""
        INSERT INTO conv_summaries
            (conversation_id, model, content, word_count, char_count, gen_time_ms)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cid, model, content, words, chars, gen_time_ms))
    conn.commit()
    return cur.lastrowid
