#!/usr/bin/env python3
"""
Validátor izolace projektů.
Kontroluje, že žádný projekt neodkazuje na soubory jiného projektu.
Spuštění: python3 _meta/validate-isolation.py
"""

import os
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

def get_project_dirs() -> list[str]:
    """Seznam adresářů projektů"""
    return [
        d.name for d in sorted(ROOT.iterdir())
        if d.is_dir() and not d.name.startswith((".", "_"))
        and (d / "project.yaml").exists()
    ]

def check_cross_references(project_dir: str, all_projects: list[str]) -> list[str]:
    """Kontroluje cross-reference na jiné projekty"""
    issues = []
    other_projects = [p for p in all_projects if p != project_dir]
    project_path = ROOT / project_dir

    for root, dirs, files in os.walk(project_path):
        # Přeskočit skryté adresáře a cache
        dirs[:] = [d for d in dirs if not d.startswith((".")) and d != "__pycache__" and d != "node_modules"]

        for fname in files:
            # Kontrolovat jen textové soubory
            if not fname.endswith((".py", ".js", ".ts", ".sh", ".yaml", ".yml", ".json", ".html", ".css", ".md")):
                continue

            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue

            for other in other_projects:
                # Hledáme přímé importy nebo cesty na jiný projekt
                patterns = [
                    rf"from\s+{other}[\.\s]",          # Python import
                    rf"import\s+{other}[\.\s]",         # Python import
                    rf"require\(['\"]\.\./{other}",     # JS require
                    rf"from\s+['\"]\.\./{other}",       # JS import
                    rf"/{other}/",                       # Absolutní cesta
                ]
                for pattern in patterns:
                    if re.search(pattern, content):
                        rel_path = os.path.relpath(fpath, ROOT)
                        issues.append(f"  {rel_path}: odkazuje na '{other}'")

    return issues

def check_required_files(project_dir: str) -> list[str]:
    """Kontroluje povinné soubory"""
    issues = []
    project_path = ROOT / project_dir

    if not (project_path / "project.yaml").exists():
        issues.append(f"  Chybí project.yaml")
    if not (project_path / "CLAUDE.md").exists():
        issues.append(f"  Chybí CLAUDE.md")

    return issues

def main():
    projects = get_project_dirs()
    if not projects:
        print("Žádné projekty nenalezeny.")
        return

    print(f"Validuji izolaci {len(projects)} projektů...\n")
    total_issues = 0

    for project in projects:
        issues = []
        issues.extend(check_required_files(project))
        issues.extend(check_cross_references(project, projects))

        if issues:
            print(f"❌ {project}/")
            for issue in issues:
                print(issue)
            total_issues += len(issues)
        else:
            print(f"✅ {project}/")

    print(f"\n{'=' * 40}")
    if total_issues == 0:
        print("Všechny projekty jsou korektně izolované.")
    else:
        print(f"Nalezeno {total_issues} problémů!")

if __name__ == "__main__":
    main()
