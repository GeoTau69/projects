#!/usr/bin/env python3
"""
docserver.py — Centrální dokumentační web pro ~/projects/.

Zobrazuje seznam projektů (discovery přes project.yaml) a obsah CLAUDE.md souborů.
Single-page app: sidebar s projekty, hlavní panel s rendered markdown (marked.js).

Port: 8080  |  Bez externích závislostí (stdlib only)
"""

import json
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT       = Path(__file__).parent.parent          # ~/projects/
OUTPUT_DIR = Path(__file__).parent / "output"      # docs/output/
PORT = 8080

STATUS_ICON = {"active": "🟢", "wip": "🟡", "planned": "⚪", "archived": "📦"}

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
        # Čteme YAML bez yaml modulu — jen klíčové řádky (stdlib only)
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
        # Přeskočit listy ([...]) — nejsou potřeba v UI
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
        # Ochrana path traversal — pouze přímé podadresáře ROOT
        candidate = ROOT / dir_param
        if not candidate.resolve().parent == ROOT.resolve():
            return b"403 Forbidden", 403
        md_path = candidate / "CLAUDE.md"

    if not md_path.exists():
        return f"# {dir_param}\n\nCLAUDE.md nenalezen.".encode("utf-8"), 404

    return md_path.read_bytes(), 200


# ── HTTP Handler ───────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<title>Projects Docs</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  background: #0d1117;
  color: #e6edf3;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  display: flex;
  flex-direction: column;
}

/* ── Header ── */
#header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1.25rem;
  background: #161b22;
  border-bottom: 1px solid #21262d;
  flex-shrink: 0;
}
#header h1 {
  color: #58a6ff;
  font-size: 0.9rem;
  letter-spacing: 3px;
  flex: 1;
}
#refresh-btn {
  font-family: inherit;
  font-size: 0.75rem;
  background: #21262d;
  color: #8b949e;
  border: 1px solid #30363d;
  padding: 3px 10px;
  cursor: pointer;
  border-radius: 3px;
  letter-spacing: 1px;
}
#refresh-btn:hover { color: #e6edf3; border-color: #58a6ff; }
#refresh-btn.active { color: #3fb950; border-color: #3fb950; }
#auto-status { font-size: 0.7rem; color: #484f58; }

/* ── Layout ── */
#layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ── Sidebar ── */
#sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #161b22;
  border-right: 1px solid #21262d;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
#sidebar-header {
  padding: 0.75rem 1rem 0.5rem;
  font-size: 0.65rem;
  letter-spacing: 3px;
  color: #484f58;
  text-transform: uppercase;
  border-bottom: 1px solid #21262d;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  cursor: pointer;
  border-bottom: 1px solid #0d1117;
  color: #8b949e;
  font-size: 0.82rem;
  user-select: none;
}
.nav-item:hover { background: #1c2128; color: #e6edf3; }
.nav-item.active { background: #1f2d3d; color: #58a6ff; }
.nav-icon { flex-shrink: 0; width: 16px; text-align: center; }
.nav-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nav-port {
  font-size: 0.65rem;
  color: #484f58;
  flex-shrink: 0;
}
.nav-sep {
  padding: 0.4rem 1rem 0.2rem;
  font-size: 0.6rem;
  letter-spacing: 2px;
  color: #30363d;
  text-transform: uppercase;
}
.nav-doc-link {
  font-size: 0.75rem;
  text-decoration: none;
  opacity: 0.35;
  flex-shrink: 0;
  padding: 0 2px;
  line-height: 1;
}
.nav-item:hover .nav-doc-link { opacity: 1; }

/* ── Main panel ── */
#main {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 2rem;
}
#loading {
  color: #484f58;
  font-size: 0.85rem;
  padding: 2rem;
}
#error-msg {
  color: #f85149;
  font-size: 0.85rem;
  padding: 1rem;
  display: none;
}

