"""
Borg backup endpointy a datové funkce
"""

import json
import os
import re
import subprocess
from datetime import datetime

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from helpers import CONFIG, run_cmd, log_action, get_borg_env

router = APIRouter()

# === DATOVÉ FUNKCE ===

def get_borg_archives() -> list[dict]:
    """Seznam Borg archivů"""
    result = run_cmd(
        ["borg", "list", "--format", "{archive}{TAB}{time}{TAB}{comment}{NL}", CONFIG["borg_repo"]],
        timeout=30,
        env_extra=get_borg_env(),
    )
    if not result["success"]:
        return []

    archives = []
    for line in result["stdout"].split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        archives.append({
            "name": parts[0] if len(parts) > 0 else "?",
            "time": parts[1] if len(parts) > 1 else "?",
            "comment": parts[2] if len(parts) > 2 else "",
        })
    return list(reversed(archives))  # Nejnovější první

def get_borg_info() -> dict:
    """Info o Borg repu"""
    result = run_cmd(
        ["borg", "info", "--json", CONFIG["borg_repo"]],
        timeout=30,
        env_extra=get_borg_env(),
    )
    if result["success"]:
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {}
    return {}

# === ENDPOINTY ===

@router.post("/api/borg/create")
async def create_borg_backup(comment: str = Form("Manual backup from dashboard")):
    """Spustí Borg backup"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # Slug z komentáře: max 50 znaků, pouze bezpečné znaky
    slug = re.sub(r'[^a-zA-Z0-9_-]', '-', comment.strip())
    slug = re.sub(r'-+', '-', slug).strip('-')[:50]
    archive_name = f"{slug}-{timestamp}" if slug else f"manual-{timestamp}"

    cmd = [
        "borg", "create",
        "--verbose", "--stats",
        "--compression", "zstd",
        "--one-file-system",
        "--exclude-caches",
        "--exclude-if-present", ".nobackup",
        "--exclude", "*/thinclient_drives",
        "--exclude", "*/.cache",
        "--exclude", "*/.Cache",
        "--exclude", "*/Cache",
        "--exclude", "*/.thumbnails",
        "--exclude", "*/__pycache__",
        "--exclude", "*/.steam",
        "--exclude", "*/snap",
        "--exclude", "*/.gvfs",
        "--exclude", "*/.dbus",
        "--exclude", "*/.local/share/Trash",
        "--exclude", "*.lock",
        "--comment", comment,
        f"{CONFIG['borg_repo']}::{archive_name}",
        CONFIG["borg_source"],
    ]

    result = run_cmd(cmd, timeout=3600, env_extra=get_borg_env())
    # Borg vrací 0=ok, 1=warning (ale backup prošel), 2=error
    if result["returncode"] in (0, 1):
        msg = f"Archiv {archive_name} vytvořen"
        if result["returncode"] == 1:
            msg += " (s varováními)"
        log_action("Borg backup vytvořen", f"{archive_name}: {comment}")
        return JSONResponse({"success": True, "message": msg})
    else:
        log_action("Borg backup SELHAL", result["stderr"], success=False)
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)

@router.post("/api/borg/delete/{archive_name}")
async def delete_borg_archive(archive_name: str):
    """Smaže Borg archiv"""
    result = run_cmd(
        ["borg", "delete", f"{CONFIG['borg_repo']}::{archive_name}"],
        timeout=300,
        env_extra=get_borg_env(),
    )
    if result["success"]:
        log_action("Borg archiv smazán", archive_name)
        return JSONResponse({"success": True, "message": f"Archiv {archive_name} smazán"})
    else:
        log_action("Smazání Borg archivu SELHALO", f"{archive_name}: {result['stderr']}", success=False)
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)

@router.get("/api/borg/files/{archive_name}")
async def borg_list_files(archive_name: str, path: str = ""):
    """Zobrazí soubory v Borg archivu"""
    cmd = ["borg", "list", "--format", "{mode}{TAB}{size}{TAB}{path}{NL}",
           f"{CONFIG['borg_repo']}::{archive_name}"]
    if path:
        cmd.extend(["--pattern", f"+ {path}/**"])

    result = run_cmd(cmd, timeout=60, env_extra=get_borg_env())
    if result["success"]:
        files = []
        for line in result["stdout"].split("\n")[:200]:  # Max 200 řádek
            parts = line.split("\t")
            if len(parts) >= 3:
                files.append({"mode": parts[0], "size": parts[1], "path": parts[2]})
        return JSONResponse({"success": True, "files": files})
    else:
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)

@router.post("/api/borg/restore")
async def borg_restore(
    archive_name: str = Form(...),
    path: str = Form(""),
    target: str = Form("/tmp/borg-restore"),
    restore_mode: str = Form("target"),  # "target" = do složky, "original" = na původní místo
):
    """Obnoví soubory z Borg archivu"""
    log_action("Borg restore ZAHÁJEN", f"archiv={archive_name} path={path or 'VŠE'} mode={restore_mode} target={target}")

    if restore_mode == "original":
        target = "/"

    os.makedirs(target, exist_ok=True)

    cmd = ["borg", "extract", f"{CONFIG['borg_repo']}::{archive_name}"]
    if path:
        cmd.append(path)

    try:
        env = os.environ.copy()
        env.update(get_borg_env())
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, env=env, cwd=target)
        if proc.returncode == 0:
            msg = f"Obnoveno do {target}"
            if path:
                msg += f" (cesta: {path})"
            log_action("Borg restore DOKONČEN", f"{archive_name}:{path or 'VŠE'} → {target}")
            return JSONResponse({"success": True, "message": msg, "target": target})
        else:
            err = proc.stderr[:500]
            log_action("Borg restore SELHAL", f"{archive_name}: {err}", success=False)
            return JSONResponse({"success": False, "message": err}, status_code=500)
    except subprocess.TimeoutExpired:
        log_action("Borg restore TIMEOUT", f"{archive_name}: překročen limit 3600s", success=False)
        return JSONResponse({"success": False, "message": "Restore překročil časový limit (60 min)"}, status_code=500)
    except Exception as e:
        log_action("Borg restore CHYBA", f"{archive_name}: {str(e)}", success=False)
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)

@router.get("/api/borg/tree/{archive_name}")
async def borg_tree(archive_name: str, prefix: str = ""):
    """Vrátí adresářovou strukturu Borg archivu pro browse"""
    cmd = ["borg", "list", "--format", "{type}{TAB}{size}{TAB}{path}{NL}",
           f"{CONFIG['borg_repo']}::{archive_name}"]

    result = run_cmd(cmd, timeout=60, env_extra=get_borg_env())
    if not result["success"]:
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)

    # Filtrujeme podle prefixu a zobrazíme jen jednu úroveň
    items = []
    seen_dirs = set()
    prefix_depth = len(prefix.rstrip("/").split("/")) if prefix else 0

    for line in result["stdout"].split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ftype, size, path = parts[0], parts[1], parts[2]

        if prefix and not path.startswith(prefix):
            continue

        # Relativní cesta
        rel = path[len(prefix):].lstrip("/") if prefix else path
        segments = rel.split("/")

        if len(segments) == 1 and segments[0]:
            items.append({"type": ftype, "size": size, "name": segments[0], "path": path})
        elif len(segments) > 1 and segments[0] not in seen_dirs:
            seen_dirs.add(segments[0])
            items.append({"type": "d", "size": "-", "name": segments[0] + "/", "path": prefix + segments[0] + "/" if prefix else segments[0] + "/"})

    # Řadíme - adresáře první
    items.sort(key=lambda x: (0 if x["type"] == "d" else 1, x["name"]))

    return JSONResponse({"success": True, "items": items[:200], "prefix": prefix, "archive": archive_name})
