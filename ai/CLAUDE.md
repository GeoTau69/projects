# AI Dev Agent Stack

Sada nástrojů pro optimalizaci práce s AI v rámci workspace.
Všechny nástroje jsou v `_meta/`, CLI dostupné globálně přes `~/bin/agent`.

## Stav implementace (2026-02-22)

| Modul | Status | Soubor |
|-------|--------|--------|
| Token účetnictví | ✅ HOTOVO | `_meta/token_tracker.py` |
| Prompt cache / deduplication | ✅ HOTOVO | `_meta/token_tracker.py` |
| Sémantický vyhledávač kódu | ✅ HOTOVO | `_meta/chroma_indexer.py` |
| Model routing | ✅ HOTOVO | `_meta/token_tracker.py` |
| Docs pipeline (JSON/Jinja2) | ✅ HOTOVO | `docs/build.py` |
| **Plugin orchestrator** | ✅ HOTOVO | `_meta/orchestrator.py`, `_meta/plugins/` |
| **Persistence paměti** | ✅ HOTOVO | `memory/MEMORY.md` + Golden Rules |

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

# AI request (Orchestrator)
agent ask "prompt" --operation code_review --project X
agent ask "ahoj" --model sonnet --project cli

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

## Golden Rules — Session persistence

Viz detailní guide v `/home/geo/projects/CLAUDE.md`.

### Signální fráze

| Fráze | Kdy | Co agent udělá |
|-------|-----|-----------------|
| **`štafeta`** | Předání jinému modelu (před `/model`) | Aktualizuje oba MEMORY.md se shrnutím + specifikací. Bez git, bez sanitace. Napíše: *"Štafeta předána — přepni model."* |
| **`konec zvonec`** | Konec práce, odhlášení | Sanitace + oba MEMORY.md + MODEL.md session log + git commit + push. Napíše: *"Vše synchronizováno — můžeš se odhlásit."* |

### Pravidlo 1: Dual MEMORY.md (synchronizace)

Auto-load cesty dle CWD:
- Start z `/home/geo/projects/` → `~/.claude/projects/-home-geo-projects/memory/MEMORY.md`
- Start z `/home/geo/` → `~/.claude/projects/-home-geo/memory/MEMORY.md`

**Při štafetě/konec zvonec: aktualizovat OŘBA** aby se kontext neztratil mezi session/modely.

### Pravidlo 2: Model routing (3 role)

| Model | Role | Odpovědnost | Kdy |
|-------|------|-------------|-----|
| **Opus 4.6** | Architekt | Návrh, audit, složité problémy, specifikace | Architektonická rozhodnutí |
| **Sonnet 4.6** | SW inženýr | Implementace dle specifikace, vývoj, refactoring | Veškerý kód |
| **Haiku 4.5** | Dokumentarista | Generování docs z CLAUDE.md → JSON → HTML | `docs/data/{projekt}.json` |

Workflow:
1. **Opus** navrhne architekturu → zapíše spec do MEMORY.md
2. **Sonnet** implementuje dle spec + aktualizuje `{projekt}/CLAUDE.md`
3. **Haiku** čte CLAUDE.md → generuje `docs/data/{projekt}.json` → `build.py` renderuje HTML

### Pravidlo 3: Output stručnost — POVINNÉ

Maximální priorita: minimalizovat output tokeny (uživatel platí).

**Mezi tool cally:** Žádný komentář pokud není architektonické rozhodnutí.
**Na začátku:** Max 3 bullet points co se změní.
**Na konci:** Max 3 bullet points co se změnilo.
**Vynechat:** "teď udělám X", debug output, mechanický průběh.

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

Auto-loaded soubor: `memory/MEMORY.md` obsahuje aktuální úkol, next steps, specifikace pro handoff.

Viz Golden Rules výše + detailní guide v `/home/geo/projects/CLAUDE.md`.

### Orchestrator (`_meta/orchestrator.py`)

Plugin-based AI middleware s centrálním cache a billing. Nahrazuje monolitický `token_tracker.py`.

#### Architektura

```
Orchestrator
  ├── register(Backend)  — registrace backendu (Claude, Ollama)
  └── request()          — entry point
      ├── 1. Semantic cache lookup (nomic-embed-text embeddingy)
      ├── 2. Hash cache lookup (SHA-256)
      ├── 3. Router: select_backend() — dle operation
      ├── 4. Execute: backend.execute()
      ├── 5. Log billing (DB)
      ├── 6. Cache store
      └── 7. Return Response
```

#### CLI

```bash
agent ask "prompt" --operation code_review --project X [--model auto]
```

Zobrazuje spinner `⠋ Zpracovávám... [model]` během volání.

#### Moduly

| Modul | Role |
|-------|------|
| `plugins/base.py` | Backend ABC + Response dataclass |
| `plugins/claude.py` | Anthropic API (is_available checks ANTHROPIC_API_KEY) |
| `plugins/ollama.py` | Ollama HTTP (is_available checks localhost:11434) |
| `billing.py` | DB, ceny, hash cache funcs |
| `router.py` | ROUTING_RULES, select_backend(), CACHE_TTL |
| `semantic_cache.py` | nomic-embed-text embeddingy, cosine similarity lookup |
| `orchestrator.py` | Orchestrator class — core |

#### Python API

```python
from _meta.orchestrator import Orchestrator
from _meta.plugins.claude import ClaudeBackend
from _meta.plugins.ollama import OllamaBackend

orch = Orchestrator()
orch.register(ClaudeBackend())
orch.register(OllamaBackend())

resp = orch.request(
    messages   = [{'role': 'user', 'content': '...'}],
    operation  = 'code_review',
    project    = 'backup-dashboard',
    model      = 'auto',  # → routing tabulka
    system     = '...',   # volitelné
    max_tokens = 4096,
)
print(resp.text)
print(f"Cost: ${resp.cost:.4f}")
```

---

## TODO

- [ ] Git post-commit hook: automatické `agent index --diff` po každém commitu
- [ ] Reálné testování `call_api` s Anthropic API klíčem
- [ ] `agent billing --export csv` pro analýzy nákladů
- [ ] Quota-aware routing (rate limit headers, error 429 fallback)