/* ── Markdown rendering ── */
#md-content h1 { color: #58a6ff; font-size: 1.4rem; margin: 1rem 0 0.75rem; border-bottom: 1px solid #21262d; padding-bottom: 0.4rem; }
#md-content h2 { color: #79c0ff; font-size: 1.1rem; margin: 1.25rem 0 0.5rem; border-bottom: 1px solid #21262d; padding-bottom: 0.3rem; }
#md-content h3 { color: #a5d6ff; font-size: 0.95rem; margin: 1rem 0 0.4rem; }
#md-content p { color: #c9d1d9; line-height: 1.6; margin: 0.5rem 0; }
#md-content ul, #md-content ol { margin: 0.5rem 0 0.5rem 1.5rem; color: #c9d1d9; line-height: 1.7; }
#md-content li { margin: 0.1rem 0; }
#md-content code {
  background: #1c2128;
  color: #ff7b72;
  padding: 0.1em 0.4em;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 0.88em;
}
#md-content pre {
  background: #1c2128;
  border: 1px solid #30363d;
  border-radius: 4px;
  padding: 1rem;
  overflow-x: auto;
  margin: 0.75rem 0;
}
#md-content pre code {
  background: none;
  color: #e6edf3;
  padding: 0;
  font-size: 0.85rem;
}
#md-content blockquote {
  border-left: 3px solid #30363d;
  margin: 0.5rem 0;
  padding: 0.4rem 1rem;
  color: #8b949e;
}
#md-content strong { color: #e6edf3; }
#md-content em { color: #a5d6ff; }
#md-content table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.75rem 0;
  font-size: 0.85rem;
}
#md-content th {
  background: #1c2128;
  border: 1px solid #30363d;
  padding: 0.4rem 0.75rem;
  color: #8b949e;
  text-align: left;
  font-weight: normal;
  letter-spacing: 1px;
}
#md-content td {
  border: 1px solid #21262d;
  padding: 0.35rem 0.75rem;
  color: #c9d1d9;
}
#md-content tr:hover td { background: #1c2128; }
#md-content a { color: #58a6ff; text-decoration: none; }
#md-content a:hover { text-decoration: underline; }
#md-content hr { border: none; border-top: 1px solid #21262d; margin: 1rem 0; }
/* Skrytí HTML komentářů (SYNC bloky jsou jen pro CLAUDE.md v editoru) */
#md-content .sync-comment { display: none; }
</style>
</head>
<body>

<div id="header">
  <h1>◈ PROJECTS DOCS</h1>
  <span id="auto-status"></span>
  <button id="refresh-btn" onclick="toggleAutoRefresh()">AUTO-REFRESH: OFF</button>
</div>

<div id="layout">
  <nav id="sidebar">
    <div id="sidebar-header">Navigator</div>
    <div id="nav-list">
      <div class="nav-item" style="color:#484f58;font-size:0.75rem;">Načítám...</div>
    </div>
  </nav>

  <main id="main">
    <div id="loading">Vyberte projekt ze seznamu vlevo.</div>
    <div id="error-msg"></div>
    <div id="md-content"></div>
  </main>
</div>

<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"
  onerror="window._markedMissing=true;console.warn('marked.js nedostupný — jsi offline?')">
</script>
<script>
// ── Stav ──────────────────────────────────────────────────────────────────────
let currentDir = null;
let autoRefreshTimer = null;
const AUTO_REFRESH_INTERVAL = 30000; // 30s

// ── Inicializace ──────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  loadProjects();
});

// ── Projekty: sidebar ─────────────────────────────────────────────────────────
async function loadProjects() {
  let projects;
  try {
    const r = await fetch('/api/projects');
    projects = await r.json();
  } catch (e) {
    document.getElementById('nav-list').innerHTML =
      '<div class="nav-item" style="color:#f85149;">Chyba načítání projektů</div>';
    return;
  }

  const nav = document.getElementById('nav-list');
  nav.innerHTML = '';

  // Fixní položky nahoře
  nav.appendChild(makeNavItem('info', 'ℹ️', 'Info', '', null));
  nav.appendChild(makeNavItem('todo', '☑️', 'Todo', '', null));
  nav.appendChild(makeNavItem('master', '📋', 'Overview (master)', '', null));
  nav.appendChild(Object.assign(document.createElement('div'), {
    className: 'nav-sep', textContent: '── projekty ──'
  }));

  for (const p of projects) {
    const portLabel = p.port ? `:${p.port}` : '';
    const liveIcon = p.port_ok === true ? '🟢' : p.port_ok === false ? '🔴' : p.status_icon;
    nav.appendChild(makeNavItem(p.dir, liveIcon, p.dir, portLabel, p));
  }
}

