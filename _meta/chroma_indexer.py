#!/usr/bin/env python3
"""
Sémantický vyhledávač kódu — SQLite + numpy + Ollama embeddingy.

chromadb není kompatibilní s Python 3.14 (pydantic v1 crash) → vlastní implementace:
  - Úložiště:   ~/.ai-agent/code_index.db  (SQLite + numpy BLOB)
  - Embeddingy: nomic-embed-text via Ollama HTTP API
  - Vyhledávání: kosínusová podobnost přes numpy (fast enough pro osobní workspace)

CLI (přes ~/bin/agent):
  agent index                      # indexuje vše
  agent index --project dashboard  # jen jeden projekt
  agent index --diff               # jen soubory změněné v git
  agent index --force              # ignoruj mtime cache, přeindexuj vše
  agent search "retry logika"
  agent search "retry logika" --project backup-dashboard
  agent search "záloha borg"  --top 10
  agent search "co projekt dělá" --scope docs   # hledá v CLAUDE.md souborech
"""

import sqlite3
import argparse
import json
import struct
import subprocess
import datetime
import urllib.request
import urllib.error
from pathlib import Path

import numpy as np

# ─── Konfigurace ─────────────────────────────────────────────────────────────

PROJECTS_ROOT  = Path.home() / 'projects'
DB_DIR         = Path.home() / '.ai-agent'
INDEX_DB_PATH  = DB_DIR / 'code_index.db'
OLLAMA_URL     = 'http://localhost:11434/api/embeddings'
EMBED_MODEL    = 'nomic-embed-text'
EMBED_DIM      = 768
CHUNK_LINES    = 60    # velikost chunků pro nepy soubory
CHUNK_OVERLAP  = 10   # překryv mezi chunky

# Přípony k indexování
CODE_EXTENSIONS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.sql', '.sh'}
DOCS_EXTENSIONS = {'.md'}

# Projekty a adresáře k přeskočení
SKIP_DIRS = {'node_modules', '.git', '__pycache__', '.venv', 'venv',
             'output', '.build-state.json', 'tmp', 'verze'}
SKIP_FILES = {'*.backup-*'}

# ─── ANSI barvy ───────────────────────────────────────────────────────────────

R = '\033[0m'
G = '\033[92m'
Y = '\033[93m'
C = '\033[96m'
D = '\033[90m'
M = '\033[95m'


def bold(s: str) -> str:
    return f'\033[1m{s}{R}'


# ─── DB ───────────────────────────────────────────────────────────────────────

