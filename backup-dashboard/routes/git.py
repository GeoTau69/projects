"""
Git správa verzí - endpointy a datové funkce
"""

import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from helpers import run_cmd, run_sudo, log_action, templates

router = APIRouter()

# === DATOVÉ FUNKCE ===

def run_git(args: list[str], timeout: int = 30) -> dict:
    """Spustí git příkaz v adresáři projektu"""
    return run_cmd(["git"] + args, timeout=timeout)

def get_git_log(max_count: int = 50) -> list[dict]:
    """Vrátí historii commitů včetně poznámek"""
    # %x1e = record separator, %x1f = unit separator
    result = run_git(["log", f"--max-count={max_count}", "--notes",
                      "--format=%H%x1f%h%x1f%ai%x1f%an%x1f%s%x1f%N%x1e"])
    if not result["success"]:
        return []
    commits = []
    for record in result["stdout"].split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f", 5)
        if len(parts) >= 5:
            note = parts[5].strip().replace("\n", " ") if len(parts) > 5 else ""
            commits.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "date": parts[2],
                "author": parts[3],
                "message": parts[4],
                "note": note,
            })
    return commits

def get_git_status() -> dict:
    """Vrátí stav git repozitáře"""
    branch_result = run_git(["branch", "--show-current"])
    branch = branch_result["stdout"] if branch_result["success"] else "?"

    status_result = run_git(["status", "--porcelain"])
    changes = []
    if status_result["success"] and status_result["stdout"]:
        for line in status_result["stdout"].split("\n"):
            if line.strip():
                changes.append(line)

    return {
        "branch": branch,
        "clean": len(changes) == 0,
        "changes": changes,
    }

def get_git_diff(commit_hash: str) -> str:
    """Vrátí diff konkrétního commitu"""
    # Zjistit, jestli má commit rodiče
    parent_check = run_git(["rev-parse", f"{commit_hash}^"], timeout=10)
    if parent_check["success"]:
        result = run_git(["diff", f"{commit_hash}^", commit_hash], timeout=30)
    else:
        # První commit — diff proti prázdnému stromu
        result = run_git(["diff", "4b825dc642cb6eb9a060e54bf899d15f3f7150", commit_hash], timeout=30)
    return result["stdout"] if result["success"] else result["stderr"]

# === ENDPOINTY ===

@router.get("/git", response_class=HTMLResponse)
async def git_page(request: Request):
    """Stránka pro správu verzí"""
    return templates.TemplateResponse("git.html", {"request": request})

@router.get("/api/git/log")
async def api_git_log():
    """Historie commitů"""
    commits = get_git_log()
    status = get_git_status()
    return JSONResponse({"success": True, "commits": commits, "status": status})

@router.get("/api/git/diff/{commit_hash}")
async def api_git_diff(commit_hash: str):
    """Diff konkrétního commitu"""
    if not re.match(r'^[0-9a-fA-F]{4,40}$', commit_hash):
        return JSONResponse({"success": False, "message": "Neplatný hash"}, status_code=400)
    diff = get_git_diff(commit_hash)
    return JSONResponse({"success": True, "diff": diff, "hash": commit_hash})

@router.post("/api/git/note/{commit_hash}")
async def api_git_note(commit_hash: str, note: str = Form("")):
    """Přidá nebo upraví poznámku ke commitu"""
    if not re.match(r'^[0-9a-fA-F]{4,40}$', commit_hash):
        return JSONResponse({"success": False, "message": "Neplatný hash"}, status_code=400)

    if note.strip():
        result = run_git(["notes", "add", "-f", "-m", note.strip(), commit_hash])
    else:
        result = run_git(["notes", "remove", commit_hash])
        # "No note found" není chyba — prostě žádná poznámka nebyla
        if not result["success"] and "No note found" in result["stderr"]:
            return JSONResponse({"success": True, "message": "Poznámka odstraněna"})

    if result["success"]:
        log_action("Git poznámka", f"{commit_hash[:7]}: {note.strip()[:50]}")
        return JSONResponse({"success": True, "message": "Poznámka uložena"})
    else:
        return JSONResponse({"success": False, "message": result["stderr"]}, status_code=500)

@router.post("/api/git/commit")
async def api_git_commit(message: str = Form(...)):
    """Vytvoří nový git commit"""
    if not message.strip():
        return JSONResponse({"success": False, "message": "Zpráva commitu nesmí být prázdná"}, status_code=400)

    # Přidat všechny změny
    add_result = run_git(["add", "-A"])
    if not add_result["success"]:
        return JSONResponse({"success": False, "message": f"git add selhal: {add_result['stderr']}"}, status_code=500)

    # Ověřit, že je co commitovat
    status = run_git(["status", "--porcelain"])
    if not status["stdout"].strip():
        return JSONResponse({"success": False, "message": "Žádné změny k uložení"}, status_code=400)

    # Commit
    commit_result = run_git(["commit", "-m", message.strip()])
    if commit_result["success"]:
        # Získat hash nového commitu
        hash_result = run_git(["rev-parse", "--short", "HEAD"])
        short_hash = hash_result["stdout"] if hash_result["success"] else "?"
        log_action("Git commit", f"{short_hash}: {message.strip()}")
        return JSONResponse({"success": True, "message": f"Commit {short_hash} vytvořen", "hash": short_hash})
    else:
        log_action("Git commit SELHAL", commit_result["stderr"], success=False)
        return JSONResponse({"success": False, "message": commit_result["stderr"]}, status_code=500)

@router.post("/api/git/rollback/{commit_hash}")
async def api_git_rollback(commit_hash: str):
    """Rollback na konkrétní verzi — vytvoří nový commit"""
    if not re.match(r'^[0-9a-fA-F]{4,40}$', commit_hash):
        return JSONResponse({"success": False, "message": "Neplatný hash"}, status_code=400)

    # Ověřit, že commit existuje
    verify = run_git(["cat-file", "-t", commit_hash])
    if not verify["success"] or verify["stdout"] != "commit":
        return JSONResponse({"success": False, "message": "Commit neexistuje"}, status_code=404)

    # Získat krátký hash
    short = run_git(["rev-parse", "--short", commit_hash])
    short_hash = short["stdout"] if short["success"] else commit_hash[:7]

    # Checkout souborů z dané verze
    checkout = run_git(["checkout", commit_hash, "--", "."])
    if not checkout["success"]:
        log_action("Git rollback SELHAL", f"checkout {short_hash}: {checkout['stderr']}", success=False)
        return JSONResponse({"success": False, "message": checkout["stderr"]}, status_code=500)

    # Auto-commit
    run_git(["add", "-A"])
    commit_msg = f"Rollback na verzi {short_hash}"
    commit_result = run_git(["commit", "-m", commit_msg])
    if not commit_result["success"]:
        # Pokud nejsou změny (rollback na aktuální stav)
        if "nothing to commit" in commit_result["stdout"]:
            return JSONResponse({"success": True, "message": f"Verze {short_hash} je již aktuální, žádné změny"})
        log_action("Git rollback SELHAL", f"commit: {commit_result['stderr']}", success=False)
        return JSONResponse({"success": False, "message": commit_result["stderr"]}, status_code=500)

    log_action("Git rollback", f"Na verzi {short_hash}")

    # Restart služby
    run_sudo(["systemctl", "restart", "backup-dashboard"])

    return JSONResponse({"success": True, "message": f"Rollback na verzi {short_hash} proveden. Služba se restartuje..."})
