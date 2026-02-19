#!/usr/bin/env python3
"""
Generátor sekce Projekty v root CLAUDE.md z project.yaml souborů.
Přepisuje POUZE blok mezi markery (statické sekce zachovány).
Spuštění: python3 _meta/generate-docs.py  nebo  make docs
"""

import yaml
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
MASTER = ROOT / "CLAUDE.md"
MARKER_START = "<!-- PROJEKTY:START -->"
MARKER_END = "<!-- PROJEKTY:END -->"

STATUS_ICON = {"active": "🟢", "wip": "🟡", "planned": "⚪", "archived": "📦"}


def load_projects() -> list[dict]:
    projects = []
    for entry in sorted(ROOT.iterdir()):
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
        yaml_path = entry / "project.yaml"
        if yaml_path.exists():
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            data["_dir"] = entry.name
            data["_has_claude"] = (entry / "CLAUDE.md").exists()
            projects.append(data)
    return projects


def generate_block(projects: list[dict]) -> str:
    lines = [MARKER_START]
    lines.append(f"<!-- generováno: {datetime.now().strftime('%Y-%m-%d %H:%M')} -->")
    lines.append("")
    lines.append("| Projekt | Status | Tech | Port | Popis | Detail |")
    lines.append("|---------|--------|------|------|-------|--------|")

    for p in projects:
        icon = STATUS_ICON.get(p.get("status", "planned"), "❓")
        status = p.get("status", "?")
        name = p["_dir"]
        lang = p.get("language", "?")
        ptype = p.get("type", "")
        tech = f"{lang}/{ptype}" if ptype and ptype not in (lang, "web-app") else lang
        port = str(p.get("port", "–"))
        desc = p.get("description", "")
        if len(desc) > 55:
            desc = desc[:52] + "..."
        detail = f"`{name}/CLAUDE.md`" if p["_has_claude"] else "⚠️ chybí"
        lines.append(f"| {icon} `{name}/` | {status} | {tech} | {port} | {desc} | {detail} |")

    lines.append("")
    lines.append(MARKER_END)
    return "\n".join(lines)


def main():
    projects = load_projects()
    if not projects:
        print("Žádné projekty s project.yaml nenalezeny.")
        return

    content = MASTER.read_text(encoding="utf-8")

    start_idx = content.find(MARKER_START)
    end_idx = content.find(MARKER_END)

    if start_idx == -1 or end_idx == -1:
        print(f"CHYBA: Markery {MARKER_START!r} / {MARKER_END!r} nenalezeny v {MASTER}")
        return

    end_idx += len(MARKER_END)
    new_block = generate_block(projects)
    new_content = content[:start_idx] + new_block + content[end_idx:]

    MASTER.write_text(new_content, encoding="utf-8")
    print(f"Aktualizován {MASTER} ({len(projects)} projektů)")

    missing = [p["_dir"] for p in projects if not p["_has_claude"]]
    if missing:
        print(f"⚠️  Chybí slave CLAUDE.md: {', '.join(missing)}")


if __name__ == "__main__":
    main()
