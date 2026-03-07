# Projects Documentation Server

Centrální dokumentační web pro `~/projects/`. Single-page app zobrazující strukturu projektů a obsah CLAUDE.md souborů.

## Přístupy

| Síť | URL |
|-----|-----|
| Lokální | http://localhost:8080 |
| LAN | http://192.168.0.101:8080 |
| Tailscale | http://fedora:8080 · http://100.117.55.88:8080 |

## Tech stack

- **Backend**: Python stdlib `http.server` (žádné závislosti)
- **Frontend**: HTML šablony (`templates/`) + sdílený CSS/JS (`static/`), marked.js CDN pro MD rendering
- **Discovery**: Stejná logika jako `info-sync.py` — prochází `project.yaml` soubory

## Soubory

```
docserver.py          — SPA web (CLAUDE.md viewer), port 8080
build.py              — JSON → HTML renderer (Jinja2, bez AI), CLI tool
project.yaml          — metadata projektu
CLAUDE.md             — tato dokumentace

static/
  css/
    theme.css         — barvy, fonty, proměnné (sdílený s fedoraOS :8081)
    layout.css        — sidebar + hlavní panel layout
    md-content.css    — styly pro renderovaný markdown
    build.css         — styly pro build.py generované HTML
  js/
    md-viewer.js      — SPA logika docserveru (sidebar, markdown loading)
    fedoraos-viewer.js — SPA logika fedoraOS serveru
    sidebar-scroll.js — auto-scroll sidebar na aktivní položku

templates/
  shell-docserver.html  — HTML šablona pro docserver (:8080)
  shell-fedoraos.html   — HTML šablona pro fedoraOS (:8081)
  maintenance.html      — maintenance panel (sanitace)
  project.html.j2       — Jinja2 šablona pro build.py generované HTML

schema/
  doc_schema.json     — JSON Schema pro validaci AI-generovaných dat

data/
  {projekt}.json      — AI generuje POUZE tyto soubory
  _test.json          — testovací/ukázkový soubor

output/               — generované HTML soubory (build.py output, není verzováno)
.build-state.json     — hash cache pro detekci změn (není verzováno)
```

## HTTP endpointy

```
GET /                    → HTML shell (SPA)
GET /static/{cesta}      → sdílené CSS/JS soubory (per-project override podporován)
GET /api/projects        → JSON: seznam projektů s live statusem portů
GET /api/md?dir=master   → raw markdown: ~/projects/CLAUDE.md
GET /api/md?dir=info     → raw markdown: docs/INFO.md
GET /api/md?dir=todo     → raw markdown: ~/projects/todo.md
GET /api/md?dir=X        → raw markdown: ~/projects/X/CLAUDE.md
GET /docs/{projekt}      → HTML dokumentace z output/{projekt}.html
GET /maintenance         → maintenance panel (sanitace MODEL.md, todo.md)
POST /api/sanitize       → spustí sanitaci (JSON body: target, keep, days)
GET /api/sanitize?...    → dry-run sanitace (query params)
```

## Příkazy

```bash
# Manuální spuštění (vývojový mód)
python3 ~/projects/docs/docserver.py

# Systemd user service
systemctl --user status docs
systemctl --user start docs
systemctl --user restart docs
journalctl --user -u docs -f
```

## Architektura

- `load_projects()` — discovery přes `project.yaml`, minimalistický YAML parser (bez yaml modulu)
- `check_port()` — live status portu pro sidebar ikony
- `api_projects()` → JSON s projekty + live statusem
- `api_md(dir)` → raw MD text (ochrana path traversal: jen přímé podadresáře ROOT)
- `serve_static(path)` → statické soubory s per-project override (projekt/static/ → docs/static/)
- `api_sanitize()` → spouští `tools/sanitize.py` jako subprocess
- `DocsHandler` — routing: `/`, `/static/*`, `/api/projects`, `/api/md`, `/docs/*`, `/maintenance`, `/api/sanitize`

## Bezpečnost

- Path traversal: `candidate.resolve().parent == ROOT.resolve()` — odmítne `../../etc/passwd`
- Žádné subprocess volání, žádné privilegované operace

## AI workflow

Před generováním dokumentace přečti: `docs/AI_WORKFLOW.md` — postup, trap list, checklist.

## build.py — JSON → HTML pipeline

AI generuje `data/{projekt}.json` → `build.py` renderuje HTML (žádné AI).

```bash
python3 build.py                              # všechny projekty
python3 build.py --project backup-dashboard   # jen jeden projekt
python3 build.py --section cli-snapper        # hash detekce jen pro sekci (s --project)
python3 build.py --check                      # jen validace JSON schématu
python3 build.py --force                      # ignoruj hash cache
python3 build.py --output /cesta/soubor.html  # vlastní výstup (pro migraci)
```

**Klíčové pravidlo pro AI:** Klíč pro seznam položek v blocích je `entries` (nikoli `items` — `items` je rezervované jméno Pythonu a způsobuje chybu v Jinja2).

**Závislosti:** `jinja2` (povinná), `jsonschema` (volitelná, pro `--check`)

## Sdílený theme s fedoraOS (:8081)

Oba servery (docserver :8080 a fedoraOS serve.py :8081) sdílejí:
- **CSS/JS** z `docs/static/` — identický vizuální styl
- **HTML šablony** z `docs/templates/` — shell-docserver.html a shell-fedoraos.html
- **Per-project override** — server hledá static nejdřív v `{projekt}/static/`, pak fallback na `docs/static/`

## Konvence

- `docserver.py` — single-file, žádné závislosti mimo stdlib
- `build.py` — Jinja2 + volitelně jsonschema
- HTML šablony v `templates/`, CSS/JS v `static/` — **žádný inline HTML/CSS/JS** v Python souborech
- marked.js načten z CDN — fallback na plain text pokud offline
- Kód česky, UTF-8

<!-- SYNC:START -->
<!-- aktualizováno: 2026-03-07 12:22 -->

**Živý stav** *(info-sync.py)*

- Port 8080: 🟢 naslouchá
- Poslední commit: `4613be2` — fedoraOS: Opus review OK, smazán NoMachine z remote tabulky

<!-- SYNC:END -->
