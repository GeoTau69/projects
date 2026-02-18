#!/usr/bin/env python3
"""
info-sync.py — Synchronizace živého stavu projektů do CLAUDE.md souborů.

Průchod:
  1. Discovery přes project.yaml (nezávisle na master CLAUDE.md)
  2. Pro každý projekt: zjistí živý stav → aktualizuje <!-- SYNC:START/END --> ve slave CLAUDE.md
  3. Aktualizuje <!-- PROJEKTY:START/END --> v master CLAUDE.md

Spuštění: python3 info-sync.py  (sudo není nutné, ale nevadí)
"""

import yaml
import subprocess
import socket
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
MASTER = ROOT / "CLAUDE.md"

# Markery master
M_START = "<!-- PROJEKTY:START -->"
M_END = "<!-- PROJEKTY:END -->"

# Markery slave (živý stav)
S_START = "<!-- SYNC:START -->"
S_END = "<!-- SYNC:END -->"

STATUS_ICON = {"active": "🟢", "wip": "🟡", "planned": "⚪", "archived": "📦"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd: list[str], cwd: Path = None) -> str:
    """Spustí příkaz, vrátí stdout nebo '' při chybě."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5,
            cwd=cwd or ROOT
        )
        return r.stdout.strip()
    except Exception:
        return ""


def port_open(port: int) -> bool:
    """Vrátí True pokud port naslouchá."""
    try:
        with socket.create_connection(("localhost", port), timeout=1):
            return True
    except Exception:
        return False


def service_active(service: str) -> str:
    """Vrátí stav systemd služby (active/inactive/unknown)."""
    result = run(["systemctl", "is-active", service])
    return result if result else "unknown"


def git_last_commit(project_dir: Path) -> dict:
    """Poslední commit týkající se daného adresáře."""
    log = run(["git", "log", "--oneline", "-1", "--", "."], cwd=project_dir)
    if not log:
        log = run(["git", "log", "--oneline", "-1"], cwd=ROOT)
    if log:
        parts = log.split(" ", 1)
        return {"hash": parts[0], "msg": parts[1] if len(parts) > 1 else ""}
    return {"hash": "–", "msg": "–"}


# ── Discovery ─────────────────────────────────────────────────────────────────

def load_projects() -> list[dict]:
    """Najde všechny adresáře s project.yaml."""
    projects = []
    for entry in sorted(ROOT.iterdir()):
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
        yaml_path = entry / "project.yaml"
        if yaml_path.exists():
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            data["_dir"] = entry.name
            data["_path"] = entry
            data["_has_claude"] = (entry / "CLAUDE.md").exists()
            projects.append(data)
    return projects


# ── Live data ─────────────────────────────────────────────────────────────────

def collect_live(p: dict) -> dict:
    """Zjistí živý stav projektu."""
    port = p.get("port")
    service = p.get("systemd_service")
    user_service = p.get("systemd_user", False)

    port_ok = port_open(port) if port else None

    # User services nelze dotázat jako root → dedukujeme z portu
    if service:
        if user_service:
            svc_status = "active" if port_ok else "inactive"
        else:
            svc_status = service_active(service)
    else:
        svc_status = None

    return {
        "port": port,
        "port_ok": port_ok,
        "service": service,
        "service_user": user_service,
        "service_status": svc_status,
        "git": git_last_commit(p["_path"]),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ── Slave CLAUDE.md ───────────────────────────────────────────────────────────

def format_sync_block(p: dict, live: dict) -> str:
    """Vygeneruje <!-- SYNC --> blok pro slave CLAUDE.md."""
    lines = [S_START, f"<!-- aktualizováno: {live['ts']} -->", ""]
    lines.append("**Živý stav** *(info-sync.py)*")
    lines.append("")

    if live["service"] and live["service_status"]:
        icon = "🟢" if live["service_status"] == "active" else "🔴"
        stype = " (user service)" if live["service_user"] else " (system service)"
        lines.append(f"- Služba `{live['service']}`{stype}: {icon} {live['service_status']}")

    if live["port"] is not None:
        icon = "🟢" if live["port_ok"] else "🔴"
        state = "naslouchá" if live["port_ok"] else "neodpovídá"
        lines.append(f"- Port {live['port']}: {icon} {state}")

    git = live["git"]
    lines.append(f"- Poslední commit: `{git['hash']}` — {git['msg']}")

    lines += ["", S_END]
    return "\n".join(lines)


def update_slave(p: dict, live: dict) -> bool:
    slave_path = p["_path"] / "CLAUDE.md"
    if not slave_path.exists():
        return False

    content = slave_path.read_text(encoding="utf-8")
    new_block = format_sync_block(p, live)

    s = content.find(S_START)
    e = content.find(S_END)

    if s != -1 and e != -1:
        # Přepsat existující blok
        new_content = content[:s] + new_block + content[e + len(S_END):]
    else:
        # Přidat na konec souboru
        new_content = content.rstrip() + "\n\n" + new_block + "\n"

    slave_path.write_text(new_content, encoding="utf-8")
    return True


# ── Master CLAUDE.md ──────────────────────────────────────────────────────────

def update_master(projects: list[dict], live_data: list[dict]) -> None:
    content = MASTER.read_text(encoding="utf-8")

    s = content.find(M_START)
    e = content.find(M_END)
    if s == -1 or e == -1:
        print(f"CHYBA: Markery nenalezeny v {MASTER}")
        return

    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [M_START, f"<!-- generováno: {ts} -->", ""]
    lines.append("| Projekt | Status | Tech | Port | Živý stav | Popis | Detail |")
    lines.append("|---------|--------|------|------|-----------|-------|--------|")

    for p, live in zip(projects, live_data):
        proj_icon = STATUS_ICON.get(p.get("status", "planned"), "❓")
        name = p["_dir"]
        lang = p.get("language", "?")
        ptype = p.get("type", "")
        tech = lang if not ptype or ptype in (lang, "web-app") else f"{lang}/{ptype}"
        port = str(p.get("port", "–"))
        desc = p.get("description", "")
        if len(desc) > 45:
            desc = desc[:42] + "..."
        detail = f"`{name}/CLAUDE.md`" if p["_has_claude"] else "⚠️ chybí"

        if live["port_ok"] is not None:
            live_icon = "🟢" if live["port_ok"] else "🔴"
        elif live["service_status"]:
            live_icon = "🟢" if live["service_status"] == "active" else "🔴"
        else:
            live_icon = "❓"

        lines.append(
            f"| {proj_icon} `{name}/` | {p.get('status','?')} | {tech} | {port} "
            f"| {live_icon} | {desc} | {detail} |"
        )

    lines += ["", M_END]
    e += len(M_END)
    MASTER.write_text(
        content[:s] + "\n".join(lines) + content[e:],
        encoding="utf-8"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"info-sync.py — {now}")
    print(f"Root: {ROOT}\n")

    projects = load_projects()
    if not projects:
        print("Žádné projekty s project.yaml nenalezeny.")
        return

    live_data = []
    for p in projects:
        name = p["_dir"]
        print(f"[{name}]")
        live = collect_live(p)
        live_data.append(live)

        if live["service"] and live["service_status"]:
            icon = "🟢" if live["service_status"] == "active" else "🔴"
            print(f"  Služba {live['service']}: {icon} {live['service_status']}")

        if live["port"] is not None:
            icon = "🟢" if live["port_ok"] else "🔴"
            print(f"  Port {live['port']}: {icon}")

        git = live["git"]
        print(f"  Git: {git['hash']} — {git['msg']}")

        if p["_has_claude"]:
            ok = update_slave(p, live)
            print(f"  {'✅ slave CLAUDE.md aktualizován' if ok else '❌ zápis selhal'}")
        else:
            print(f"  ⚠️  slave CLAUDE.md chybí — přeskočeno")
        print()

    update_master(projects, live_data)
    print(f"✅ Master CLAUDE.md aktualizován ({len(projects)} projektů)")


if __name__ == "__main__":
    main()
