#!/usr/bin/env python3
"""
docserver.py — Centrální dokumentační web pro ~/projects/.

Zobrazuje seznam projektů (discovery přes project.yaml) a obsah CLAUDE.md souborů.
Single-page app: sidebar s projekty, hlavní panel s rendered markdown (marked.js).

Port: 8080  |  Bez externích závislostí (stdlib only)
"""

import json
import mimetypes
import socket
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT            = Path(__file__).parent.parent          # ~/projects/
DOCS_DIR        = Path(__file__).parent                 # ~/projects/docs/
STATIC_DIR      = DOCS_DIR / "static"
TEMPLATES_DIR   = DOCS_DIR / "templates"
OUTPUT_DIR      = DOCS_DIR / "output"
SANITIZE_SCRIPT = ROOT / "tools" / "sanitize.py"
PORT = 8080

STATUS_ICON = {"active": "🟢", "wip": "🟡", "planned": "⚪", "archived": "📦"}

# ── Načtení šablon při startu ─────────────────────────────────────────────────

HTML = (TEMPLATES_DIR / "shell-docserver.html").read_text(encoding="utf-8")
MAINTENANCE_HTML = (TEMPLATES_DIR / "maintenance.html").read_text(encoding="utf-8")

# ── Discovery ──────────────────────────────────────────────────────────────────

def load_projects() -> list[dict]:
    """Najde všechny adresáře s project.yaml — stejná logika jako info-sync.py."""
    projects = []
    for entry in sorted(ROOT.iterdir()):
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
        yaml_path = entry / "project.yaml"
        if not yaml_path.exists():
            continue
        data = parse_simple_yaml(yaml_path)
        data["_dir"] = entry.name
        data["_has_claude"] = (entry / "CLAUDE.md").exists()
        projects.append(data)
    return projects


def parse_simple_yaml(path: Path) -> dict:
    """Minimalistický YAML parser pro project.yaml (jen skalární hodnoty)."""
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if val.startswith("["):
            continue
        result[key] = val
    return result


def check_port(port) -> bool:
    """Vrátí True pokud port naslouchá."""
    if not port:
        return False
    try:
        with socket.create_connection(("localhost", int(port)), timeout=0.5):
            return True
    except Exception:
        return False


# ── API handlers ───────────────────────────────────────────────────────────────

def api_projects() -> bytes:
    """JSON: seznam projektů s live statusem."""
    projects = load_projects()
    result = []
    for p in projects:
        port = p.get("port", "")
        port_ok = check_port(port) if port else None
        result.append({
            "dir": p["_dir"],
            "name": p.get("display_name", p["_dir"]),
            "status": p.get("status", "planned"),
            "status_icon": STATUS_ICON.get(p.get("status", "planned"), "❓"),
            "port": port,
            "port_ok": port_ok,
            "description": p.get("description", ""),
            "has_claude": p["_has_claude"],
            "has_html_doc": (OUTPUT_DIR / f"{p['_dir']}.html").exists(),
        })
    return json.dumps(result, ensure_ascii=False).encode("utf-8")


def api_md(dir_param: str) -> tuple[bytes, int]:
    """Vrátí surový markdown obsah CLAUDE.md pro daný projekt (nebo master/todo)."""
    if dir_param == "master":
        md_path = ROOT / "CLAUDE.md"
    elif dir_param == "todo":
        md_path = ROOT / "todo.md"
    elif dir_param == "info":
        md_path = ROOT / "docs" / "INFO.md"
    else:
        if "/" in dir_param or dir_param.startswith("."):
            return b"403 Forbidden", 403
        md_path = ROOT / dir_param / "CLAUDE.md"

    if not md_path.exists():
        return f"# {dir_param}\n\nCLAUDE.md nenalezen.".encode("utf-8"), 404

    return md_path.read_bytes(), 200


