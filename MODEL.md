# MODEL.md — AI-to-AI Handoff & Knowledge Base

> Účel: Přechod znalostí mezi modely (Haiku 4.5 → Sonnet 4.6 → Opus 4.6)
> Poslední update: 2026-02-20 14:15 CET
> Aktuální model: Claude Haiku 4.5

---

## 📝 SESSION LOG (nejnovější nahoře)

### 2026-02-20 14:15 — Haiku session #2
**Co:** Čtení handoff od Sonneta, potvrzení dass chápu workflow.
- ✅ Přečetl jsem `docs/AI_WORKFLOW.md` — trap list, postup, checklist
- ✅ Rozumím: `entries` ne `items`, Unicode uvozovky, validace přes `build.py --check`
- ✅ Ready: příště budu generovat dokumentaci bez chyb
**Status:** Ready for next doc task

### 2026-02-20 10:00 — Sonnet session #1
**Co:** Integrace HTML docs do UI sidebar + dokumentace pro Haiku
- ✅ Implementoval Option A: `/docs/` endpoint v sidebar (📖 ikony)
- ✅ Vytvořil `docs/AI_WORKFLOW.md` — kompletní guide pro Haiku
- ✅ Přidal odkazy v `docs/CLAUDE.md` a `MODEL.md`
**Status:** Dokumentace pro Haiku je hotová a ready

### 2026-02-20 09:30 — Haiku session #1
**Co:** Vytvoření AI dokumentace a handoff pro Sonneta
- ✅ Vygeneroval `docs/data/ai.json` (12 sekcí, vrstvitá dokumentace)
- ✅ Přidal `/docs/{projekt}` endpoint do `docserver.py`
- ✅ Vytvořil `MODEL.md` — handoff dokument
**Status:** Dokumentace AI projektu hotová, integrace částečná

---

## 🎯 Stav projektu — TL;DR

**Workspace**: `/home/geo/projects/` — monorepo s 6 aktivními projekty
**Primární fokus**: `ai/` projekt — stack nástrojů pro optimalizaci práce s AI

| Komponenta | Status | Poznámka |
|-----------|--------|----------|
| **Token Tracker** | ✅ HOTOVO | Účetnictví API, SQLite, CLI `agent` |
| **Prompt Cache** | ✅ HOTOVO | TTL dedup, cache lookup/store |
| **Semantic Search** | ✅ HOTOVO | SQLite+numpy, nomic-embed-text z Ollamy |
| **Model Routing** | ✅ HOTOVO | Automatický výběr LLM (local vs cloud) |
| **Docs Pipeline** | ✅ HOTOVO | JSON→HTML (Jinja2), build.py, schema |
| **AI Dokumentace** | ✅ HOTOVO | `docs/data/ai.json` (12 sekcí, 1300+ řádků) |
| **Docs integrace** | 🟡 ČÁSTEČNĚ | `/docs/{projekt}` endpoint přidán, ale UI neví |
| **Git post-commit hook** | ❌ TODO | Volitelně — automatické reindexování |
| **Ostatní docs** | ❌ TODO | dashboard.json, web-edit.json, docs.json |

---

## 📚 Architektura celého workspace

```
/home/geo/projects/                    # Monorepo root (main branch)
├── CLAUDE.md                           # Master dokumentace + tabulka projektů
├── todo.md                             # Centrální backlog
├── MODEL.md                            # TENTO SOUBOR — handoff pro AI modely
├── Makefile                            # Příkazy: make docs, make validate, make new-project
├── .systems.json                       # Registr sledovaných služeb
│
├── ai/                                 # ← FOKUS TOHOTO VÝVOJE
│   ├── project.yaml                    # Metadata (status: active, port: null)
│   ├── CLAUDE.md                       # Dokumentace AI stacku
│   └── (žádné zdrojové kódy ještě — jen koncepty v CLAUDE.md)
│
├── backup-dashboard/                   # Port 8090, systemd: backup-dashboard
│   ├── app.py, helpers.py, routes/     # FastAPI aplikace
│   ├── project.yaml, CLAUDE.md
│   └── docs/docs.html                  # 1268 řádků inline HTML (migruj do JSON!)
│
├── dashboard/                          # Port 8099, systemd: projects-dashboard
│   ├── dashboard.py                    # Single-file, stdlib only
│   └── project.yaml, CLAUDE.md
│
├── docs/                               # Port 8080, systemd: docs
│   ├── docserver.py                    # SPA + API endpoints
│   ├── build.py                        # JSON→HTML renderer (Jinja2)
│   ├── schema/doc_schema.json          # JSON Schema pro validaci
│   ├── templates/project.html.j2       # Jinja2 šablona
│   ├── data/                           # AI generuje pouze tyto soubory
│   │   ├── ai.json                     # ✅ Vytvořeno
│   │   └── backup-dashboard.json       # ✅ Vytvořeno (z docs.html)
│   └── output/                         # Vygenerované HTML (build.py)
│       ├── ai.html (43 kB)
│       └── backup-dashboard.html (37 kB)
│
├── web-edit/                           # Port 8765, systemd: mdserver
│   ├── app.py                          # Aiohttp server
│   └── project.yaml, CLAUDE.md
│
└── git/                                # Dokumentace git setupu
    ├── project.yaml, CLAUDE.md
    └── (no code — dokumentace pouze)
```

