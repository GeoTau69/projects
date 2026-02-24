# Projects Docs — Info

Centrální dokumentační portál pro workspace `~/projects/`.

## Navigace

**Fixní položky** (vždy nahoře v sidebaru):

| Položka | Obsah |
|---------|-------|
| ℹ️ Info | Tato stránka |
| ☑️ Todo | Živý backlog (`todo.md`) — aktualizuj přímo v souboru |
| 📋 Overview | Workspace mapa (`CLAUDE.md`) — projekty, infrastruktura, konvence |

**Help dialog** — klikni na **?** v hlavičce → zobrazí obsah této stránky (INFO.md) přímo v dialogu.

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

## 🧹 Maintenance — Údržba metadat

### Proč to potřebujeme

`MODEL.md` a `todo.md` jsou živé dokumenty s chronologickou historií (SESSION LOG, backlog). Bez údržby by rostly nekonečně a AI by načítala zbytečně staré záznamy. **Rolling window** znamená: starší záznamy se archivují, ale zůstávají v gitu.

### Portál — `/maintenance` stránka

Klikni na **🧹 Maintain** (dole v sidebaru) → otevře se maintenance panel s formulářem:

```
Cíl:                all / model / todo
Zachovat sessions:  [5] — posledních N záznamů v SESSION LOG
Nebo dní:           [  ] — záznamy mladší než N dní (přebije "sessions")

[👁 Preview]  → zobrazí dry-run (co by se archivovalo)
[⚡ Spustit]  → spustí sanitaci (aktivní až po preview)
```

**Workflow:**
1. Vyplň parametry
2. Klikni **Preview** → vidíš seznam co se archivuje
3. Pokud je OK, klikni **Spustit**
4. Archivované soubory se vytvoří v `archive/` s timestamp
5. Git změny si **commitni ručně** po kontrole

### CLI — příkazový řádek (pokročilé)

```bash
# Dry-run: zjisti co by se archivovalo
python3 tools/sanitize.py --target all --keep 5 --dry-run

# Spustit sanitaci (bez commitu)
python3 tools/sanitize.py --target all --keep 5

# Jen MODEL.md SESSION LOG — zachovat 10 záznamů
python3 tools/sanitize.py --target model --keep 10

# Jen záznamy mladší než 30 dní
python3 tools/sanitize.py --target model --days 30

# Automaticky commitnout po sanitaci
python3 tools/sanitize.py --target all --keep 5 --commit

# Výstup jako JSON (pro skriptování)
python3 tools/sanitize.py --target all --keep 5 --json
```

### Co se archivuje

**MODEL.md — SESSION LOG:**
- Nejnovější session záznamy si zůstávají v hlavním souboru
- Starší (`### YYYY-MM-DD ...`) se přesunou do `archive/sessions-YYYY-MM.md`
- Archivní soubory jsou měsíční (leden 2026 → `sessions-2026-01.md`, únor → `sessions-2026-02.md`)

**todo.md — HOTOVO backlog:**
- Backlog položky s `**Status: HOTOVO**` se archivují
- Přesunou se do `archive/todo-done-YYYY-MM.md`
- Aktivní ([TODO] DOKUMENTACE) zůstávají v `todo.md`

**Archive struktura:**
```
archive/
  sessions-2026-02.md        — staré SESSION LOG záznamy (ChatGPT messages)
  todo-done-2026-02.md       — hotové backlog položky (uzavřené features)
  .gitkeep                   — archiv je verzovaný v gitu
```

Archiv najdeš v gitu → `git log archive/sessions-*` vidíš historii.

### Příklady

**Scénář 1: Pravidelná údržba (měsíčně)**
```bash
# Podívej se co se archivuje
python3 tools/sanitize.py --target all --keep 5 --dry-run

# Vypadá OK → spustit
python3 tools/sanitize.py --target all --keep 5 --commit
# Auto-vytvoří git commit: "chore: sanitize — model: -2 položek, ..."
```

**Scénář 2: Archivovat jen stará data (3+ měsíce)**
```bash
# Zachování záznamů mladších než 90 dní
python3 tools/sanitize.py --target model --days 90
```

**Scénář 3: Jen todo — archivovat hotové projekty**
```bash
python3 tools/sanitize.py --target todo
# Všechny HOTOVO backlog položky jdou do archive/
```

### FAQ — Údržba

**Ztratím data archivací?**
Ne. Archivované soubory zůstávají v gitu. `git log -p archive/sessions-*` vidíš vše.

**Chci zachovat víc/méně záznamů.**
Změň `--keep N`. Default je 10. Můžeš mít klidně `--keep 20` pokud chceš delší historii v souboru.

**Čím se liší `--keep` vs `--days`?**
- `--keep 5` = posledních 5 session záznamů (bez ohledu na datum)
- `--days 30` = záznamy z posledních 30 dní (bez ohledu na počet)
- Pokud zadáš obě, `--days` má přednost

**Mohu archivovat manuálně?**
Ano, přesunout část textu do `archive/{prefix}-YYYY-MM.md` a commitnout. Script jen to dělá automaticky.

**Co když mám chybu nebo se chci vrátit?**
Git log si pamatuje všechno. `git revert` poslední commit nebo vrátit změny ručně.

## Soubory

```
docs/
  docserver.py        — SPA server, port 8080
  build.py            — JSON → HTML renderer (Jinja2)
  INFO.md             — tato stránka
  AI_WORKFLOW.md      — průvodce generováním dokumentace pro Haiku
  static/
    css/              — theme.css, layout.css, md-content.css, build.css
    js/               — md-viewer.js, fedoraos-viewer.js, sidebar-scroll.js
  templates/
    shell-docserver.html  — HTML šablona pro :8080
    shell-fedoraos.html   — HTML šablona pro :8081
    maintenance.html      — maintenance panel
    project.html.j2       — Jinja2 šablona pro build.py
  schema/
    doc_schema.json   — JSON Schema pro validaci
  data/
    {projekt}.json    — AI generuje pouze tyto soubory
  output/             — generované HTML (není verzováno)
```
