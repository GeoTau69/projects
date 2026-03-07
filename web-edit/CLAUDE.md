# Web-Edit — Micro MD Collaborative Editor

Online Markdown editor pro IC dokumentaci s real-time multi-user editací přes WebSocket.

## Přístupy

| Síť | URL |
|-----|-----|
| Lokální | http://localhost:8765 |
| LAN | http://192.168.0.101:8765 |
| Tailscale | http://fedora:8765 · http://100.117.55.88:8765 |
| Tailscale Funnel | https://fedora.tail41712d.ts.net/ |

## Tech stack

- **Backend**: Python `aiohttp` + WebSocket
- **Frontend**: Inline HTML/CSS/JS (dark theme), live preview
- **Data**: `/home/geo/Shared/IC` — Markdown soubory (adresář mimo repozitář)
- **Přístup**: viz tabulka níže

## Soubory

```
mdserver.py      — celá aplikace (single-file), port 8765
project.yaml     — metadata projektu
```

## Příkazy

```bash
python3 web-edit/mdserver.py            # Spustit manuálně (výchozí: /home/geo/Shared/IC, port 8765)
python3 web-edit/mdserver.py /cesta 9000  # Vlastní adresář a port
systemctl --user status mdserver        # Stav systemd služby
systemctl --user restart mdserver
journalctl --user -u mdserver -f        # Logy
```

## Architektura

- Více uživatelů může editovat stejný `.md` soubor najednou (WebSocket `rooms`)
- Zálohy editovaných souborů do `/home/geo/Shared/IC/tmp/`
- Vyloučené adresáře ze souborového listingu: `code`, `tmp`, `verze`, `.claude`

## Konvence

- Single-file projekt
- `aiohttp` je jediná závislost (`pip install aiohttp`)
- Kód česky, UTF-8

<!-- SYNC:START -->
<!-- aktualizováno: 2026-03-07 12:22 -->

**Živý stav** *(info-sync.py)*

- Služba `mdserver` (user service): 🟢 active
- Port 8765: 🟢 naslouchá
- Poslední commit: `684ae8a` — Sync: aktualizace SYNC bloků a tabulky projektů (info-sync.py)

<!-- SYNC:END -->
