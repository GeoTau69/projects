# Git Integrace

Centrální dokumentace git setupu pro workspace `~/projects/`. Monorepo — jeden git repozitář pro všechny projekty.

## Přístupy (Gitea web UI)

| Síť | URL |
|-----|-----|
| Lokální | http://localhost:3000 |
| LAN | http://192.168.0.101:3000 |
| Tailscale | http://fedora:3000 · http://100.117.55.88:3000 |

## Identita

```
user.name  = geo
user.email = jk@kompi.cz
```

## Remoty

| Remote | URL | Typ |
|--------|-----|-----|
| `gitea` | `http://localhost:3000/geo/projects.git` | primární (lokální Gitea) |
| `github` | `git@github.com:GeoTau69/projects.git` | mirror |

```bash
# Push na oba remoty
git push gitea main && git push github main
```

## Credentials

- **Gitea**: `~/.git-credentials` (HTTP Basic Auth)
- **GitHub**: SSH klíč `~/.ssh/id_ed25519` + `gh` CLI

## Workflow

```bash
git status
git add <soubory>            # nikdy git add -A (může přidat .env, *.backup-*)
git commit -m "zpráva"
git push gitea main && git push github main
```

## Co neverzovat

- `*.backup-*` — ruční zálohy souborů (jsou v `.gitignore`)
- `.env`, credentials soubory
- `__pycache__/`, `*.pyc`

## Větve

- Výchozí větev: `main`
- Feature větve: dle potřeby, merge do `main`

---

## Projekty využívající Git

### backup-dashboard — Web UI pro git správu

`backup-dashboard/routes/git.py` implementuje HTTP endpointy pro git operace přes dashboard UI:

| Endpoint | Popis |
|----------|-------|
| `GET /git` | Git stránka (git.html template) |
| `GET /api/git/log` | Historie commitů |
| `GET /api/git/diff` | Diff konkrétního commitu |
| `GET /api/git/status` | Aktuální status (staged/unstaged) |
| `POST /api/git/commit` | Vytvoření commitu z UI |
| `POST /api/git/rollback` | Rollback na commit |

Web UI běží na [http://localhost:8090/git](http://localhost:8090/git).
Zdrojový kód: `backup-dashboard/routes/git.py`, šablona: `backup-dashboard/templates/git.html`.

### info-sync.py — Git info do CLAUDE.md

`info-sync.py` volá `git log --oneline -1` pro každý projekt a zapisuje hash + zprávu posledního commitu do SYNC bloku slave CLAUDE.md:

```python
# backup-dashboard/CLAUDE.md → SYNC blok:
# - Poslední commit: `593f6ee` — Migrace backup-dashboard z /opt do ~/projects/
```

### web-edit — Editace souborů (bez git integrace)

`web-edit/` umí editovat MD soubory online, ale nemá vlastní git committing — změny je třeba commitovat ručně.

### docs (docserver.py) — Nezávislý na git

`docs/` čte CLAUDE.md soubory přímo z disku, git commit info zobrazuje jen skrze SYNC bloky zapsané `info-sync.py`.

---

## Gitea (lokální instance)

Repozitář: `geo/projects` — viz tabulka Přístupy nahoře.

Správa: přes web UI nebo `gh` CLI (pokud nakonfigurováno pro Gitea)

## GitHub mirror

- Repozitář: `GeoTau69/projects`
- Push: automaticky při `git push github main`
- Autentizace: SSH (`~/.ssh/id_ed25519`)

<!-- SYNC:START -->
<!-- aktualizováno: 2026-02-18 20:18 -->

**Živý stav** *(info-sync.py)*

- Poslední commit: `45ac6e7` — Přidány projekty docs, git; síťové adresy (LAN, Tailscale) do dokumentace

<!-- SYNC:END -->
