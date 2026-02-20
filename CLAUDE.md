# Workspace `/home/geo/projects/`

> Monorepo, Fedora 43 · owner: `geo` · Gitea + GitHub

## Infrastruktura

- **Git remoty**: Gitea `localhost:3000/geo/projects` (primární) + GitHub mirror
  - Push: `git push gitea main && git push github main`
  - Gitea credentials: `~/.git-credentials` · GitHub: SSH `~/.ssh/id_ed25519` + `gh` CLI
- **Systém**: Fedora 43, Btrfs, Python 3.14
- **Git identity**: `geo <jk@kompi.cz>`, default branch `main`

## Síťové adresy

Fedora server: LAN `192.168.0.101` · Tailscale `fedora` / `100.117.55.88`

| Služba | Lokální | LAN | Tailscale |
|--------|---------|-----|-----------|
| Gitea | :3000 | 192.168.0.101:3000 | fedora:3000 |
| backup-dashboard | :8090 | 192.168.0.101:8090 | fedora:8090 |
| dashboard | :8099 | 192.168.0.101:8099 | fedora:8099 |
| docs | :8080 | 192.168.0.101:8080 | fedora:8080 |
| web-edit | :8765 | 192.168.0.101:8765 | fedora:8765 · [funnel](https://fedora.tail41712d.ts.net/) |

## Konvence

- Kód/komentáře: **čeština** · kódování: **UTF-8**
- Každý projekt: self-contained, žádné cross-imports mezi projekty
- Každý projekt má: `project.yaml` (metadata) + `CLAUDE.md` (kontext)
- Backup soubory (`*.backup-*`) neverzovat · privilegované příkazy přes `sudo`

## Kontextové soubory

- `MODEL.md` — AI-to-AI handoff: stav, architektura, session log
- `todo.md` — centrální backlog

## Příkazy workspace

```bash
make docs                # Regeneruje tabulku projektů v tomto souboru
make validate            # Ověří izolaci projektů
make new-project NAME=x  # Nový projekt ze šablony
make list                # Rychlý výpis projektů
```

## Projekty — navigator

> **Workflow**: Tento soubor slouží jako mapa. Před prací na projektu X přečti `X/CLAUDE.md` pro plný kontext.
> `make docs` aktualizuje tabulku níže z `project.yaml` souborů (statické sekce výše jsou zachovány).

<!-- PROJEKTY:START -->
<!-- generováno: 2026-02-19 21:40 -->

| Projekt | Status | Tech | Port | Popis | Detail |
|---------|--------|------|------|-------|--------|
| 🟢 `ai/` | active | ? | None | Sada nástrojů pro optimalizaci práce s AI v rámci wo... | `ai/CLAUDE.md` |
| 🟢 `backup-dashboard/` | active | python | 8090 | Webové rozhraní pro správu 3-vrstvového backup systé... | `backup-dashboard/CLAUDE.md` |
| 🟢 `dashboard/` | active | python | 8099 | Živý přehled stavu všech projektů, služeb a systémov... | `dashboard/CLAUDE.md` |
| 🟢 `docs/` | active | python | 8080 | Centrální dokumentační web — navigator přes projekty... | `docs/CLAUDE.md` |
| 🟢 `git/` | active | markdown/docs | – | Centrální dokumentace git setupu, workflow a integra... | `git/CLAUDE.md` |
| 🟢 `web-edit/` | active | python | 8765 | Online Markdown editor pro IC dokumentaci s real-tim... | `web-edit/CLAUDE.md` |

<!-- PROJEKTY:END -->
