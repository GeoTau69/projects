#!/usr/bin/env python3
"""
Fedora Backup Dashboard
Webové rozhraní pro správu 3-vrstvého backup systému
- Vrstva 1: Snapper (Btrfs snapshoty)
- Vrstva 2: Btrfs send/receive (sync na backup disk)
- Vrstva 3: Borg (šifrované home zálohy)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from helpers import CONFIG, log_action
from routes import snapshots, borg, git, system

# === APLIKACE ===
app = FastAPI(title="Fedora Backup Dashboard", docs_url=None, redoc_url=None, openapi_url=None)

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# === ROUTERY ===
app.include_router(snapshots.router)
app.include_router(borg.router)
app.include_router(git.router)
app.include_router(system.router)

# === SPUŠTĚNÍ ===
if __name__ == "__main__":
    import uvicorn
    log_action("Dashboard spuštěn", f"Port {CONFIG['port']}")
    uvicorn.run(app, host=CONFIG["host"], port=CONFIG["port"])
