#!/usr/bin/env python3
"""sanitize.py — Rolling window sanitace MODEL.md a todo.md.

Zachová posledních N session záznamů nebo záznamy mladší než X dní.
Hotové todo backlog položky přesune do archive/. Vše zůstane v gitu.

Použití:
    python3 tools/sanitize.py --target model --keep 5 --dry-run
    python3 tools/sanitize.py --target model --days 30
    python3 tools/sanitize.py --target todo
    python3 tools/sanitize.py --target all --keep 5 --commit

Výstup:
    --json    Strojově čitelný JSON (pro portál)
    výchozí   Human-readable text
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT        = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "archive"
MODEL_MD    = ROOT / "MODEL.md"
TODO_MD     = ROOT / "todo.md"

# ── Pomocné funkce ──────────────────────────────────────────────────────────────

def today() -> datetime.date:
    return datetime.date.today()

def archive_path(prefix: str) -> Path:
    """Vrátí archivní soubor pro aktuální měsíc: archive/{prefix}-YYYY-MM.md"""
    ARCHIVE_DIR.mkdir(exist_ok=True)
    month = today().strftime("%Y-%m")
    return ARCHIVE_DIR / f"{prefix}-{month}.md"

def append_to_archive(path: Path, content: str, section_header: str = ""):
    """Přidá obsah do archivního souboru (vytvoří pokud neexistuje)."""
    if not path.exists():
        path.write_text(
            f"# Archive: {section_header}\n"
            f"# Generováno: {today().isoformat()}\n\n",
            encoding="utf-8"
        )
    with path.open("a", encoding="utf-8") as f:
        f.write(content)


# ── MODEL.md — SESSION LOG ──────────────────────────────────────────────────────

SESSION_LOG_MARKER = "## 📝 SESSION LOG (nejnovější nahoře)\n"
SESSION_ENTRY_RE   = re.compile(r'^(### \d{4}-\d{2}-\d{2})', re.MULTILINE)
SESSION_DATE_RE    = re.compile(r'^### (\d{4}-\d{2}-\d{2})')


def parse_model_md(text: str) -> tuple[str, str, list[str], str]:
    """Rozdělí MODEL.md na 4 části: before_log | log_header | [entries] | after_log."""
    log_start = text.find(SESSION_LOG_MARKER)
    if log_start == -1:
        raise ValueError("SESSION LOG sekce nenalezena v MODEL.md")

    body_start = log_start + len(SESSION_LOG_MARKER)
    sep_idx    = text.find("\n---\n", body_start)
    sep_idx    = sep_idx if sep_idx != -1 else len(text)

    before   = text[:log_start]
    log_body = text[body_start:sep_idx]
    after    = text[sep_idx:]

    # Rozděl na session entries (každá začíná ### YYYY-MM-DD)
    positions = [m.start() for m in SESSION_ENTRY_RE.finditer(log_body)]
    entries   = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(log_body)
        entries.append(log_body[pos:end].rstrip('\n') + '\n\n')

    return before, SESSION_LOG_MARKER, entries, after


def session_date(entry: str) -> datetime.date | None:
    m = SESSION_DATE_RE.match(entry)
    return datetime.date.fromisoformat(m.group(1)) if m else None


def sanitize_model(keep: int | None, days: int | None, dry_run: bool) -> dict:
    """Sanituje SESSION LOG v MODEL.md — zachová keep posledních nebo záznamy mladší než days dní."""
    text = MODEL_MD.read_text(encoding="utf-8")
    before, log_header, entries, after = parse_model_md(text)

    cutoff = (today() - datetime.timedelta(days=days)) if days else None

    kept     = []
    archived = []

    for entry in entries:
        d = session_date(entry)
        if keep is not None and len(kept) < keep:
            kept.append(entry)
        elif cutoff and d and d >= cutoff:
            kept.append(entry)
        else:
            archived.append(entry)

    result = {
        "target":       "model",
        "dry_run":      dry_run,
        "kept":         len(kept),
        "archived":     len(archived),
        "archive_file": None,
        "details":      [],
    }

    if archived:
        result["details"] = [
            SESSION_DATE_RE.match(e).group(0) + " " + e.split("—", 1)[-1].split("\n")[0].strip()
            for e in archived if SESSION_DATE_RE.match(e)
        ]

    if archived and not dry_run:
        arch = archive_path("sessions")
        result["archive_file"] = str(arch.relative_to(ROOT))
        stamp = f"\n<!-- Archivováno: {today().isoformat()} (keep={keep}, days={days}) -->\n\n"
        append_to_archive(arch, stamp + "".join(archived), "SESSION LOG")

        new_text = before + log_header + "\n" + "".join(kept) + after
        MODEL_MD.write_text(new_text, encoding="utf-8")

    return result


# ── todo.md — HOTOVO backlog položky ───────────────────────────────────────────

# Najde celý backlog item (od ### [N] do dalšího ### [N] nebo konce sekce)
BACKLOG_ITEM_RE = re.compile(
    r'(### \[\d+\] .+?)(?=### \[\d+\]|^---|\Z)',
    re.MULTILINE | re.DOTALL
)
HOTOVO_RE = re.compile(r'\*\*Status:\s*HOTOVO\*\*', re.IGNORECASE)
ITEM_TITLE_RE = re.compile(r'^### \[\d+\] (.+)$', re.MULTILINE)


def sanitize_todo(dry_run: bool) -> dict:
    """Přesune HOTOVO backlog položky z todo.md do archive/todo-done-YYYY-MM.md."""
    text = TODO_MD.read_text(encoding="utf-8")

    kept_titles     = []
    archived_items  = []
    archived_titles = []

    for m in BACKLOG_ITEM_RE.finditer(text):
        item = m.group(0)
        title_m = ITEM_TITLE_RE.search(item)
        title = title_m.group(1).strip() if title_m else "?"
        if HOTOVO_RE.search(item):
            archived_items.append(item)
            archived_titles.append(title)
        else:
            kept_titles.append(title)

    result = {
        "target":       "todo",
        "dry_run":      dry_run,
        "kept":         len(kept_titles),
        "archived":     len(archived_items),
        "archive_file": None,
        "details":      archived_titles,
    }

    if archived_items and not dry_run:
        arch = archive_path("todo-done")
        result["archive_file"] = str(arch.relative_to(ROOT))
        stamp = f"\n<!-- Archivováno: {today().isoformat()} -->\n\n"
        append_to_archive(arch, stamp + "".join(archived_items), "TODO DONE")

        # Odstraň archivované položky z textu
        new_text = BACKLOG_ITEM_RE.sub(
            lambda m: "" if HOTOVO_RE.search(m.group(0)) else m.group(0),
            text
        )
        new_text = re.sub(r'\n{4,}', '\n\n\n', new_text)
        TODO_MD.write_text(new_text, encoding="utf-8")

    return result


# ── Git commit ──────────────────────────────────────────────────────────────────

def git_commit(results: list[dict]):
    parts = []
    files = []
    for r in results:
        if r["archived"]:
            parts.append(f"{r['target']}: -{r['archived']} položek")
            if r["target"] == "model":
                files.append(str(MODEL_MD.relative_to(ROOT)))
            elif r["target"] == "todo":
                files.append(str(TODO_MD.relative_to(ROOT)))
            if r.get("archive_file"):
                files.append(r["archive_file"])

    if not parts:
        print("Nic k commitnutí.")
        return

    msg = "chore: sanitize — " + ", ".join(parts)
    subprocess.run(["git", "add"] + files, cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", f"{msg}\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"],
                   cwd=ROOT, check=True)
    print("✓ Git commit vytvořen.")


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sanitace MODEL.md (SESSION LOG) a todo.md (HOTOVO položky)"
    )
    parser.add_argument("--target", choices=["model", "todo", "all"], default="all",
                        help="Co sanitovat (výchozí: all)")
    parser.add_argument("--keep", type=int, default=None,
                        help="Zachovat posledních N session v MODEL.md (výchozí: 10)")
    parser.add_argument("--days", type=int, default=None,
                        help="Zachovat session záznamy mladší než N dní")
    parser.add_argument("--dry-run", action="store_true",
                        help="Pouze ukáže co by se stalo, nic nezmění")
    parser.add_argument("--commit", action="store_true",
                        help="Automaticky commitnout po sanitaci")
    parser.add_argument("--json", dest="json_out", action="store_true",
                        help="Výstup jako JSON (pro API volání z portálu)")
    args = parser.parse_args()

    # Výchozí: keep=10 pokud není zadáno --keep ani --days
    keep = args.keep if args.keep is not None else (10 if args.days is None else None)

    results = []
    if args.target in ("model", "all"):
        results.append(sanitize_model(keep=keep, days=args.days, dry_run=args.dry_run))
    if args.target in ("todo", "all"):
        results.append(sanitize_todo(dry_run=args.dry_run))

    if args.json_out:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    # Human-readable výstup
    prefix = "[DRY-RUN] " if args.dry_run else ""
    for r in results:
        print(f"\n{prefix}{r['target'].upper()}")
        print(f"  Zachováno:   {r['kept']}")
        print(f"  Archivováno: {r['archived']}")
        if r.get("archive_file"):
            print(f"  Archiv:      {r['archive_file']}")
        if r.get("details"):
            print("  Položky:")
            for d in r["details"]:
                print(f"    - {d}")

    if args.commit and not args.dry_run:
        git_commit(results)


if __name__ == "__main__":
    main()