def init_index_db() -> sqlite3.Connection:
    """Inicializuje ~/.ai-agent/code_index.db."""
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(INDEX_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS code_chunks (
            id          INTEGER PRIMARY KEY,
            filepath    TEXT NOT NULL,
            project     TEXT NOT NULL,
            language    TEXT,
            chunk_start INTEGER,
            chunk_end   INTEGER,
            chunk_type  TEXT,
            name        TEXT,
            content     TEXT NOT NULL,
            embedding   BLOB NOT NULL,
            indexed_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            file_mtime  REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project  ON code_chunks(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_filepath ON code_chunks(filepath)")
    conn.commit()
    return conn


def store_embedding(arr: np.ndarray) -> bytes:
    """Serializuje numpy float32 array do BLOB."""
    return arr.astype(np.float32).tobytes()


def load_embedding(blob: bytes) -> np.ndarray:
    """Deserializuje BLOB na numpy float32 array."""
    return np.frombuffer(blob, dtype=np.float32)


# ─── Embeddingy ───────────────────────────────────────────────────────────────

def get_embedding(text: str) -> np.ndarray:
    """Získá embedding přes Ollama nomic-embed-text HTTP API."""
    payload = json.dumps({'model': EMBED_MODEL, 'prompt': text}).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        return np.array(data['embedding'], dtype=np.float32)
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ollama nedostupná ({OLLAMA_URL}): {e}\n"
            "  Spusť: ollama serve"
        )


def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Kosínusová podobnost query vektoru vůči každému řádku matice."""
    q = query / (np.linalg.norm(query) + 1e-10)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    return (matrix / norms) @ q


# ─── Chunking ─────────────────────────────────────────────────────────────────

def chunk_python(lines: list[str], filepath: str) -> list[dict]:
    """
    Rozdělí Python soubor na chunky po funkcích a třídách.
    Každý chunk = jedna top-level nebo class-level def/class.
    """
    chunks = []
    i = 0
    n = len(lines)

    def flush_chunk(start, end, ctype, name):
        content = ''.join(lines[start:end]).strip()
        if len(content) > 20:
            chunks.append({
                'start': start + 1, 'end': end,
                'type': ctype, 'name': name,
                'content': content[:3000]  # max délka pro embedding
            })

    chunk_start = 0
    chunk_type  = 'module'
    chunk_name  = Path(filepath).stem
    in_block    = False
    block_indent = 0

    for i, line in enumerate(lines):
        stripped  = line.lstrip()
        indent    = len(line) - len(stripped)

        is_def   = stripped.startswith('def ')   and indent <= 4
        is_class = stripped.startswith('class ') and indent == 0

        if is_def or is_class:
            if in_block and i > chunk_start:
                flush_chunk(chunk_start, i, chunk_type, chunk_name)
            chunk_start  = i
            chunk_type   = 'class' if is_class else 'function'
            chunk_name   = stripped.split('(')[0].split(':')[0].split()[-1]
            in_block     = True
            block_indent = indent

    # Poslední chunk
    if chunk_start < n:
        flush_chunk(chunk_start, n, chunk_type, chunk_name)

    # Fallback: celý soubor jako jeden chunk pokud nic nebylo detekováno
    if not chunks:
        content = ''.join(lines).strip()
        if content:
            chunks.append({
                'start': 1, 'end': n,
                'type': 'module', 'name': Path(filepath).stem,
                'content': content[:3000]
            })

    return chunks


def chunk_generic(lines: list[str]) -> list[dict]:
    """Sliding window pro nepy soubory: CHUNK_LINES řádků s CHUNK_OVERLAP překryvem."""
    chunks = []
    n = len(lines)
    step = CHUNK_LINES - CHUNK_OVERLAP

    for start in range(0, n, step):
        end     = min(start + CHUNK_LINES, n)
        content = ''.join(lines[start:end]).strip()
        if len(content) > 20:
            chunks.append({
                'start': start + 1, 'end': end,
                'type': 'block', 'name': '',
                'content': content[:3000]
            })
        if end == n:
            break

    return chunks


def chunk_markdown(lines: list[str]) -> list[dict]:
    """Rozdělí Markdown soubor na sekce dle nadpisů (# / ##)."""
    chunks = []
    section_start = 0
    section_name  = 'úvod'

    for i, line in enumerate(lines):
        if line.startswith('#') and i > section_start:
            content = ''.join(lines[section_start:i]).strip()
            if len(content) > 20:
                chunks.append({
                    'start': section_start + 1, 'end': i,
                    'type': 'section', 'name': section_name,
                    'content': content[:3000]
                })
            section_start = i
            section_name  = line.lstrip('#').strip()

    # Poslední sekce
    content = ''.join(lines[section_start:]).strip()
    if len(content) > 20:
        chunks.append({
            'start': section_start + 1, 'end': len(lines),
            'type': 'section', 'name': section_name,
            'content': content[:3000]
        })

    return chunks


def get_chunks(filepath: Path) -> list[dict]:
    """Vrátí seznam chunků pro soubor dle přípony."""
    try:
        lines = filepath.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
    except Exception:
        return []

    ext = filepath.suffix.lower()
    if ext == '.py':
        return chunk_python(lines, str(filepath))
    elif ext == '.md':
        return chunk_markdown(lines)
    else:
        return chunk_generic(lines)


# ─── Indexování ───────────────────────────────────────────────────────────────

def get_project_files(project: str | None = None,
                      extensions: set | None = None,
                      diff_only: bool = False) -> list[Path]:
    """Vrátí seznam souborů k indexování."""
    if extensions is None:
        extensions = CODE_EXTENSIONS | DOCS_EXTENSIONS

    if diff_only:
        # Jen soubory změněné v git
        result = subprocess.run(
            ['git', '-C', str(PROJECTS_ROOT), 'diff', 'HEAD', '--name-only'],
            capture_output=True, text=True
        )
        paths = [PROJECTS_ROOT / p.strip() for p in result.stdout.splitlines() if p.strip()]
        return [p for p in paths if p.exists() and p.suffix.lower() in extensions]

    search_root = PROJECTS_ROOT / project if project else PROJECTS_ROOT
    files = []

    for p in search_root.rglob('*'):
        if not p.is_file():
            continue
        if any(skip in p.parts for skip in SKIP_DIRS):
            continue
        if p.suffix.lower() not in extensions:
            continue
        # Přeskočit backup soubory
        if '.backup-' in p.name:
            continue
        files.append(p)

    return sorted(files)


def index_file(conn: sqlite3.Connection, filepath: Path, force: bool = False) -> int:
    """
    Indexuje jeden soubor. Vrátí počet nových chunků.
    Přeskočí soubor pokud mtime nezměněno (pokud force=False).
    """
    rel_path  = str(filepath.relative_to(PROJECTS_ROOT))
    project   = rel_path.split('/')[0] if '/' in rel_path else '_root'
    language  = filepath.suffix.lstrip('.').lower()
    mtime     = filepath.stat().st_mtime

    # Kontrola mtime — přeskočit pokud nezměněno
    if not force:
        existing = conn.execute(
            "SELECT file_mtime FROM code_chunks WHERE filepath = ? LIMIT 1",
            (rel_path,)
        ).fetchone()
        if existing and existing['file_mtime'] and abs(existing['file_mtime'] - mtime) < 1.0:
            return 0  # beze změny

    # Smazat staré chunky pro tento soubor
    conn.execute("DELETE FROM code_chunks WHERE filepath = ?", (rel_path,))

    # Chunking
    raw_chunks = get_chunks(filepath)
    if not raw_chunks:
        conn.commit()
        return 0

    count = 0
    for chunk in raw_chunks:
        try:
            emb = get_embedding(chunk['content'])
        except RuntimeError:
            raise
        except Exception:
            continue  # přeskočit chunk kde embedding selhal

        conn.execute(
            """INSERT INTO code_chunks
               (filepath, project, language, chunk_start, chunk_end,
                chunk_type, name, content, embedding, file_mtime)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rel_path, project, language,
             chunk['start'], chunk['end'],
             chunk['type'], chunk['name'],
             chunk['content'], store_embedding(emb), mtime)
        )
        count += 1

    conn.commit()
    return count


def cmd_index(args: argparse.Namespace) -> None:
    """Indexuje soubory do SQLite vector store."""
    extensions = DOCS_EXTENSIONS if getattr(args, 'docs', False) else CODE_EXTENSIONS

    files = get_project_files(
        project    = getattr(args, 'project', None),
        extensions = extensions,
        diff_only  = getattr(args, 'diff', False)
    )

    if not files:
        print(f"{Y}Žádné soubory k indexování.{R}")
        return

    conn   = init_index_db()
    force  = getattr(args, 'force', False)
    total  = 0
    skipped = 0

    print(f"\n{bold('INDEXOVÁNÍ')}  {D}{len(files)} souborů{R}")

    for fp in files:
        rel = str(fp.relative_to(PROJECTS_ROOT))
        count = index_file(conn, fp, force=force)
        if count > 0:
            print(f"  {G}+{count:>3}{R}  {C}{rel}{R}")
            total += count
        else:
            skipped += 1

    conn.close()
    print(f"\n  {bold('Hotovo:')} {total} chunků přidáno, {skipped} souborů beze změny.\n")


# ─── Vyhledávání ─────────────────────────────────────────────────────────────

def cmd_search(args: argparse.Namespace) -> None:
    """Sémantické vyhledávání přes indexovaný kód nebo dokumentaci."""
    query   = args.query
    top_n   = getattr(args, 'top', 5)
    project = getattr(args, 'project', None)
    scope   = getattr(args, 'scope', 'code')

    conn = init_index_db()

    # Sestavit WHERE
    conditions = []
    params: list = []

    if scope == 'docs':
        conditions.append("language = 'md'")
    else:
        conditions.append(f"language IN ({','.join('?' * len(CODE_EXTENSIONS))})")
        params.extend([ext.lstrip('.') for ext in CODE_EXTENSIONS])

    if project:
        conditions.append("project = ?")
        params.append(project)

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    # Načíst všechny chunky + embeddingy
    rows = conn.execute(f"""
        SELECT id, filepath, project, language, chunk_start, chunk_end,
               chunk_type, name, content, embedding
        FROM code_chunks {where}
    """, params).fetchall()

    conn.close()

    if not rows:
        print(f"{Y}Žádné indexované soubory. Spusť: agent index{R}")
        return

    # Query embedding + cosine similarity
    try:
        q_emb = get_embedding(query)
    except RuntimeError as e:
        print(f"\033[91mChyba:{R} {e}")
        return

    matrix = np.stack([load_embedding(r['embedding']) for r in rows])
    scores = cosine_similarity(q_emb, matrix)

    # Top-N výsledků
    top_idx = np.argsort(scores)[::-1][:top_n]

    print(f"\n{bold('VÝSLEDKY')}  {D}dotaz: \"{query}\"{R}  {D}scope: {scope}{R}")
    if project:
        print(f"  {D}projekt: {project}{R}")
    print()

    for rank, idx in enumerate(top_idx, 1):
        r     = rows[idx]
        score = scores[idx]

        # Zvýraznění skóre
        if score >= 0.75:   score_color = G
        elif score >= 0.55: score_color = Y
        else:               score_color = D

        # Krátký preview (první neprázdný řádek obsahu)
        preview_lines = [l.strip() for l in r['content'].splitlines() if l.strip()]
        preview = preview_lines[0][:100] if preview_lines else ''

        loc = f"{r['filepath']}:{r['chunk_start']}-{r['chunk_end']}"
        label = f"[{r['chunk_type']}: {r['name']}]" if r['name'] else f"[{r['chunk_type']}]"

        print(f"  {score_color}{score:.3f}{R}  {C}{loc}{R}  {D}{label}{R}")
        print(f"         {D}{preview}{R}")
        print()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='agent',
        description='Sémantický indexer kódu — SQLite + nomic-embed-text'
    )
    sub = parser.add_subparsers(dest='cmd')

    # ── agent index ───────────────────────────────────────────────────────────
    p_idx = sub.add_parser('index', help='Indexovat zdrojové soubory')
    p_idx.add_argument('--project', help='Indexovat jen jeden projekt')
    p_idx.add_argument('--diff',    action='store_true', help='Jen git-změněné soubory')
    p_idx.add_argument('--force',   action='store_true', help='Ignoruj mtime, přeindexuj vše')
    p_idx.add_argument('--docs',    action='store_true', help='Indexovat i .md soubory')

    # ── agent search ──────────────────────────────────────────────────────────
    p_srch = sub.add_parser('search', help='Sémantické vyhledávání v kódu')
    p_srch.add_argument('query', help='Dotaz v přirozené řeči nebo kódu')
    p_srch.add_argument('--project', help='Omezit na projekt')
    p_srch.add_argument('--top',     type=int, default=5, help='Počet výsledků (výchozí: 5)')
    p_srch.add_argument('--scope',   choices=['code', 'docs'], default='code',
                        help='code = zdrojáky, docs = CLAUDE.md soubory')

    args = parser.parse_args()

    if args.cmd == 'index':
        cmd_index(args)
    elif args.cmd == 'search':
        cmd_search(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
