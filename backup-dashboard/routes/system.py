"""
Systémové endpointy - dashboard, docs, health, logs, sync, full-backup, nuclear-delete
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse

from helpers import CONFIG, run_cmd, run_sudo, log_action, get_borg_env, templates
from routes.snapshots import get_snapper_list
from routes.borg import get_borg_archives

router = APIRouter()

# === DATOVÉ FUNKCE ===

def get_backup_disk_status() -> dict:
    """Stav backup disku"""
    mount = CONFIG["backup_mount"]
    mounted = run_cmd(["mountpoint", "-q", mount])["success"]
    if not mounted:
        return {"mounted": False, "total": "N/A", "used": "N/A", "avail": "N/A", "percent": "N/A"}

    df = run_cmd(["df", "-h", "--output=size,used,avail,pcent", mount])
    if df["success"]:
        lines = df["stdout"].strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            return {
                "mounted": True,
                "total": parts[0] if len(parts) > 0 else "?",
                "used": parts[1] if len(parts) > 1 else "?",
                "avail": parts[2] if len(parts) > 2 else "?",
                "percent": parts[3] if len(parts) > 3 else "?",
            }
    return {"mounted": mounted, "total": "?", "used": "?", "avail": "?", "percent": "?"}

def get_root_disk_status() -> dict:
    """Stav root disku"""
    df = run_cmd(["df", "-h", "--output=size,used,avail,pcent", "/"])
    if df["success"]:
        lines = df["stdout"].strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            return {
                "total": parts[0] if len(parts) > 0 else "?",
                "used": parts[1] if len(parts) > 1 else "?",
                "avail": parts[2] if len(parts) > 2 else "?",
                "percent": parts[3] if len(parts) > 3 else "?",
            }
    return {"total": "?", "used": "?", "avail": "?", "percent": "?"}

def get_systemd_timers() -> list[dict]:
    """Stav backup timerů"""
    timers_to_check = [
        ("snapper-timeline.timer", "Snapper Timeline"),
        ("snapper-cleanup.timer", "Snapper Cleanup"),
        ("borg-backup.timer", "Borg Backup"),
        ("snapshot-sync.timer", "Snapshot Sync"),
    ]
    timers = []
    for unit, label in timers_to_check:
        status = run_cmd(["systemctl", "is-active", unit])
        next_run = run_cmd(["systemctl", "show", unit, "--property=NextElapseUSecRealtime", "--value"])
        last_trigger = run_cmd(["systemctl", "show", unit, "--property=LastTriggerUSec", "--value"])
        timers.append({
            "unit": unit,
            "label": label,
            "active": status["stdout"] == "active",
            "next_run": next_run["stdout"] if next_run["success"] else "?",
            "last_trigger": last_trigger["stdout"] if last_trigger["success"] else "?",
        })
    return timers

def get_sync_snapshots() -> list[str]:
    """Seznam snapshotů na backup disku"""
    sync_dir = CONFIG["snapshot_sync_dir"]
    if not os.path.isdir(sync_dir):
        return []
    try:
        entries = sorted(os.listdir(sync_dir), reverse=True)
        return entries[:20]
    except OSError:
        return []

def get_dashboard_log(lines: int = 30) -> list[str]:
    """Posledních N řádek logu"""
    log_path = Path(CONFIG["log_file"])
    if not log_path.exists():
        return []
    try:
        with open(log_path) as f:
            all_lines = f.readlines()
        return list(reversed(all_lines[-lines:]))
    except OSError:
        return []

def get_health_status() -> dict:
    """Celkový zdravotní stav"""
    warnings = []
    errors = []

    # Backup disk mounted?
    disk = get_backup_disk_status()
    if not disk["mounted"]:
        errors.append("Backup disk NENÍ připojen!")

    # Snapper snapshoty existují?
    snaps = get_snapper_list()
    if len(snaps) < 2:
        warnings.append("Málo Snapper snapshotů")

    # Borg - poslední archiv
    archives = get_borg_archives()
    if not archives:
        errors.append("Žádné Borg archivy!")
    elif archives:
        try:
            last_time_str = archives[0]["time"].strip()
            # Borg formát: "Fri, 2026-02-13 03:13:47"
            for fmt in ["%a, %Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    last_time = datetime.strptime(last_time_str, fmt)
                    if datetime.now() - last_time > timedelta(hours=36):
                        warnings.append(f"Poslední Borg archiv je starší než 36h: {last_time_str}")
                    break
                except ValueError:
                    continue
        except (KeyError, IndexError):
            pass

    # Root disk
    root = get_root_disk_status()

    status = "ok"
    if warnings:
        status = "warning"
    if errors:
        status = "error"

    return {
        "status": status,
        "warnings": warnings,
        "errors": errors,
        "snapshots": {"count": len(snaps)},
        "borg": {
            "count": len(archives),
            "last_backup": archives[0]["time"] if archives else "N/A",
        },
        "backup_disk": {
            "mounted": disk["mounted"],
            "used_percent": int(disk["percent"].replace("%", "")) if disk["percent"] not in ("N/A", "?") else 0,
        },
        "root_disk": {
            "used_percent": int(root["percent"].replace("%", "")) if root["percent"] not in ("N/A", "?") else 0,
        },
        "sync": {"last_run": "N/A"},
    }

# === ENDPOINTY ===

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Hlavní dashboard"""
    health = get_health_status()
    disk_backup = get_backup_disk_status()
    disk_root = get_root_disk_status()
    snapshots = get_snapper_list()
    archives = get_borg_archives()
    timers = get_systemd_timers()
    sync_snaps = get_sync_snapshots()
    log_lines = get_dashboard_log(20)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "health": health,
        "disk_backup": disk_backup,
        "disk_root": disk_root,
        "snapshots": snapshots,
        "archives": archives,
        "timers": timers,
        "sync_snaps": sync_snaps,
        "log_lines": log_lines,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