---

## 🔑 Klíčové koncepty a implementace

### 1. docs/ — Dvoustupňový pipeline

**Problém**: AI generování HTML je plýtvání tokeny → 100 API volání = 100× re-render

**Řešení**:
- **Fáze 1 (AI)**: Generuj jen JSON strukturu (data-only)
- **Fáze 2 (Python)**: Renderuj HTML přes Jinja2 (bez AI)

**Workflow**:
```
User pořadavek
    ↓
AI vygeneruje docs/data/{projekt}.json (strukturované, bez HTML)
    ↓
python build.py --project X
    ↓
Jinja2 šablona (project.html.j2) renderuje HTML
    ↓
docserver.py obsluhuje na http://localhost:8080/docs/{projekt}
```

**Klíčové soubory**:
- `schema/doc_schema.json` — co AI musí vygenerovat (povinná pole, typy)
- `templates/project.html.j2` — jak se to vykreslí
- `build.py` — CLI tool s MD5 hash detekčí změn (inkrementální build)
- `docserver.py` — HTTP server s discovery a API endpointy

**Klíčová pravidla**:
- 🔴 **NIKDY** nepoužívej `"items"` v JSON seznamech — to je reserved v Pythonu/Jinja2. Použij **`"entries"`**
- JSON struktura má: `modules` (API/CLI/třídy) + `sections` (dokumentace)
- Každá sekce má `blocks` (text, code, table, card, list, heading, live_status)

### 2. docserver.py — Discovery + API

**Jak funguje**:
1. `load_projects()` — čte všechny `project.yaml` v ROOT a filtruje (skip `.`, `_`)
2. `api_projects()` — vrací JSON se statusem portů (live check)
3. `api_md()` — obsluhuje `/api/md?dir=X` — surový markdown CLAUDE.md
4. **NOVÝ**: `/docs/{projekt}` — obsluhuje HTML z `docs/output/{projekt}.html`

**Discovery logika** (`parse_simple_yaml`):
- Čte YAML bez yaml modulu (stdlib only)
- Přeskakuje listy `[...]` — nejsou potřeba
- Key-value páry: `name: value` → `{"name": "value"}`

**Problem**: UI (JavaScript) ví jen o `/api/md?dir=`, nezná `/docs/` endpoint. Ale `/docs/ai` fyzicky funguje — zkus v prohlížeči přímo.

### 3. build.py — Jinja2 renderer

```bash
# Principy:
python build.py                    # Builduj všechny (dle hash cache)
python build.py --project ai       # Jen jeden projekt
python build.py --check            # Validuj JSON schéma (bez renderu)
python build.py --force            # Ignoruj hash, rebuilduj

# Interně:
1. Načti docs/data/{projekt}.json
2. Validuj proti schema/doc_schema.json
3. Vypočítej MD5 hash
4. Je v cache? Beze-změn? → SKIP
5. Jinak: vyrenderuj Jinja2 → HTML
6. Ulož hash do .build-state.json
```

**Důležité**: Hash-based inkrementální build = úspora času, když se jen jedna sekce změní.

### 4. AI dokumentace — `docs/data/ai.json`

**Vytvořeno v tomto vývoji**:
- 12 sekcí: Přehled, Slovník, Architektura, Token Tracker, Prompt Cache, Search, Routing, Docs Pipeline, Use Cases, FAQ, Setup, Troubleshooting
- Vrstvitá vysvětlení: beginner → advanced
- Kódové příklady: Python, Bash, JSON

**Struktura**:
```json
{
  "project": "ai",
  "display_name": "AI Dev Agent Stack",
  "modules": [
    {
      "id": "token_tracker",
      "name": "Token Tracker",
      "file": "_meta/token_tracker.py",
      "purpose": "SQLite účetnictví API volání...",
      "status": "stable",
      "public_methods": [...],
      "dependencies": [],
      "notes": "..."
    }
  ],
  "sections": [
    {
      "id": "prehled",
      "title": "Přehled",
      "icon": "📚",
      "blocks": [
        {"type": "text", "text": "..."},
        {"type": "table", "headers": [...], "rows": [...]},
        {"type": "code", "lang": "bash", "text": "..."},
        {"type": "card", "variant": "info", "title": "...", "entries": [...]}
      ]
    }
  ]
}
```