function makeNavItem(dir, icon, label, port, project) {
  const el = document.createElement('div');
  el.className = 'nav-item';
  el.dataset.dir = dir;
  el.title = project ? project.description : 'Master dokumentace (~/projects/CLAUDE.md)';

  const docLink = (project && project.has_html_doc)
    ? `<a class="nav-doc-link" href="/docs/${dir}" target="_blank" title="Otevřít HTML dokumentaci">📖</a>`
    : '';

  el.innerHTML = `
    <span class="nav-icon">${icon}</span>
    <span class="nav-label">${label}</span>
    <span class="nav-port">${port}</span>
    ${docLink}
  `;

  if (project && project.has_html_doc) {
    el.querySelector('.nav-doc-link').addEventListener('click', e => e.stopPropagation());
  }
  el.addEventListener('click', () => selectProject(dir, el));
  return el;
}

// ── Zobrazení markdown ────────────────────────────────────────────────────────
async function selectProject(dir, navEl) {
  // Zvýraznění aktivní položky
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  if (navEl) navEl.classList.add('active');

  currentDir = dir;
  const loading = document.getElementById('loading');
  const errEl   = document.getElementById('error-msg');
  const mdEl    = document.getElementById('md-content');

  loading.textContent = 'Načítám...';
  loading.style.display = 'block';
  errEl.style.display = 'none';
  mdEl.innerHTML = '';

  let mdText;
  try {
    const r = await fetch(`/api/md?dir=${encodeURIComponent(dir)}`);
    mdText = await r.text();
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  } catch (e) {
    loading.style.display = 'none';
    errEl.style.display = 'block';
    errEl.textContent = `Chyba: ${e.message}`;
    return;
  }

  loading.style.display = 'none';

  if (window._markedMissing || typeof marked === 'undefined') {
    // Fallback: surový text (bez renderingu)
    mdEl.innerHTML = `<pre style="white-space:pre-wrap;color:#8b949e;">${escapeHtml(mdText)}</pre>
      <p style="color:#f85149;margin-top:1rem;">⚠ marked.js nedostupný — jsi offline? Markdown není renderován.</p>`;
  } else {
    mdEl.innerHTML = marked.parse(mdText);
  }
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Auto-refresh ──────────────────────────────────────────────────────────────
function toggleAutoRefresh() {
  const btn = document.getElementById('refresh-btn');
  const statusEl = document.getElementById('auto-status');

  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
    btn.textContent = 'AUTO-REFRESH: OFF';
    btn.classList.remove('active');
    statusEl.textContent = '';
  } else {
    autoRefreshTimer = setInterval(() => {
      loadProjects();
      if (currentDir) {
        const active = document.querySelector('.nav-item.active');
        selectProject(currentDir, active);
      }
      statusEl.textContent = `↻ ${new Date().toLocaleTimeString('cs-CZ')}`;
    }, AUTO_REFRESH_INTERVAL);
    btn.textContent = 'AUTO-REFRESH: ON';
    btn.classList.add('active');
    statusEl.textContent = 'každých 30s';
  }
}
</script>
</body>
</html>
"""


class DocsHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # tiché logy

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML.encode("utf-8"))

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

        elif path.startswith("/docs/"):
            # Servírovat HTML z docs/output/{projekt}.html
            projekt = path[6:].strip("/").split("?")[0]  # Strip /docs/ prefix
            if not projekt or "/" in projekt:
                self._send(400, "text/plain; charset=utf-8", b"Invalid projekt")
                return
            html_path = ROOT / "docs" / "output" / f"{projekt}.html"
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