def api_sanitize(target: str, keep: int | None, days: int | None, dry_run: bool) -> bytes:
    """Spustí tools/sanitize.py, vrátí JSON výsledek."""
    cmd = [sys.executable, str(SANITIZE_SCRIPT), "--target", target, "--json"]
    if keep is not None:
        cmd += ["--keep", str(keep)]
    if days is not None:
        cmd += ["--days", str(days)]
    if dry_run:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=15)
    if r.returncode != 0:
        return json.dumps({"error": r.stderr or "Sanitize script selhal"}, ensure_ascii=False).encode()
    return r.stdout.encode("utf-8")


# ── Static file serving ───────────────────────────────────────────────────────

def serve_static(path: str, project_dir: str | None = None) -> tuple[bytes, int, str]:
    """Servíruje statické soubory. Per-project override: hledá nejdřív v {projekt}/static/,
    pak fallback na docs/static/. Vrátí (body, status, content_type)."""
    clean = path.lstrip("/")
    if ".." in clean:
        return b"403 Forbidden", 403, "text/plain"

    # Per-project override: {projekt}/static/ → docs/static/
    search_dirs = [STATIC_DIR]
    if project_dir:
        proj_static = ROOT / project_dir / "static"
        if proj_static.is_dir():
            search_dirs.insert(0, proj_static)

    for base in search_dirs:
        file_path = base / clean
        if file_path.exists() and file_path.is_file():
            try:
                file_path.resolve().relative_to(base.resolve())
            except ValueError:
                continue
            ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            return file_path.read_bytes(), 200, ctype

    return b"404 Not Found", 404, "text/plain"


# ── HTTP Handler ───────────────────────────────────────────────────────────────

class DocsHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # tiché logy

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/sanitize":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length) or b"{}")
            target = body.get("target", "all")
            keep   = body.get("keep")
            days   = body.get("days")
            data   = api_sanitize(target, keep, days, dry_run=False)
            self._send(200, "application/json; charset=utf-8", data)
        else:
            self._send(404, "text/plain; charset=utf-8", b"Not Found")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML.encode("utf-8"))

        elif path.startswith("/static/"):
            rel = path[len("/static/"):]
            body, status, ctype = serve_static(rel)
            self._send(status, f"{ctype}; charset=utf-8", body)

        elif path == "/api/projects":
            data = api_projects()
            self._send(200, "application/json; charset=utf-8", data)

        elif path == "/api/md":
            dir_param = qs.get("dir", [""])[0].strip()
            if not dir_param:
                self._send(400, "text/plain; charset=utf-8", b"Chybi parametr ?dir=")
                return
            body, status = api_md(dir_param)
            self._send(status, "text/plain; charset=utf-8", body)

        elif path == "/maintenance":
            self._send(200, "text/html; charset=utf-8", MAINTENANCE_HTML.encode("utf-8"))

        elif path == "/api/sanitize":
            target  = qs.get("target", ["all"])[0]
            keep    = int(qs["keep"][0]) if "keep" in qs else None
            days    = int(qs["days"][0]) if "days" in qs else None
            dry_run = qs.get("dry_run", ["0"])[0] == "1"
            data    = api_sanitize(target, keep, days, dry_run=dry_run)
            self._send(200, "application/json; charset=utf-8", data)

        elif path.startswith("/docs/"):
            projekt = path[6:].strip("/").split("?")[0]
            if not projekt or "/" in projekt:
                self._send(400, "text/plain; charset=utf-8", b"Invalid projekt")
                return
            html_path = OUTPUT_DIR / f"{projekt}.html"
            if not html_path.exists():
                self._send(404, "text/plain; charset=utf-8", b"HTML nenalezen pro projekt: " + projekt.encode())
                return
            body = html_path.read_bytes()
            self._send(200, "text/html; charset=utf-8", body)

        else:
            self._send(404, "text/plain; charset=utf-8", b"Not Found")

    def _send(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = HTTPServer(("", PORT), DocsHandler)
    print(f"Docs server: http://localhost:{PORT}/")
    print(f"Root: {ROOT}")
    server.serve_forever()
