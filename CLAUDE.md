# Projektový workspace

> Monorepo pro všechny projekty na Fedoře 43 (Workstation)
> Umístění: `/home/geo/projects/`
> Vlastník: `geo` (uid=1000, skupina wheel)

## Infrastruktura

### Git remoty
- **Gitea** (primární): `http://localhost:3000/geo/projects` — self-hosted, port 3000, systemd služba `gitea`
- **GitHub** (mirror): `https://github.com/GeoTau69/projects` — veřejný mirror
- Push na oba: `git push gitea main && git push github main`
- Gitea credentials uloženy v `~/.git-credentials` (token)
- GitHub autentizace přes SSH klíč `~/.ssh/id_ed25519` + `gh` CLI

### Systém
- **OS**: Fedora 43, Btrfs root, NVMe disk (300G, 6% použito)
- **Python**: 3.14 (systémový)
- **Git**: globální config `geo <jk@kompi.cz>`, default branch `main`

## Architektura monorepa

### Principy
- Každý projekt = jeden adresář v rootu
- **Galvanická izolace**: žádné cross-imports, žádné sdílené runtime závislosti
- Každý projekt musí být self-contained (kopírovatelný jinam bez závislostí na ostatních)
- Dvouúrovňová dokumentace: root CLAUDE.md (auto-generovaný) + projektový CLAUDE.md (manuální)

### Struktura
```
~/projects/                          # Monorepo root
├── CLAUDE.md                        # TENTO SOUBOR — auto-generovaná sekce Projekty + manuální sekce
├── Makefile                         # make docs | make validate | make new-project NAME=x | make list
├── .gitignore
├── _meta/                           # Meta-tooling (není projekt)
│   ├── generate-docs.py             # Generátor sekce Projekty z project.yaml souborů
│   ├── validate-isolation.py        # Kontrola izolace mezi projekty
│   ├── new-project.sh               # Scaffold nového projektu ze šablony
│   └── templates/
│       ├── project.yaml.template
│       └── CLAUDE.md.template
├── backup-dashboard/                # PROJEKT: Backup Dashboard [ACTIVE]
└── system/                          # PROJEKT: System Utilities [PLANNED]
```

### Konvence pro projekty
- Každý projekt MUSÍ mít: `project.yaml` (metadata) + `CLAUDE.md` (detailní instrukce)
- Kód a komentáře psát **česky**
- Soubory MUSÍ být v kódování **UTF-8**
- Backup soubory (`*.backup-*`) neverzovat
- Privilegované příkazy vždy přes `sudo` / `run_sudo()`

### Příkazy
```bash
make docs              # Regeneruje sekci Projekty níže z project.yaml
make validate          # Ověří izolaci všech projektů
make new-project NAME=x  # Vytvoří nový projekt ze šablony
make list              # Vypíše projekty a jejich stav
```

## Projekty

### 🟢 Fedora Backup Dashboard (`backup-dashboard/`)

- **Stav**: active
- **Typ**: web-app | **Jazyk**: python (FastAPI, Jinja2, uvicorn)
- **Port**: 8090 | **Služba**: `backup-dashboard`
- **Popis**: Webové rozhraní pro správu 3-vrstvového backup systému (Snapper + Btrfs sync + Borg)
- **Tagy**: backup, btrfs, snapper, borg, fastapi
- **Migrace**: Přesunuto z `/opt/backup-dashboard` → `~/projects/backup-dashboard` (2026-02-17)
- **Detaily**: viz `backup-dashboard/CLAUDE.md`

### ⚪ System Utilities (`system/`) — PLANNED

- Konfigurace, utility, remote/local mode switch
- Manuály na terminál, tmux, systémové nástroje
- Zatím nevytvořeno

## Historie workspace (2026-02-17)

1. Nainstalována Gitea 1.25.4 jako systemd služba (port 3000, SQLite)
2. Založen GitHub účet GeoTau69, SSH klíč registrován, `gh` CLI nainstalováno
3. Vytvořena monorepo struktura `~/projects/` s _meta toolingem
4. Migrován backup-dashboard z `/opt` — systemd unit aktualizován
5. Push do Gitea + GitHub — oba remoty funkční