---

## 🛠️ Jak vše funguje dohromady

### Tok uživatelského požadavku

```
User: "Potřebuju dokumentaci pro projekt X"
    ↓
[Claude] call_api(project='X', operation='doc_update', model='auto', ...)
    ↓
[token_tracker.py]
  ├─ Routing: doc_update → local (Ollama)
  ├─ Cache lookup: existuje hash?
  │  ├─ Yes → vrať cached response ($0 cost)
  │  └─ No → pokračuj
  ├─ Pošli do Ollama (qwen2.5-coder:14b, zdarma)
  ├─ Ulož: token log + cache s TTL (24h)
  └─ Vrať: JSON strukturu
    ↓
[docs/build.py]
  ├─ Ulož JSON do docs/data/X.json
  ├─ Validuj schéma
  ├─ Hash detekce: změna?
  │  ├─ Yes → renderuj
  │  └─ No → skip (cache hit)
  ├─ Jinja2 renderuje → HTML
  └─ Ulož do docs/output/X.html
    ↓
[docserver.py] na portu 8080
  └─ GET /docs/X → serve docs/output/X.html
    ↓
Browser: http://localhost:8080/docs/X
  └─ Vidí hotový HTML (dark theme, responsive)
```

### Model Routing Tabulka

```python
ROUTING_RULES = {
    'doc_update':    'local',    # Ollama qwen2.5-coder (zdarma, 24h cache)
    'boilerplate':   'local',    # Ollama (zdarma, 48h cache)
    'info_sync':     'local',    # Ollama (zdarma, 12h cache)
    'code_review':   'sonnet',   # Claude Sonnet ($$, 0h cache)
    'architecture':  'opus',     # Claude Opus ($$$, 0h cache)
    'debug_complex': 'sonnet',   # Claude Sonnet
    '_default':      'sonnet',   # fallback
}
```

**Princip**: Levné operace na Ollama, drahé na Claude. Cache vypnutý pro analýzy (vždy čerstvá data).

---

## 📦 Databáze: `~/.ai-agent/`

### tokens.db (SQLite)

```sql
CREATE TABLE token_log (
    id           INTEGER PRIMARY KEY,
    timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP,
    project      VARCHAR(50),
    operation    VARCHAR(50),
    model        VARCHAR(30),
    tokens_in    INTEGER,
    tokens_out   INTEGER,
    cost_usd     DECIMAL(10,6),
    prompt_hash  VARCHAR(64)
);

-- Cache rozšíření:
ALTER TABLE token_log ADD COLUMN response_text TEXT;
ALTER TABLE token_log ADD COLUMN cache_hit BOOLEAN;
ALTER TABLE token_log ADD COLUMN ttl_expire DATETIME;
```

### code_index.db (SQLite)

```sql
CREATE TABLE embeddings (
    id              INTEGER PRIMARY KEY,
    file_path       VARCHAR(255),
    chunk_text      TEXT,
    chunk_hash      VARCHAR(64),
    mtime           INTEGER,
    embedding       BLOB  -- numpy array serialized
);

CREATE TABLE search_results (
    query           TEXT,
    chunk_id        INTEGER,
    similarity      REAL,
    rank            INTEGER
);
```

---

## ⚙️ CLI Příkazy (`~/bin/agent` router)

```bash
# Token Tracker
agent billing [--today|--week|--month|--top|--project X|--model M]
agent log --project X --operation Y --model Z --in 5000 --out 1200
agent cache [--stats|--list|--clear|--clear --all]
agent route [--show|--test OPERACE]

# Semantic Search
agent index [--project X|--diff|--force|--docs]
agent search "DOTAZ" [--project X|--top N|--scope docs]

# Init
agent init  # vytvoří ~/.ai-agent/ + inicializuj databáze
```

---

## 🚀 Co jsem vyvíjel (Haiku session)

1. ✅ **Přečetl jsem vše** — všechny CLAUDE.md, archit, koncepty
2. ✅ **Vytvořil jsem docs/data/ai.json** — 1300+ řádků, 12 sekcí, vrstvitá
3. ✅ **Buildoval jsem HTML** — `build.py --project ai --force`
4. ✅ **Přidal jsem `/docs/{projekt}` endpoint** do docserver.py
5. ✅ **Restartoval jsem docs service** — HTTP 200 na `/docs/ai`
6. ✅ **Vytvořil jsem TENTO MODEL.md** — handoff pro Sonneta

---

## ❌ Co ZBÝVÁ (TODO)

### Vysoká priorita

1. **UI integrace** — JavaScript v docserver.py ví jen o `/api/md?dir=`
   - Potřeba: Přidat do sidebar odkaz na `/docs/{projekt}` kde existuje HTML
   - Nebo: Přidej tab "📖 Dokumentace" která linkuje na `/docs/`

