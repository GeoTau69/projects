# AI Dev Agent Stack

Sada nástrojů pro optimalizaci práce s AI v rámci workspace.
Všechny nástroje jsou v `_meta/`, CLI dostupné globálně přes `~/bin/agent`.

## Stav implementace (2026-02-21)

| Modul | Status | Soubor |
|-------|--------|--------|
| Token účetnictví | ✅ HOTOVO | `_meta/token_tracker.py` |
| Prompt cache / deduplication | ✅ HOTOVO | `_meta/token_tracker.py` |
| Sémantický vyhledávač kódu | ✅ HOTOVO | `_meta/chroma_indexer.py` |
| Model routing | ✅ HOTOVO | `_meta/token_tracker.py` |
| Docs pipeline (JSON/Jinja2) | ✅ HOTOVO | `docs/build.py` |
| **Persistence paměti** | ✅ HOTOVO | `memory/MEMORY.md` + `memory/session.md` + Golden Rule |

## Architektura

```
~/bin/agent  (router)
    ├── log / billing / cache / route / init  →  _meta/token_tracker.py
    └── index / search                         →  _meta/chroma_indexer.py

Databáze: ~/.ai-agent/
    ├── tokens.db       — token log + prompt cache (SQLite)
    └── code_index.db   — kódové chunky + numpy embeddingy (SQLite)

Ollama (lokální):
    ├── nomic-embed-text  — embeddingy pro sémantické vyhledávání
    └── qwen2.5-coder:14b — lokální LLM pro doc_update, boilerplate, info_sync
```

## Token Tracker (`_meta/token_tracker.py`)

SQLite účetnictví všech API volání + prompt cache + model routing.

### CLI

```bash
# Manuální záznam (pro Claude Code sessions)
agent log --project X --operation doc_update --model sonnet --in 5000 --out 1200 [--notes "..."]

# Přehledy
agent billing                    # vše
agent billing --today            # jen dnes
agent billing --week             # posledních 7 dní
agent billing --month            # posledních 30 dní
agent billing --project X        # filtr projektu
agent billing --model sonnet     # filtr modelu
agent billing --top              # top operace dle ceny

# Prompt cache
agent cache --stats              # statistiky + TTL pravidla
agent cache --list               # seznam uložených odpovědí
agent cache --clear              # smazat expirované
agent cache --clear --all        # smazat vše

# Model routing
agent route --show               # zobrazit routing tabulku
agent route --test doc_update    # otestovat routing pro operaci

# Init
agent init                       # inicializovat ~/.ai-agent/ a DB
```

### Python import

```python
from _meta.token_tracker import call_api

# model='auto' → routing tabulka rozhodne (Ollama nebo Claude)
text = call_api(
    project   = 'backup-dashboard',
    operation = 'doc_update',        # → Ollama dle ROUTING_RULES
    model     = 'auto',
    messages  = [{'role': 'user', 'content': 'Vygeneruj dokumentaci pro ...'}],
    system    = 'Jsi technický dokumentarista...',  # volitelné
)
# Automaticky: routing → cache lookup → API call → log + cache store
```

### Ceny modelů (aktualizovat dle anthropic.com/pricing)

| Model | Input | Output |
|-------|-------|--------|
| claude-opus-4-6 | $15/M | $75/M |
| claude-sonnet-4-6 | $3/M | $15/M |
| claude-haiku-4-5 | $0.80/M | $4/M |
| Ollama (lokální) | $0 | $0 |

### Prompt cache TTL

| Operace | TTL | Důvod |
|---------|-----|-------|
| `doc_update` | 24h | Dokumentace se nemění každou hodinu |
| `boilerplate` | 48h | Šablony jsou stabilní |
| `info_sync` | 12h | Kratší TTL — git info se mění |
| `code_review` | 0 (vypnuto) | Vždy čerstvá analýza |
| `architecture` | 0 (vypnuto) | Vždy čerstvá analýza |
| `debug` | 0 (vypnuto) | Kontext se mění |

### Model routing tabulka

| Operace | Cíl | Model |
|---------|-----|-------|
| `doc_update` | local | qwen2.5-coder:14b |
| `boilerplate` | local | qwen2.5-coder:14b |
| `info_sync` | local | qwen2.5-coder:14b |
| `code_review` | cloud | claude-sonnet-4-6 |
| `architecture` | cloud | claude-opus-4-6 |
| `debug_complex` | cloud | claude-sonnet-4-6 |
| `_default` | cloud | claude-sonnet-4-6 |

Změna lokálního modelu: upravit `LOCAL_MODEL` v `token_tracker.py`.

## Sémantický vyhledávač (`_meta/chroma_indexer.py`)

**Poznámka:** chromadb nekompatibilní s Python 3.14 → vlastní implementace přes SQLite + numpy.

Stack: SQLite BLOB pro embeddingy, numpy pro cosine similarity, nomic-embed-text přes Ollama HTTP.

### CLI

```bash
# Indexování
agent index                          # celý workspace (mtime cache)
agent index --project dashboard      # jen jeden projekt
agent index --diff                   # jen git-changed soubory (git diff HEAD)
agent index --force                  # ignoruj mtime, přeindexuj vše
agent index --docs                   # indexuj i .md soubory

# Vyhledávání
agent search "retry logika"
agent search "záloha borg archiv" --project backup-dashboard
agent search "WebSocket rooms"  --top 10
agent search "co projekt dělá" --scope docs    # hledá v .md souborech
```

### Chunking strategie

| Typ souboru | Strategie | Chunk = |
|-------------|-----------|---------|
| `.py` | Per definice | jedna `def` nebo `class` |
| `.md` | Per sekce | jeden `#` nebo `##` nadpis |
| ostatní | Sliding window | 60 řádků, 10 overlap |

### Výsledky

```
0.708  backup-dashboard/routes/borg.py:45-89  [function: create_archive]
       def create_archive(path: Path, name: str) -> dict:

0.656  docs/build.py:51-59  [function: compute_hash]
       def compute_hash(data) -> str:
```

Skóre ≥ 0.75 → zelená, ≥ 0.55 → žlutá, ostatní → šedá.

## Docs pipeline (`docs/build.py`)

AI generuje `docs/data/{projekt}.json`, `build.py` renderuje HTML přes Jinja2 (bez AI).

```bash
python3 docs/build.py                              # všechny projekty
python3 docs/build.py --project backup-dashboard   # jen jeden
python3 docs/build.py --check                      # jen validace JSON
python3 docs/build.py --force                      # ignoruj hash cache
python3 docs/build.py --output /cesta/soubor.html  # vlastní výstup
```

**Klíčové pravidlo:** Pole pro seznam položek v JSON blocích = `entries` (nikoli `items` — Jinja2 conflict).

## Persistence paměti

Viz Golden Rule v `/home/geo/projects/CLAUDE.md` a `memory/MEMORY.md`.

- [ ] Git post-commit hook: automatické `agent index --diff` po každém commitu
- [ ] Komplexní dokumentace v tomto adresáři (popis konceptů, architektura, příklady)
- [ ] Dokončit docs pipeline pro projekty: `dashboard/`, `web-edit/`, `docs/`
- [ ] Reálné testování `call_api` s Anthropic API klíčem
- [ ] `agent billing --export csv` pro analýzy nákladů