@router.get("/docs", response_class=HTMLResponse)
async def docs_page(request: Request):
    """Dokumentace systému s live status"""
    return templates.TemplateResponse("docs.html", {"request": request})

@router.get("/api/health")
async def health_check():
    """Zdravotní check pro monitoring"""
    return JSONResponse(get_health_status())

@router.get("/api/refresh")
async def refresh_data():
    """Vrátí aktuální data jako JSON"""
    return JSONResponse({
        "health": get_health_status(),
        "disk_backup": get_backup_disk_status(),
        "disk_root": get_root_disk_status(),
        "snapshots": get_snapper_list(),
        "archives": get_borg_archives(),
        "timers": get_systemd_timers(),
        "log": get_dashboard_log(20),
    })

# === LOG MANAGEMENT ===

@router.get("/api/logs")
async def get_logs(lines: int = 100):
    """Vrátí log"""
    log_lines = get_dashboard_log(lines)
    return JSONResponse({"success": True, "lines": log_lines, "total": len(log_lines)})

@router.post("/api/logs/clear")
async def clear_logs(password: str = Form(...)):
    """Smaže log - chráněno heslem"""
    if password != "19801969":
        return JSONResponse({"success": False, "message": "Špatné heslo"}, status_code=403)
    log_path = Path(CONFIG["log_file"])
    if log_path.exists():
        with open(log_path, "w") as f:
            f.write("")
    log_action("Log vymazán", "Manuální smazání logu")
    return JSONResponse({"success": True, "message": "Log vymazán"})

@router.post("/api/logs/export")
async def export_logs():
    """Exportuje log jako soubor"""
    from fastapi.responses import FileResponse
    log_path = Path(CONFIG["log_file"])
    if log_path.exists():
        return FileResponse(log_path, filename=f"backup-dashboard-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log")
    return JSONResponse({"success": False, "message": "Log neexistuje"}, status_code=404)

# === SYNC ===

@router.post("/api/sync/run")
async def run_sync():
    """Spustí sync snapshotů na backup disk"""
    script = "/usr/local/bin/backup-snapshot-sync.sh"
    if os.path.exists(script):
        result = run_sudo([script], timeout=600)
    else:
        # Fallback - ruční btrfs send
        result = run_sudo(["systemctl", "start", "snapshot-sync.service"])

    if result["success"]:
        log_action("Snapshot sync spuštěn", "OK")
        return JSONResponse({"success": True, "message": "Sync spuštěn"})
    else:
        log_action("Snapshot sync SELHAL", result["stderr"], success=False)
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)

# === FULL FLOW ===

