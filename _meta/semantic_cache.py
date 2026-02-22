"""
Sémantická cache — embedding-based lookup přes nomic-embed-text (Ollama).

Fallback na hash cache pokud Ollama nedostupná.
"""

import json
import sqlite3
import struct
import urllib.request
import urllib.error
from _meta.billing import DB_DIR, DB_PATH, init_db

import numpy as np

OLLAMA_EMBED_URL = 'http://localhost:11434/api/embeddings'
EMBED_MODEL      = 'nomic-embed-text'
EMBED_DIM        = 768


def _init_embed_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache_embeddings (
            id          INTEGER PRIMARY KEY,
            prompt_text TEXT,
            response    TEXT,
            embedding   BLOB,
            operation   VARCHAR(50),
            model       VARCHAR(30),
            created     DATETIME DEFAULT CURRENT_TIMESTAMP,
            hit_count   INTEGER DEFAULT 0
        )
    """)
    conn.commit()


def embed(text: str) -> np.ndarray | None:
    """Volá Ollama nomic-embed-text. Vrátí None pokud Ollama nedostupná."""
    payload = json.dumps({'model': EMBED_MODEL, 'prompt': text}).encode()
    req = urllib.request.Request(
        OLLAMA_EMBED_URL, data=payload,
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return np.array(data['embedding'], dtype=np.float32)
    except Exception:
        return None


def _vec_to_blob(v: np.ndarray) -> bytes:
    return struct.pack(f'{len(v)}f', *v)


def _blob_to_vec(b: bytes) -> np.ndarray:
    n = len(b) // 4
    return np.array(struct.unpack(f'{n}f', b), dtype=np.float32)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def lookup(prompt: str, operation: str, threshold: float = 0.90) -> str | None:
    """
    Hledá sémanticky podobnou cached odpověď.
    Vrátí response pokud cosine similarity >= threshold, jinak None.
    """
    vec = embed(prompt)
    if vec is None:
        return None

    conn = init_db()
    _init_embed_table(conn)

    rows = conn.execute("""
        SELECT id, embedding, response FROM cache_embeddings
        WHERE operation = ?
        ORDER BY created DESC
        LIMIT 500
    """, (operation,)).fetchall()

    best_id   = None
    best_score = 0.0
    best_resp  = None

    for row in rows:
        stored = _blob_to_vec(row['embedding'])
        score  = _cosine(vec, stored)
        if score > best_score:
            best_score = score
            best_id    = row['id']
            best_resp  = row['response']

    if best_score >= threshold and best_resp:
        conn.execute(
            "UPDATE cache_embeddings SET hit_count = hit_count + 1 WHERE id = ?",
            (best_id,)
        )
        conn.commit()
        conn.close()
        return best_resp

    conn.close()
    return None


def store(prompt: str, response: str, operation: str, model: str) -> None:
    """Uloží embedding + text do cache_embeddings."""
    vec = embed(prompt)
    if vec is None:
        return  # Ollama nedostupná, přeskočíme

    conn = init_db()
    _init_embed_table(conn)
    conn.execute("""
        INSERT INTO cache_embeddings (prompt_text, response, embedding, operation, model)
        VALUES (?, ?, ?, ?, ?)
    """, (prompt, response, _vec_to_blob(vec), operation, model))
    conn.commit()
    conn.close()
