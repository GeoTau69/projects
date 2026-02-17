"""
Sdílené pomocné funkce a konfigurace pro Backup Dashboard
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

# === KONFIGURACE ===
CONFIG = {
    "snapper_config": "root",
    "borg_repo": "/mnt/fedora-backups/borg-repo",
    "borg_passphrase_file": "/home/geo/.borg-passphrase",
    "backup_mount": "/mnt/fedora-backups",
    "snapshot_sync_dir": "/mnt/fedora-backups/system-snapshots",
    "borg_source": "/home/geo",
    "borg_excludes": [
        "*.cache*",
        "*.Cache*",
        ".local/share/Trash",
        ".thumbnails",
        "__pycache__",
        ".steam",
        "snap",
        "thinclient_drives",
        ".gvfs",
        ".dbus",
        "*.lock",
    ],
    "log_file": str(Path(__file__).parent / "logs" / "dashboard.log"),
    "host": "0.0.0.0",
    "port": 8090,
}

# === TEMPLATES ===
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# === LOGGING ===
def log_action(action: str, detail: str = "", success: bool = True):
    """Zapíše akci do logu"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "OK" if success else "FAIL"
    line = f"[{timestamp}] [{status}] {action}: {detail}\n"
    log_path = Path(CONFIG["log_file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(line)

# === POMOCNÉ FUNKCE ===
def run_cmd(cmd: list[str], timeout: int = 120, env_extra: dict = None) -> dict:
    """Spustí příkaz a vrátí výsledek"""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            encoding="utf-8",
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Timeout", "success": False}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e), "success": False}

def run_sudo(cmd: list[str], timeout: int = 120) -> dict:
    """Spustí příkaz přes sudo"""
    return run_cmd(["sudo"] + cmd, timeout=timeout)

def get_borg_env() -> dict:
    """Vrátí environment pro Borg"""
    return {"BORG_PASSCOMMAND": f"cat {CONFIG['borg_passphrase_file']}"}
