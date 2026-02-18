# Projects Dashboard

Živý přehled stavu všech projektů a systémových módů. Čte `~/projects/.systems.json`.

## Přístupy

| Síť | URL |
|-----|-----|
| Lokální | http://localhost:8099 |
| LAN | http://192.168.0.101:8099 |
| Tailscale | http://fedora:8099 · http://100.117.55.88:8099 |

## Tech stack

- **Backend**: Python stdlib `http.server` (žádné závislosti)
- **Frontend**: Inline HTML/CSS (dark theme, monospace), auto-refresh každých 5s
- **Konfigurace**: `~/projects/.systems.json` — seznam sledovaných systémů/módů

## Soubory

```
dashboard.py     — celá aplikace (single-file), port 8099
project.yaml     — metadata projektu
```

## Příkazy

```bash
python3 dashboard.py                    # Spustit manuálně
systemctl --user status projects-dashboard  # Stav systemd služby
systemctl --user restart projects-dashboard
journalctl --user -u projects-dashboard -f  # Logy
```

## Konvence

- Single-file projekt, žádné závislosti mimo stdlib
- HTML šablona inline v `dashboard.py` jako raw string `HTML = r"""..."""`
- Kód česky, UTF-8

<!-- SYNC:START -->
<!-- aktualizováno: 2026-02-18 20:06 -->

**Živý stav** *(info-sync.py)*

- Služba `projects-dashboard` (user service): 🟢 active
- Port 8099: 🟢 naslouchá
- Poslední commit: `f4620c3` — Aktualizace root CLAUDE.md — kompletní stav workspace

<!-- SYNC:END -->
