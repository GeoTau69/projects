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

## Persistence paměti — Cross-model kontextový přenos

**Problém:** Claude Code ztrácí kontext po odhlášení. Při přepnutí mezi modely (Haiku → Sonnet → Opus) nebo mezi seseionami zmizí všechny informace o tom co se dělalo.

**Řešení:** Třívrstvý systém persistence, který zachovává kontext napřích seseionami a modely.

### Architektura persistence

```
VRSTVA 1: CLAUDE.md (master)     — stable, versioned, git
         └─ Zlaté pravidlo: "Před koncem session ulož vše"
         └─ Signální fráze: "konec zvonec" = trigger pro AI modely

VRSTVA 2: memory/ adresář         — volatile, auto-loaded
         ├─ MEMORY.md            ← AUTO-NAČÍTÁN Claudem při každé session
         │  └─ Aktuální úkol, poslední akce, next steps (max 200 řádků)
         └─ session.md           ← Detailní session log + template

VRSTVA 3: MODEL.md               — handoff dokument
         └─ SESSION LOG (nejnovější nahoře)
         └─ Architektura, znalosti, problémy
```

### Soubory a jejich role

| Soubor | Umístění | Role | Kdo píše | Kdo čte | Format |
|--------|----------|------|---------|--------|--------|
| **CLAUDE.md** | `/home/geo/projects/` | Master pravidla + golden rule | Developer + AI | Vždy auto-načten | Markdown |
| **MEMORY.md** | `~/.claude/projects/.../memory/` | Volatile session state | **Jakýkoliv model** | **Vždy auto-načten** | Markdown |
| **session.md** | `~/.claude/projects/.../memory/` | Detailní session log | Jakýkoliv model | Manuálně | Markdown |
| **MODEL.md** | `/home/geo/projects/` | AI handoff + architektura | Jakýkoliv model | Čtení pro kontext | Markdown |

### Mechanismus — jak to funguje

#### 1. Normální session (bez `konec zvonec`)
```
Model pracuje na úkolu
    → Když skončí sesseion, kontext ZMIZÍ
    → Ale MEMORY.md už obsahuje poslední stav
    → Nový model to načte a naváže
```

#### 2. Signální fráze `konec zvonec`
```
Uživatel: "konec zvonec"
    ↓
Model (Haiku/Sonnet/Opus):
  1. Tiše aktualizuje MEMORY.md (aktuální úkol + poslední akce + next steps)
  2. Tiše přidá záznam do MODEL.md SESSION LOG
  3. Tiše commitne: git add MODEL.md && git commit && git push
  4. Napíše: "Vše synchronizováno — můžeš se odhlásit."
```

#### 3. Příští session — auto-load
```
Uživatel se přihlásí (jakýkoliv model)
    ↓
Claude Code auto-načte: `~/.claude/projects/.../memory/MEMORY.md`
    ↓
Model vidí: "Poslední úkol byl..., poslední akce byla..., next steps jsou..."
    ↓
Model pokračuje kde skončil předchozí (bez ztrát)
```

### Praktický příklad — přepínání modelů

```
Session 1: Sonnet pracuje na dokumentaci
  ↓ "konec zvonec"
  → MEMORY.md: "Psáli jsme sekci 'Token Tracker', zbývá 'Routing'"
  → MODEL.md: "Sonnet #4 — dokumentace AI projektu"

Session 2: Haiku se přihlásí na stejný projekt
  ↓ MEMORY.md je auto-načten
  ↓ Haiku vidí: "Pokračuj v sekci 'Routing' pro dokumentaci"
  ✓ Haiku bezpečně navazuje bez ztrát

Session 3: Sonnet se vrátí
  ↓ MEMORY.md je stále zde
  ↓ Sonnet vidí co Haiku udělal ("Haiku skončil u 'Model Routing'")
  ✓ Sonnet pokračuje dál
```

### Obsah MEMORY.md — co tam je

```markdown
## Aktuální úkol
- Co právě řešíme (brief popis)
- Status (In progress / Hotovo / Blokáno)

## Poslední session
- Co bylo uděláno (bullet list)
- Problémy které jsme NEdořešili
- Otevřené blockers

## Next Steps
- Co zbývá udělat (ordered list)

## Otevřené problémy / Blockers
- Věc 1
- Věc 2

## Klíčové soubory (quick ref)
- CLAUDE.md — kde jsou pravidla
- MODEL.md — kde je architektura

## SESSION LOG (stručný)
| Datum | Co | Status |
| ... | ... | ... |
```

### Obsah MODEL.md SESSION LOG — co tam je

```markdown
### YYYY-MM-DD — [Model] session #N ([téma])
**Co:**
- Bod 1
- Bod 2

**Otevřené:**
- Problém který se nevyřešil

**Timestamp:** YYYY-MM-DD HH:MM CET
```

Každý nový záznam jde na ZAČÁTEK (nejnovější nahoře).

### Golden Rule — Co MUSÍŠ dělat

```
PŘED KONCEM JAKÉKOLIV SESSION:

1. Řekni "konec zvonec"
2. Já (jakýkoliv model) automaticky:
   → aktualizuji MEMORY.md
   → přidám záznam do MODEL.md
   → commitnu + pushnu
3. Napíšu: "Vše synchronizováno — můžeš se odhlásit."
4. Teprve pak se můžeš odhlásit
```

**Bez tohoto = kontext navždy ztracen.**

### Praktické situace

**Situace 1: Aktualizace dokumentace v session**
```
Sonnet: "Přidej sekci 'Persistence paměti' do ai/CLAUDE.md"
[Sonnet to dělá]
Uživatel: "konec zvonec"
→ MEMORY.md: "Právě jsem přidal sekci persistence do ai/CLAUDE.md"
→ MODEL.md: Nový záznam
→ Git: Commit pushnutý
```

**Situace 2: Dlouhý úkol přes více session**
```
Session 1 (Sonnet): Napsal kód pro feature X
  "konec zvonec" → MEMORY.md: "Kód hotov, zbývá testování"

Session 2 (Haiku): Generuje testy
  Auto-load MEMORY.md → ví co je hotovo
  "konec zvonec" → MEMORY.md: "Testy napsány, zbývá review"

Session 3 (Sonnet): Dělá code review
  Auto-load MEMORY.md → ví co už je hotovo
  "konec zvonec" → MEMORY.md: "Review hotov, ready to merge"
```

### Limity a poznámky

- **Max 200 řádků v MEMORY.md** — musíš být stručný, není to archiv
- **session.md nemusíš updatovat ručně** — je to spíš reference pro detailní logy
- **MODEL.md je verzovaný v git** — to je dlouhodobá paměť
- **Signál "konec zvonec" je case-sensitive** — přesně tak jak je psáno
- **Platí pro všechny modely bez výjimky** — Haiku, Sonnet, Opus všichni musí dodržovat

- [ ] Git post-commit hook: automatické `agent index --diff` po každém commitu
- [ ] Komplexní dokumentace v tomto adresáři (popis konceptů, architektura, příklady)
- [ ] Dokončit docs pipeline pro projekty: `dashboard/`, `web-edit/`, `docs/`
- [ ] Reálné testování `call_api` s Anthropic API klíčem
- [ ] `agent billing --export csv` pro analýzy nákladů
