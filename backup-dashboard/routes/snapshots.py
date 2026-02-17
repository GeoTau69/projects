"""
Snapper snapshot endpointy a datové funkce
"""

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from helpers import CONFIG, run_sudo, log_action

router = APIRouter()

# === DATOVÉ FUNKCE ===

def get_snapper_list() -> list[dict]:
    """Seznam Snapper snapshotů"""
    result = run_sudo(["snapper", "-c", CONFIG["snapper_config"], "list", "--columns",
                       "number,type,pre-number,date,cleanup,description"])
    if not result["success"]:
        return []

    snapshots = []
    lines = result["stdout"].split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("─") or line.startswith("Number") or line.startswith("#"):
            continue
        # Parsování snapper výstupu
        parts = [p.strip() for p in line.split("│")]
        if not parts:
            parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 4:
            try:
                num = int(parts[0].strip()) if parts[0].strip().isdigit() else None
                if num is not None:
                    snapshots.append({
                        "number": num,
                        "type": parts[1].strip() if len(parts) > 1 else "",
                        "pre_number": parts[2].strip() if len(parts) > 2 else "",
                        "date": parts[3].strip() if len(parts) > 3 else "",
                        "cleanup": parts[4].strip() if len(parts) > 4 else "",
                        "description": parts[5].strip() if len(parts) > 5 else "",
                    })
            except (ValueError, IndexError):
                continue
    return snapshots

# === ENDPOINTY ===

@router.post("/api/snapshot/create")
async def create_snapshot(description: str = Form("Manual snapshot from dashboard")):
    """Vytvoří nový Snapper snapshot"""
    result = run_sudo(["snapper", "-c", CONFIG["snapper_config"], "create",
                       "--type", "single", "--description", description, "--print-number"])
    if result["success"]:
        snap_num = result["stdout"].strip()
        log_action("Snapshot vytvořen", f"#{snap_num}: {description}")
        return JSONResponse({"success": True, "message": f"Snapshot #{snap_num} vytvořen", "number": snap_num})
    else:
        log_action("Snapshot SELHAL", result["stderr"], success=False)
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)


@router.post("/api/snapshot/new-golden")
async def new_golden_snapshot():
    """Vytvoří nový GOLDEN snapshot a přejmenuje starý"""
    snap_list = get_snapper_list()

    # Najít starý GOLDEN snapshot
    old_golden = [s for s in snap_list if "GOLDEN" in s.get("description", "")]

    # Přejmenovat staré GOLDEN snapshoty
    for snap in old_golden:
        old_desc = snap["description"]
        new_desc = old_desc.replace("GOLDEN", "GOLDEN-old")
        run_sudo(["snapper", "-c", CONFIG["snapper_config"], "modify",
                  "--description", new_desc, str(snap["number"])])
        log_action("GOLDEN deaktivován", f"#{snap['number']}: {old_desc} → {new_desc}")

    # Vytvořit nový GOLDEN snapshot
    result = run_sudo(["snapper", "-c", CONFIG["snapper_config"], "create",
                       "--type", "single",
                       "--description", "GOLDEN - čistý stav systému",
                       "--userdata", "important=yes",
                       "--print-number"])

    if result["success"]:
        snap_num = result["stdout"].strip()
        log_action("⭐ Nový GOLDEN vytvořen", f"#{snap_num} (starých: {len(old_golden)})")
        return JSONResponse({
            "success": True,
            "message": f"⭐ Nový GOLDEN snapshot #{snap_num} vytvořen" +
                       (f", deaktivováno {len(old_golden)} starých" if old_golden else "")
        })
    else:
        log_action("GOLDEN SELHAL", result["stderr"], success=False)
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)

@router.post("/api/snapshot/delete/{number}")
async def delete_snapshot(number: int):
    """Smaže Snapper snapshot"""
    if number <= 1:
        return JSONResponse({"success": False, "message": "Snapshot #0 a #1 nelze smazat!"}, status_code=400)
    result = run_sudo(["snapper", "-c", CONFIG["snapper_config"], "delete", str(number)])
    if result["success"]:
        log_action("Snapshot smazán", f"#{number}")
        return JSONResponse({"success": True, "message": f"Snapshot #{number} smazán"})
    else:
        log_action("Smazání snapshotu SELHALO", f"#{number}: {result['stderr']}", success=False)
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)

@router.post("/api/snapshot/rollback/{number}")
async def rollback_snapshot(number: int):
    """Rollback na Snapper snapshot (vyžaduje reboot)"""
    if number < 1:
        return JSONResponse({"success": False, "message": "Neplatný snapshot"}, status_code=400)

    result = run_sudo(["snapper", "-c", CONFIG["snapper_config"], "rollback", str(number)])
    if result["success"]:
        log_action("ROLLBACK", f"Na snapshot #{number} - VYŽADUJE REBOOT")
        return JSONResponse({
            "success": True,
            "message": f"Rollback na #{number} připraven. RESTARTUJTE systém pro dokončení!",
            "needs_reboot": True,
        })
    else:
        log_action("ROLLBACK SELHAL", f"#{number}: {result['stderr']}", success=False)
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)

@router.get("/api/snapshot/diff/{number}")
async def snapshot_diff(number: int):
    """Zobrazí změny ve snapshotu oproti aktuálnímu stavu"""
    result = run_sudo(["snapper", "-c", CONFIG["snapper_config"], "status", f"{number}..0"])
    if result["success"]:
        return JSONResponse({"success": True, "diff": result["stdout"]})
    else:
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)