2. **Ostatní docs** — fáze B migrace
   - [ ] `docs/data/dashboard.json` → `python build.py --project dashboard`
   - [ ] `docs/data/web-edit.json` → `python build.py --project web-edit`
   - [ ] `docs/data/docs.json` (samotný docs projekt)

### Střední priorita

3. **Git post-commit hook** (volitelné)
   ```bash
   .git/hooks/post-commit:
   #!/bin/bash
   agent index --diff
   python build.py --force
   ```

4. **CSV export** — `agent billing --export ~/costs.csv`

### Nízká priorita

5. **Reálné testování** — až budou skutečné API skripty

---

## 💡 Know-How & Tricky Stuff

### Build.py — Inkrementální build

Problem: Jinja2 rendering je pomalý na velkých datech
Řešení: MD5 hash cache — rebuild jen když se data změní
```python
state = load_state()  # load .build-state.json
hash_data = doc      # nebo jen jedna sekce
current_hash = compute_hash(hash_data)
if state.get(state_key) == current_hash:
    print("SKIP — beze změn")
    return False
# Renderuj a ulož hash
```

### Docserver discovery

Problem: Jak najít všechny projekty bez centrálního registru?
Řešení: `project.yaml` v každém adresáři
```python
for entry in ROOT.iterdir():
    if entry.is_dir() and not entry.name.startswith('.'):
        yaml_path = entry / 'project.yaml'
        if yaml_path.exists():
            projects.append(parse_yaml(yaml_path))
```

### Jinja2 a "items" klíč

⚠️ **PAST TRAP**: `items` je Python dict method → Jinja2 getattr zachytí dříve
```json
// ✗ ŠPATNĚ — Jinja2 vrátí dict.items() metodu
{"type": "list", "items": [...]}

// ✓ SPRÁVNĚ
{"type": "list", "entries": [...]}
```

### TTL Cache strategie

TTL se liší dle operace:
- `doc_update` (24h) — dokumentace se mění zřídka
- `boilerplate` (48h) — šablony jsou stabilní
- `code_review` (0) — chceme vždy čerstvou analýzu
- `architecture` (0) — architektura se mění

**Princip**: Dlouhý TTL = ušetříš peníze. Ale pokud máš živý context (git logs), nastav 0.

---

## 🔐 Bezpečnost

- **Path traversal**: `docserver.py` kontroluje `candidate.resolve().parent == ROOT.resolve()`
- **SQL injection**: Nepoužívej raw SQL queries — SQLite bindings jsou safe
- **XSS**: HTML v JSON je trusted — jen CLAUDE.md data, ne user input
- **RCE**: Žádné subprocess bez seznam known commands

---

## 📖 Dokumentace pro Haiku — generování docs

Před generováním dokumentace přečti: **`docs/AI_WORKFLOW.md`**
Obsahuje: postup krok za krokem, strukturu JSON, trap list, checklist.

## 📋 Checklist pro dalšího modela (Sonnet 4.6+)

Když budeš pokračovat, zkontroluj:

- [ ] Všechny CLAUDE.md projekty čtu a rozumím workflow
- [ ] Vím, jak build.py funguje (JSON → HTML, hash cache)
- [ ] Vím, jak routing decisions fungují (local vs cloud LLM)
- [ ] Znám klíčová pravidla: `entries` ne `items`, TTL per operace
- [ ] Vidím `/docs/ai` v prohlížeči na http://localhost:8080/docs/ai
- [ ] Chci pokračovat s: **UI integrací** (sidebar, tabs) nebo **ostatní docs**

---

## 📞 Kontakt pro debugging

Pokud něco nefunguje:

1. **docserver nenaslouchá** → `systemctl --user status docs`
2. **HTML nenalezen** → zkontroluj `ls /home/geo/projects/docs/output/`
3. **JSON chyba** → spusť `python build.py --project ai --check`
4. **Discovery selhalo** → zkontroluj `curl -s http://localhost:8080/api/projects`

---

## 📝 Epilog

Haiku session přinesla:
- Kompletní analýzu workspace architektury
- Vytvoření comprehensive AI dokumentace (ai.json)
- Integrace `/docs/` endpointu do docserver
- TENTO handoff dokument pro znalostní transfer

**Příští model (Sonnet)** by měl zaměřit se na:
1. **Vizuální integraci** — aby "/docs/ai" bylo vidět v UI
2. **Zbývající dokumentace** — dashboard, web-edit, docs samy
3. **Git hook automatizace** — post-commit triggery

---

**Vygenerováno**: Haiku 4.5 @ 2026-02-20 09:30 CET
**Pro**: Sonnet 4.6 a vyšší
**Status**: ✅ Ready to handoff