@router.post("/api/full-backup")
async def full_backup_flow(description: str = Form("Full backup flow")):
    """Kompletní backup flow: Snapshot → Borg → Sync"""
    results = []

    # Krok 1: Snapper snapshot
    log_action("FULL FLOW", "Krok 1/3: Vytvářím snapshot...")
    snap_result = run_sudo(["snapper", "-c", CONFIG["snapper_config"], "create",
                            "--type", "single", "--description", f"[FULL] {description}", "--print-number"])
    if snap_result["success"]:
        snap_num = snap_result["stdout"].strip()
        results.append(f"✅ Snapshot #{snap_num} vytvořen")
        log_action("FULL FLOW snapshot", f"#{snap_num}: {description}")
    else:
        results.append(f"❌ Snapshot selhal: {snap_result['stderr']}")
        log_action("FULL FLOW snapshot SELHAL", snap_result["stderr"], success=False)

    # Krok 2: Borg backup
    log_action("FULL FLOW", "Krok 2/3: Spouštím Borg backup...")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r'[^a-zA-Z0-9_-]', '-', description.strip())
    slug = re.sub(r'-+', '-', slug).strip('-')[:50]
    archive_name = f"FULL-{slug}-{timestamp}" if slug else f"FULL-{timestamp}"

    exclude_args = []
    for exc in CONFIG["borg_excludes"]:
        exclude_args.extend(["--exclude", exc])

    cmd = [
        "borg", "create",
        "--compression", "zstd", "--one-file-system", "--exclude-if-present", ".nobackup",
        "--comment", f"[FULL FLOW] {description}",
        f"{CONFIG['borg_repo']}::{archive_name}",
        CONFIG["borg_source"],
    ] + exclude_args

    borg_result = run_cmd(cmd, timeout=3600, env_extra=get_borg_env())
    if borg_result["success"]:
        results.append(f"✅ Borg archiv {archive_name} vytvořen")
        log_action("FULL FLOW borg", archive_name)
    else:
        results.append(f"❌ Borg selhal: {borg_result['stderr']}")
        log_action("FULL FLOW borg SELHAL", borg_result["stderr"], success=False)

    # Krok 3: Sync na backup disk
    log_action("FULL FLOW", "Krok 3/3: Sync snapshotů na backup disk...")
    script = "/usr/local/bin/backup-snapshot-sync.sh"
    if os.path.exists(script):
        sync_result = run_sudo([script], timeout=600)
    else:
        sync_result = run_sudo(["systemctl", "start", "snapshot-sync.service"])

    if sync_result["success"]:
        results.append("✅ Sync na backup disk dokončen")
        log_action("FULL FLOW sync", "OK")
    else:
        results.append(f"❌ Sync selhal: {sync_result['stderr']}")
        log_action("FULL FLOW sync SELHAL", sync_result["stderr"], success=False)

    all_ok = all("✅" in r for r in results)
    log_action("FULL FLOW DOKONČEN", " | ".join(results), success=all_ok)

    return JSONResponse({
        "success": all_ok,
        "message": "\n".join(results),
        "results": results,
    })

# === NUCLEAR DELETE ===

@router.post("/api/nuclear-delete")
async def nuclear_delete(password: str = Form(...), confirm_text: str = Form(...)):
    """Smaže VŠECHNY zálohy - chráněno heslem"""
    NUCLEAR_PASSWORD = "19801969"

    if password != NUCLEAR_PASSWORD:
        log_action("NUCLEAR DELETE ODMÍTNUTO", "Špatné heslo", success=False)
        return JSONResponse({"success": False, "message": "❌ Špatné heslo!"}, status_code=403)

    if confirm_text != "SMAZAT VSE":
        return JSONResponse({"success": False, "message": "❌ Musíte napsat přesně: SMAZAT VSE"}, status_code=400)

    results = []
    log_action("⚠️ NUCLEAR DELETE", "ZAHÁJENO - mažu všechny zálohy!")

    # 1. Smazat všechny Snapper snapshoty (kromě #0 a #1)
    snap_list = get_snapper_list()
    deleted_snaps = 0
    for snap in snap_list:
        if snap["number"] > 1 and snap.get("description", "").find("GOLDEN") == -1:
            r = run_sudo(["snapper", "-c", CONFIG["snapper_config"], "delete", str(snap["number"])])
            if r["success"]:
                deleted_snaps += 1
    results.append(f"🗑 Smazáno {deleted_snaps} Snapper snapshotů")

    # 2. Smazat všechny Borg archivy
    archives = get_borg_archives()
    deleted_borg = 0
    for arch in archives:
        r = run_cmd(
            ["borg", "delete", "--force", f"{CONFIG['borg_repo']}::{arch['name']}"],
            timeout=300,
            env_extra=get_borg_env(),
        )
        if r["success"]:
            deleted_borg += 1
    # Compact repo
    run_cmd(["borg", "compact", CONFIG["borg_repo"]], timeout=600, env_extra=get_borg_env())
    results.append(f"🗑 Smazáno {deleted_borg} Borg archivů")

    # 3. Smazat sync snapshoty z backup disku
    sync_dir = CONFIG["snapshot_sync_dir"]
    deleted_sync = 0
    if os.path.isdir(sync_dir):
        for entry in os.listdir(sync_dir):
            full_path = os.path.join(sync_dir, entry)
            r = run_sudo(["btrfs", "subvolume", "delete", full_path])
            if r["success"]:
                deleted_sync += 1
            else:
                # Fallback - rm -rf
                run_sudo(["rm", "-rf", full_path])
                deleted_sync += 1
    results.append(f"🗑 Smazáno {deleted_sync} sync snapshotů z backup disku")

    log_action("⚠️ NUCLEAR DELETE DOKONČEN", " | ".join(results))

    return JSONResponse({
        "success": True,
        "message": "\n".join(results),
        "results": results,
    })
