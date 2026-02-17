#!/bin/bash
# Vytvoří nový projekt ze šablony
# Spuštění: bash _meta/new-project.sh <název-projektu>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -z "${1:-}" ]; then
    echo "Použití: bash _meta/new-project.sh <název-projektu>"
    echo "Příklad: bash _meta/new-project.sh muj-novy-projekt"
    exit 1
fi

PROJECT_NAME="$1"
PROJECT_DIR="$ROOT_DIR/$PROJECT_NAME"

if [ -d "$PROJECT_DIR" ]; then
    echo "Chyba: Adresář '$PROJECT_NAME' již existuje!"
    exit 1
fi

echo "Vytvářím projekt: $PROJECT_NAME"
mkdir -p "$PROJECT_DIR"

# project.yaml z šablony
cp "$SCRIPT_DIR/templates/project.yaml.template" "$PROJECT_DIR/project.yaml"
sed -i "s/project-name/$PROJECT_NAME/g" "$PROJECT_DIR/project.yaml"
sed -i "s/Název projektu/$PROJECT_NAME/g" "$PROJECT_DIR/project.yaml"

# CLAUDE.md z šablony
sed "s/{display_name}/$PROJECT_NAME/g; s/{description}/Popis projektu/g; s/{language}/python/g; s/{type}/scripts/g" \
    "$SCRIPT_DIR/templates/CLAUDE.md.template" > "$PROJECT_DIR/CLAUDE.md"

# README.md
echo "# $PROJECT_NAME" > "$PROJECT_DIR/README.md"
echo "" >> "$PROJECT_DIR/README.md"
echo "Popis projektu." >> "$PROJECT_DIR/README.md"

echo ""
echo "✅ Projekt '$PROJECT_NAME' vytvořen v: $PROJECT_DIR"
echo "   Upravte: project.yaml, CLAUDE.md, README.md"
echo "   Regenerujte docs: python3 _meta/generate-docs.py"
