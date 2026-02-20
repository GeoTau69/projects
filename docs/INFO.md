# Projects Docs — Info

Centrální dokumentační portál pro workspace `~/projects/`.

## Navigace

**Fixní položky** (vždy nahoře v sidebaru):

| Položka | Obsah |
|---------|-------|
| ℹ️ Info | Tato stránka |
| ☑️ Todo | Živý backlog (`todo.md`) — aktualizuj přímo v souboru |
| 📋 Overview | Workspace mapa (`CLAUDE.md`) — projekty, infrastruktura, konvence |

**Projekty** — každý projekt má:
- Barevnou ikonu stavu: 🟢 active · 🟡 wip · ⚪ planned · 📦 archived
- Port badge pokud projekt běží jako service
- 📖 odkaz na HTML dokumentaci (pokud existuje)

## AI dokumentace (📖 ikony)

Projekty s 📖 ikonou mají vygenerovanou HTML dokumentaci. Pipeline:

```
AI (Haiku) generuje docs/data/{projekt}.json
       ↓
build.py renderuje docs/output/{projekt}.html  (Jinja2)
       ↓
Sidebar zobrazí 📖 ikonu, klik otevře v nové záložce
```

Jak vygenerovat dokumentaci pro nový projekt → viz `docs/AI_WORKFLOW.md`.

## HTTP endpointy

| Endpoint | Popis |
|----------|-------|
| `GET /` | HTML shell (SPA) |
| `GET /api/projects` | JSON seznam projektů s live statusem portů |
| `GET /api/md?dir=master` | raw markdown: `~/projects/CLAUDE.md` |
| `GET /api/md?dir=todo` | raw markdown: `~/projects/todo.md` |
| `GET /api/md?dir=info` | raw markdown: `docs/INFO.md` |
| `GET /api/md?dir=X` | raw markdown: `~/projects/X/CLAUDE.md` |
| `GET /docs/{projekt}` | HTML dokumentace z `docs/output/{projekt}.html` |

## Příkazy

```bash
# Systemd user service
systemctl --user status docs
systemctl --user restart docs
journalctl --user -u docs -f

# Manuální spuštění
python3 ~/projects/docs/docserver.py

# Build HTML dokumentace
cd ~/projects/docs
python3 build.py --project {projekt} --force
python3 build.py --check    # validace všech JSON
```

## Technické info

| Atribut | Hodnota |
|---------|---------|
| Port | `8080` |
| Systemd | `docs` (user service) |
| Backend | Python stdlib `http.server` — žádné závislosti |
| Markdown rendering | marked.js (CDN), fallback na plain text offline |
| Discovery | `project.yaml` soubory v přímých podadresářích `~/projects/` |
| HTML docs | `docs/output/{projekt}.html` — generuje `build.py` (Jinja2) |

## Auto-refresh

Tlačítko **AUTO-REFRESH** v hlavičce — obnoví seznam projektů a aktivní stránku každých 30 sekund. Užitečné pro monitoring live statusů portů.

## Soubory

```
docs/
  docserver.py        — SPA server, port 8080
  build.py            — JSON → HTML renderer (Jinja2)
  INFO.md             — tato stránka
  AI_WORKFLOW.md      — průvodce generováním dokumentace pro Haiku
  schema/
    doc_schema.json   — JSON Schema pro validaci
  templates/
    project.html.j2   — Jinja2 šablona
  data/
    {projekt}.json    — AI generuje pouze tyto soubory
  output/             — generované HTML (není verzováno)
```
