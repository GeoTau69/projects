# Fedora Backup Dashboard

Webový dashboard pro správu 3-vrstvého backup systému na Fedoře (Btrfs). Běží jako systemd služba na portu 8090.

## Přístupy

| Síť | URL |
|-----|-----|
| Lokální | http://localhost:8090 |
| LAN | http://192.168.0.101:8090 |
| Tailscale | http://fedora:8090 · http://100.117.55.88:8090 |

## Backup vrstvy

1. **Snapper** – Btrfs snapshoty root disku (`snapper -c root`)
2. **Btrfs send/receive** – synchronizace snapshotů na backup disk `/mnt/fedora-backups/system-snapshots`
3. **Borg** – šifrované zálohy `/home/geo` do `/mnt/fedora-backups/borg-repo`

## Tech stack

- **Backend**: Python 3, FastAPI (APIRouter), Jinja2, uvicorn
- **Frontend**: Vanilla HTML/CSS/JS (dark theme, GitHub-style), žádný framework
- **Systém**: Fedora, Btrfs, systemd timery, sudo pro privilegované operace
- **Jazyk UI/komentářů**: čeština

## Struktura projektu

```
app.py                  – Entry point: app instance, mount routerů, spuštění (~30 ř.)
helpers.py              – Sdílené: CONFIG, log_action(), run_cmd(), run_sudo(), get_borg_env(), templates (~80 ř.)
routes/
  __init__.py           – Prázdný
  snapshots.py          – Snapper endpointy + get_snapper_list() (~130 ř.)
  borg.py               – Borg endpointy + get_borg_archives/info() + tree/files (~190 ř.)
  git.py                – Git endpointy + run_git/get_git_log/status/diff() (~150 ř.)
  system.py             – Dashboard, docs, health, refresh, logs, full-backup, nuclear-delete, sync (~300 ř.)
                           + get_backup_disk_status, get_root_disk_status, get_systemd_timers,
                             get_sync_snapshots, get_dashboard_log, get_health_status
templates/
  dashboard.html        – Hlavní dashboard UI (~1066 řádků, vše inline – CSS+JS+HTML)
  git.html              – Git správa verzí (~290 řádků, inline CSS+JS+HTML)
  docs.html             – Dokumentační stránka s live statusem (~1268 řádků, inline)
static/                 – Statické soubory (zatím prázdný)
logs/dashboard.log      – Aplikační log
export_backup.sh        – Script pro export projektu do ZIP
*.backup-*              – Ruční zálohy souborů (ignorovat)
```

## Architektura modulů

### helpers.py
- `CONFIG` – centrální konfigurace (cesty, porty, borg excludes)
- `templates` – Jinja2Templates instance (sdílená pro všechny routery)
- `log_action()`, `run_cmd()`, `run_sudo()`, `get_borg_env()`

### routes/snapshots.py
- `get_snapper_list()` – datová funkce (importována v system.py)
- Endpointy: `POST /api/snapshot/create|delete|rollback|new-golden`, `GET /api/snapshot/diff/{number}`

### routes/borg.py
- `get_borg_archives()`, `get_borg_info()` – datové funkce (importovány v system.py)
- Endpointy: `POST /api/borg/create|delete|restore`, `GET /api/borg/files|tree`

### routes/git.py
- `run_git()`, `get_git_log()`, `get_git_status()`, `get_git_diff()`
- Endpointy: `GET /git`, `GET /api/git/log|diff`, `POST /api/git/commit|rollback`

### routes/system.py
- Datové funkce: `get_backup_disk_status()`, `get_root_disk_status()`, `get_systemd_timers()`, `get_sync_snapshots()`, `get_dashboard_log()`, `get_health_status()`
- Importuje `get_snapper_list` z routes.snapshots a `get_borg_archives` z routes.borg
- Endpointy: `GET /`, `GET /docs`, `GET /api/health|refresh|logs`, `POST /api/logs/clear|export`, `POST /api/sync/run|full-backup|nuclear-delete`

## Důležité příkazy

```bash
# Spuštění dev serveru
cd /opt/backup-dashboard && python app.py

# Systemd služba
sudo systemctl status backup-dashboard
sudo systemctl restart backup-dashboard

# Logy
journalctl -u backup-dashboard -f
cat /opt/backup-dashboard/logs/dashboard.log
```

## Konvence a pravidla

- **KRITICKÉ: Veškeré soubory MUSÍ být v kódování UTF-8.** V minulosti úpravy logiky rozbily kódování českých znaků — při každé změně ověřit, že soubor zůstává validní UTF-8
- Kód a komentáře psat **česky** (odpovídá existujícímu stylu)
- Backend je rozdělen do modulů podle vrstev (`helpers.py` + `routes/*.py`) — při přidávání endpointů zařadit do správného modulu
- Frontend je inline v šablonách (CSS + JS přímo v HTML) – neextrahovat do souborů
- Backup soubory (`*.backup-*`) neverzovat a nemazat
- Privilegované systémové příkazy vždy přes `run_sudo()`
- Borg příkazy vždy s `env_extra=get_borg_env()`
- Každá akce se loguje přes `log_action()`
- Při změnách v API aktualizovat i odpovídající frontend v dashboard.html
- Port 8090, bind na 0.0.0.0
- Neduplikovat endpointy ani JS funkce — v minulosti se opakovaně stalo, že se kód nalepil vícekrát
- Když potřebuji, aby uživatel spustil příkaz v terminálu: vždy zapsat obsah do souboru (Write tool) a poslat **jednořádkový** příkaz na spuštění (např. `sudo bash /tmp/script.sh`). Nikdy neposílat víceřádkové příkazy — terminál uživatele je neumí správně zpracovat
- Sudoers pravidlo pro backup-dashboard: `/etc/sudoers.d/backup-dashboard` — umožňuje `geo` spouštět `systemctl start|stop|restart|status backup-dashboard` bez hesla. **Nepoužívat `--no-pager` ani jiné flagy** — sudoers kontroluje přesnou shodu příkazu a extra argumenty způsobí odmítnutí

<!-- SYNC:START -->
<!-- aktualizováno: 2026-02-18 20:18 -->

**Živý stav** *(info-sync.py)*

- Služba `backup-dashboard` (system service): 🟢 active
- Port 8090: 🟢 naslouchá
- Poslední commit: `45ac6e7` — Přidány projekty docs, git; síťové adresy (LAN, Tailscale) do dokumentace

<!-- SYNC:END -->
