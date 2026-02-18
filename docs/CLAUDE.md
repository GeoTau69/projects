# Projects Documentation Server

Centrální dokumentační web pro `~/projects/`. Single-page app zobrazující strukturu projektů a obsah CLAUDE.md souborů.

## Přístupy

| Síť | URL |
|-----|-----|
| Lokální | http://localhost:8080 |
| LAN | http://192.168.0.101:8080 |
| Tailscale | http://fedora:8080 · http://100.117.55.88:8080 |

## Tech stack

- **Backend**: Python stdlib `http.server` (žádné závislosti, jako `dashboard.py`)
- **Frontend**: Inline HTML/CSS/JS (dark theme, monospace), marked.js CDN pro MD rendering
- **Discovery**: Stejná logika jako `info-sync.py` — prochází `project.yaml` soubory

## Soubory

```
docserver.py     — celá aplikace (single-file), port 8080
project.yaml     — metadata projektu
CLAUDE.md        — tato dokumentace
```

## HTTP endpointy

```
GET /                    → HTML shell (SPA)
GET /api/projects        → JSON: seznam projektů s live statusem portů
GET /api/md?dir=master   → raw markdown: ~/projects/CLAUDE.md
GET /api/md?dir=X        → raw markdown: ~/projects/X/CLAUDE.md
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
- `DocsHandler` — routing: `/`, `/api/projects`, `/api/md`

## Bezpečnost

- Path traversal: `candidate.resolve().parent == ROOT.resolve()` — odmítne `../../etc/passwd`
- Žádné subprocess volání, žádné privilegované operace

## Konvence

- Single-file projekt, žádné závislosti mimo stdlib
- HTML/CSS/JS inline v `docserver.py` jako raw string
- marked.js načten z CDN — fallback na plain text pokud offline
- Kód česky, UTF-8

<!-- SYNC:START -->
<!-- aktualizováno: 2026-02-18 20:06 -->

**Živý stav** *(info-sync.py)*

- Služba `docs` (user service): 🟢 active
- Port 8080: 🟢 naslouchá
- Poslední commit: `f4620c3` — Aktualizace root CLAUDE.md — kompletní stav workspace

<!-- SYNC:END -->
