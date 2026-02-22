# AI Dev Agent Stack — Vývojový backlog

> Aktualizováno: 2026-02-19
> Účel: Živý backlog vývoje workspace. Popisuje aktuální stav a plánované kroky.

---

## Aktuální stav workspace

### Infrastruktura (funkční)

| Projekt | Port | Systemd | Stav |
|---------|------|---------|------|
| `backup-dashboard/` | 8090 | `backup-dashboard` (system) | 🟢 active |
| `dashboard/` | 8099 | `projects-dashboard` (user) | 🟢 active |
| `docs/` | 8080 | `docs` (user) | 🟢 active |
| `web-edit/` | 8765 | `mdserver` (user) | 🟢 active |
| Gitea | 3000 | — | 🟢 active |

### Co je hotové

- Hierarchický systém CLAUDE.md: master (`/projects/CLAUDE.md`) + slave per projekt
- YAML metadata (`project.yaml`) pro každý projekt
- `_meta/info-sync.py` — synchronizuje SYNC bloky do slave CLAUDE.md (git info, live status)
- `_meta/generate-docs.py` — regeneruje tabulku projektů v master CLAUDE.md
- `Makefile` — příkazy `make docs`, `make validate`, `make list`, `make new-project`
- Gitea (lokální primární) + GitHub (mirror)
- `backup-dashboard` má git UI na `:8090/git` pro commit/rollback z prohlížeče
- `.systems.json` — registr všech sledovaných služeb

### Co zatím chybí

- AI se podílí na generování HTML dokumentace = zbytečné plýtvání tokeny
- Žádné sledování spotřeby tokenů / nákladů
- Žádná cache pro opakované identické dotazy
- Žádné sémantické vyhledávání přes kód
- Žádné automatické přepínání mezi lokálním LLM a Claude API

---

## BACKLOG — prioritní pořadí

---

### [1] DOKUMENTACE — nová architektura (AI generuje minimum)
**Priorita: NEJVYŠŠÍ**
**Status: TODO**

**Princip:** AI přestane generovat HTML. Generuje pouze datový JSON se strukturou a obsahem. Python/Jinja2 renderuje HTML bez účasti AI. Tím se dramaticky sníží spotřeba tokenů při každém update dokumentace.

#### Fáze A — Postavit framework

Nový podprojekt rozšiřující `docs/`:

```
docs/
  templates/          # Jinja2 HTML šablony (AI se nedotýká)
    project.html.j2   # šablona pro jeden projekt
    index.html.j2     # přehledová stránka
  schema/
    doc_schema.json   # JSON Schema pro validaci AI výstupu
  data/
    {projekt}.json    # AI generuje POUZE tento soubor
  build.py            # Python: JSON → HTML, žádné AI
```

**CLI rozhraní `build.py`:**
```bash
python build.py                                      # vše
python build.py --project backup-dashboard           # jen jeden projekt
python build.py --project backup-dashboard --section borg  # jen sekci
```

Detekce změn přes MD5 hash jednotlivých JSON sekcí — přeskakovat nezměněné části.

**JSON struktura (co AI generuje):**
```json
{
  "project": "backup-dashboard",
  "version": "1.0.0",
  "updated": "2026-02-19",
  "modules": [
    {
      "id": "borg",
      "name": "BorgBackup",
      "purpose": "Šifrované zálohy /home/geo",
      "status": "stable",
      "methods": [],
      "dependencies": ["helpers.get_borg_env"],
      "notes": ""
    }
  ]
}
```

**Pravidla (co patří / nepatří do JSON):**
- Patří: veřejné moduly/třídy s `purpose`+`status`, veřejné metody, závislosti, known issues
- Nepatří: interní impl. detaily, komentáře z kódu, historické poznámky (→ git log)

**Kroky:**
- [x] Navrhnout `doc_schema.json`
- [x] Napsat Jinja2 šablonu `project.html.j2`
- [x] Napsat `build.py` s CLI a hash-based detekcí změn
- [x] Ověřit funkčnost na testovacím projektu (`data/_test.json`)
- [ ] Aktualizovat pravidla do slave CLAUDE.md každého projektu (fáze B)

**Technická poznámka:** Klíč pro seznam položek v JSON blocích je `entries` (nikoli `items` — `items` je rezervované jméno dict metody, Jinja2 getattr ho zachytí dříve než dict klíč).

#### Fáze B — Migrace stávající dokumentace

Po otestování frameworku (fáze A) migrovat existující projekty:

| Projekt | Co migrovat | Poznámka |
|---------|-------------|----------|
| `backup-dashboard/` | `templates/docs.html` | Největší soubor, 1268 řádků inline HTML — priorita |
| `docs/` | Samotný docserver | Rozšíření o nové endpointy pro JSON data |
| `dashboard/` | Menší rozsah | |
| `web-edit/` | Menší rozsah | |

Postup pro každý projekt:

**backup-dashboard** ✅
- [x] AI vygenerovala `docs/data/backup-dashboard.json` ze stávající dokumentace
- [x] JSON prošel validací (`--check`)
- [x] `build.py --output backup-dashboard/templates/docs.html` — 36 kB, HTTP 200
- [x] Live status widget (`/api/health`), 32 karet, 24 sidebar odkazů — ověřeno

**Zbývající projekty** (menší rozsah, nižší priorita):
- [ ] `docs/data/dashboard.json` → `dashboard/` (žádná inline docs HTML)
- [ ] `docs/data/web-edit.json` → `web-edit/` (žádná inline docs HTML)
- [ ] `docs/data/docs.json` → samotný docs server

---

---

---

---

---

## Cílová architektura

```
Git commit
    ↓
[Git Hook: post-commit]
    ├── info-sync.py           — SYNC bloky v CLAUDE.md (AI: lokální model)
    ├── generate-docs.py       — tabulka projektů v master CLAUDE.md (bez AI)
    ├── docs/data/{projekt}.json — AI aktualizuje jen změněné moduly (lokální model)
    ├── build.py               — JSON → HTML (Jinja2, BEZ AI)
    ├── chroma_indexer.py      — re-indexace změněných souborů
    └── git push gitea main && git push github main

Každé AI volání → token_tracker.py → SQLite (~/.ai-agent/tokens.db)
                                    → cache lookup před voláním API
```

---

## Hotové milníky

- [x] Hierarchický systém CLAUDE.md (master + slave)
- [x] info-sync.py — SYNC bloky s živým stavem
- [x] generate-docs.py — tabulka projektů v master CLAUDE.md
- [x] dashboard (port 8099) — live přehled služeb
- [x] docs (port 8080) — centrální dokumentační web
- [x] backup-dashboard (port 8090) — správa záloh + git UI
- [x] web-edit (port 8765) — online MD editor s WebSocket
- [x] Gitea lokální instance + GitHub mirror

---

## Poznámky

- Stávající HTML v `backup-dashboard/templates/` migrovat v rámci [1B], ne rušit předčasně
- Python 3.14 (Fedora 43) — stdlib preferred, závislosti jen kde nutné
- Ollama je nainstalována a funkční
- Veškerý kód a komentáře: česky, UTF-8
