#!/usr/bin/env python3
"""
Generátor root CLAUDE.md z project.yaml souborů.
Spuštění: python3 _meta/generate-docs.py
"""

import os
import yaml
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "CLAUDE.md"

def load_projects() -> list[dict]:
    """Načte všechny project.yaml soubory"""
    projects = []
    for entry in sorted(ROOT.iterdir()):
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
        yaml_path = entry / "project.yaml"
        if yaml_path.exists():
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            data["_dir"] = entry.name
            projects.append(data)
    return projects

def generate_markdown(projects: list[dict]) -> str:
    """Vygeneruje obsah root CLAUDE.md"""
    lines = []
    lines.append("# Projektový workspace")
    lines.append("")
    lines.append(f"> Auto-generováno: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> Počet projektů: {len(projects)}")
    lines.append("")

    # Globální konvence
    lines.append("## Globální konvence")
    lines.append("")
    lines.append("- **Jazyk kódu/komentářů**: čeština")
    lines.append("- **Kódování**: UTF-8 (vždy)")
    lines.append("- **Izolace**: každý projekt je self-contained, žádné cross-imports")
    lines.append("- **Metadata**: každý projekt má `project.yaml` + vlastní `CLAUDE.md`")
    lines.append("- **Git**: monorepo, projekty jako adresáře v rootu")
    lines.append("")

    # Přehled projektů
    status_icons = {
        "active": "🟢",
        "wip": "🟡",
        "planned": "⚪",
        "archived": "📦",
    }

    lines.append("## Projekty")
    lines.append("")

    for p in projects:
        icon = status_icons.get(p.get("status", "planned"), "❓")
        name = p.get("display_name", p.get("name", p["_dir"]))
        status = p.get("status", "?")
        desc = p.get("description", "")
        lang = p.get("language", "?")
        ptype = p.get("type", "?")
        port = p.get("port")
        service = p.get("systemd_service")
        tags = ", ".join(p.get("tags", []))

        lines.append(f"### {icon} {name} (`{p['_dir']}/`)")
        lines.append("")
        lines.append(f"- **Stav**: {status}")
        lines.append(f"- **Typ**: {ptype} | **Jazyk**: {lang}")
        if port:
            lines.append(f"- **Port**: {port}")
        if service:
            lines.append(f"- **Služba**: `{service}`")
        lines.append(f"- **Popis**: {desc}")
        if tags:
            lines.append(f"- **Tagy**: {tags}")
        lines.append("")

    return "\n".join(lines)

def main():
    projects = load_projects()
    if not projects:
        print("Žádné projekty s project.yaml nenalezeny.")
        return

    content = generate_markdown(projects)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Vygenerován {OUTPUT} ({len(projects)} projektů)")

if __name__ == "__main__":
    main()
