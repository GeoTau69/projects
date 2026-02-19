#!/usr/bin/env python3
"""
build.py — JSON → HTML renderer pro projektovou dokumentaci.

Čte docs/data/{projekt}.json, renderuje přes Jinja2 šablony → statické HTML.
Žádné AI volání. Detekce změn přes MD5 hash (přeskakuje nezměněné projekty).

Použití:
  python build.py                              # všechny projekty v docs/data/
  python build.py --project backup-dashboard   # jen jeden projekt
  python build.py --project X --section rizika # hash detekce jen pro tuto sekci
  python build.py --check                      # jen validace JSON, bez renderování
  python build.py --force                      # ignoruj hash cache, vždy přebuduj
  python build.py --output /cesta/soubor.html  # vlastní výstupní soubor

Závislosti: jinja2 (povinná), jsonschema (volitelná — pro validaci)
  pip install jinja2 jsonschema
"""

import argparse
import hashlib
import html as html_module
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
    JINJA2_OK = True
except ImportError:
    JINJA2_OK = False

try:
    import jsonschema
    JSONSCHEMA_OK = True
except ImportError:
    JSONSCHEMA_OK = False

# ── Cesty ──────────────────────────────────────────────────────────────────────

DOCS_DIR      = Path(__file__).parent
DATA_DIR      = DOCS_DIR / "data"
TEMPLATES_DIR = DOCS_DIR / "templates"
SCHEMA_PATH   = DOCS_DIR / "schema" / "doc_schema.json"
OUTPUT_DIR    = DOCS_DIR / "output"
STATE_FILE    = DOCS_DIR / ".build-state.json"   # hash cache

# ── Hash utilty ────────────────────────────────────────────────────────────────

def compute_hash(data) -> str:
    """MD5 hash libovolných dat (dict, list nebo string). Používá usedforsecurity=False pro FIPS kompatibilitu."""
    if isinstance(data, (dict, list)):
        s = json.dumps(data, sort_keys=True, ensure_ascii=False)
    else:
        s = str(data)
    return hashlib.md5(s.encode("utf-8"), usedforsecurity=False).hexdigest()


def load_state() -> dict:
    """Načte stavový soubor s hashi předchozích buildů."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict):
    """Uloží stavový soubor."""
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

# ── Validace ───────────────────────────────────────────────────────────────────

def validate_doc(doc: dict) -> list[str]:
    """Validuje JSON dokument proti doc_schema.json. Vrátí seznam chybových zpráv."""
    if not JSONSCHEMA_OK:
        return []
    if not SCHEMA_PATH.exists():
        return [f"  Schéma nenalezeno: {SCHEMA_PATH}"]
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft7Validator(schema)
        errors = []
        for err in validator.iter_errors(doc):
            path = " → ".join(str(p) for p in err.absolute_path) or "(kořen)"
            errors.append(f"  [{path}] {err.message}")
        return errors
    except Exception as ex:
        return [f"  Chyba při validaci: {ex}"]

# ── Jinja2 ─────────────────────────────────────────────────────────────────────

def build_env() -> "Environment":
    """Vytvoří Jinja2 Environment s filtry."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,       # JSON je důvěryhodný zdroj; inline HTML v textech je záměrné
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Explicitní HTML escape — používáme ve šabloně pro code bloky ({{ text | e }})
    env.filters["e"] = html_module.escape
    return env

# ── Renderování ────────────────────────────────────────────────────────────────

def render_project(
    doc: dict,
    output_path: Path,
    section_id: str | None = None,
    force: bool = False,
) -> bool:
    """
    Renderuje projekt do HTML souboru.

    Pokud section_id je zadáno, hash se počítá jen z té sekce (úspora při
    inkrementálních AI updatech). HTML stránka se vždy generuje celá.

    Vrátí True pokud byl soubor vygenerován, False pokud přeskočen (beze změn).
    """
    state   = load_state()
    project = doc.get("project", output_path.stem)

    # Sestavit klíč a data pro hash detekci
    if section_id:
        sections = [s for s in doc.get("sections", []) if s["id"] == section_id]
        if not sections:
            print(f"  WARN: sekce '{section_id}' nenalezena v projektu '{project}'",
                  file=sys.stderr)
            return False
        hash_data = {"project": project, "section": sections[0]}
        state_key = f"{project}::{section_id}"
    else:
        hash_data = doc
        state_key = project

    current_hash = compute_hash(hash_data)

    if not force and state.get(state_key) == current_hash:
        print(f"  SKIP  {project}{f' [{section_id}]' if section_id else ''} — beze změn")
        return False

    # Render přes Jinja2
    env      = build_env()
    template = env.get_template("project.html.j2")
    html_out = template.render(
        doc=doc,
        built_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_out, encoding="utf-8")

    # Uložit hash
    state[state_key] = current_hash
    save_state(state)

    size_kb = len(html_out.encode("utf-8")) // 1024
    print(f"  OK    {output_path}  ({size_kb} kB)")
    return True

# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Renderuje projektovou dokumentaci z JSON → HTML (Jinja2, bez AI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Příklady:
  python build.py                                      # všechny projekty
  python build.py --project backup-dashboard           # jen jeden projekt
  python build.py --project backup-dashboard --section cli-snapper
  python build.py --check                              # jen validace JSON
  python build.py --force                              # ignoruj hash cache
  python build.py --project X --output ~/public/X.html
        """,
    )
    parser.add_argument("--project", "-p",
        metavar="ID",
        help="ID projektu (= název souboru bez .json v docs/data/)")
    parser.add_argument("--section", "-s",
        metavar="ID",
        help="Hash detekce jen pro tuto sekci; HTML se generuje vždy celé (vyžaduje --project)")
    parser.add_argument("--output", "-o",
        metavar="SOUBOR",
        help="Výstupní soubor (výchozí: docs/output/{projekt}.html)")
    parser.add_argument("--check",
        action="store_true",
        help="Jen validace JSON schématu, bez renderování")
    parser.add_argument("--force", "-f",
        action="store_true",
        help="Přebudovat i bez změn (ignoruj hash cache)")
    args = parser.parse_args()

    # Kontrola závislostí
    if not JINJA2_OK:
        print("CHYBA: Jinja2 není nainstalována.", file=sys.stderr)
        print("  pip install jinja2", file=sys.stderr)
        sys.exit(1)

    if not JSONSCHEMA_OK:
        print("WARN: jsonschema není nainstalováno — validace JSON přeskočena.")
        print("  pip install jsonschema")

    # Ověřit šablonu
    template_path = TEMPLATES_DIR / "project.html.j2"
    if not template_path.exists():
        print(f"CHYBA: Šablona nenalezena: {template_path}", file=sys.stderr)
        sys.exit(1)

    # Najít JSON soubory ke zpracování
    if args.project:
        json_files = [DATA_DIR / f"{args.project}.json"]
        if not json_files[0].exists():
            print(f"CHYBA: {json_files[0]} nenalezen", file=sys.stderr)
            sys.exit(1)
    else:
        if args.section:
            print("CHYBA: --section vyžaduje --project", file=sys.stderr)
            sys.exit(1)
        json_files = sorted(DATA_DIR.glob("*.json"))
        if not json_files:
            print(f"Žádné JSON soubory v {DATA_DIR}")
            print("Vytvořte docs/data/{{projekt}}.json (AI generuje, validuje doc_schema.json)")
            return

    generated = skipped = errors = 0

    for json_path in json_files:
        try:
            doc = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as ex:
            print(f"\n[{json_path.stem}]")
            print(f"  CHYBA: Neplatný JSON — {ex}", file=sys.stderr)
            errors += 1
            continue

        project = doc.get("project", json_path.stem)
        print(f"\n[{project}]")

        # Validace
        val_errors = validate_doc(doc)
        if val_errors:
            print(f"  WARN: {len(val_errors)} chyb validace JSON schématu:")
            for e in val_errors[:8]:    # max 8 chyb
                print(e)
            if len(val_errors) > 8:
                print(f"  ... a {len(val_errors) - 8} dalších chyb")

        if args.check:
            if not val_errors:
                print("  OK    validace prošla")
            else:
                errors += 1
            continue

        # Výstupní cesta
        if args.output:
            out = Path(args.output)
        else:
            out = OUTPUT_DIR / f"{project}.html"

        try:
            result = render_project(
                doc,
                out,
                section_id=args.section,
                force=args.force,
            )
            if result:
                generated += 1
            else:
                skipped += 1
        except Exception as ex:
            print(f"  CHYBA: {ex}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            errors += 1

    print(f"\nVýsledek: {generated} vygenerováno, {skipped} přeskočeno, {errors} chyb")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
