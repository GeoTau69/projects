#!/usr/bin/env python3
"""Projects Dashboard — živý přehled stavu projektů a systémových módů.

Port: 8099  |  Auto-refresh: 5s
Konfigurace: ~/projects/.systems.json
"""

import json
import subprocess
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent.parent   # ~/projects/
SYSTEMS_FILE = ROOT / '.systems.json'
PORT = 8099

HTML = r"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="5">
<title>Projects Dashboard</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0d1117;
  color: #e6edf3;
  font-family: 'Courier New', monospace;
  padding: 2rem;
  font-size: 14px;
}
h1 { color: #58a6ff; font-size: 1rem; letter-spacing: 3px; margin-bottom: 0.2rem; }
.ts { color: #484f58; font-size: 0.75rem; margin-bottom: 2.5rem; }
section { margin-bottom: 2rem; }
h2 {
  color: #8b949e;
  font-size: 0.7rem;
  letter-spacing: 4px;
  text-transform: uppercase;
  border-bottom: 1px solid #21262d;
  padding-bottom: 0.4rem;
  margin-bottom: 0.75rem;
}
.row {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.45rem 0;
  border-bottom: 1px solid #0d1117;
}
.dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.active   { background: #3fb950; box-shadow: 0 0 6px #3fb95055; }
.inactive { background: #f85149; }
.unknown  { background: #484f58; }
.name { width: 190px; }
.port { color: #58a6ff; width: 60px; font-size: 0.85rem; }
.desc { color: #8b949e; flex: 1; font-size: 0.85rem; }
.badge {
  font-size: 0.7rem;
  padding: 1px 8px;
  border-radius: 3px;
  letter-spacing: 1px;
  min-width: 60px;
  text-align: center;
}
.badge-on  { background: #0d4429; color: #3fb950; }
.badge-off { background: #21262d; color: #484f58; }
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }
</style>
</head>
<body>
<h1>◈ PROJECTS DASHBOARD</h1>
<div class="ts">STAMP</div>
<section>
  <h2>Services</h2>
  SERVICES
</section>
<section>
  <h2>Modes</h2>
  MODES
</section>
</body>
</html>"""


def run_cmd(cmd):
    """Spustí příkaz, vrátí (stdout, returncode)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        return r.stdout.strip(), r.returncode
    except Exception:
        return '', 99


def svc_status(name, user_svc):
    """Vrátí systemd stav služby: 'active', 'inactive', nebo jiný string."""
    cmd = ['systemctl', '--user', 'is-active', name] if user_svc \
          else ['systemctl', 'is-active', name]
    out, _ = run_cmd(cmd)
    return out or 'unknown'


def remote_mode_active():
    """Vrátí True pokud je Tailscale Funnel aktivní (port 8765)."""
    out, code = run_cmd(['tailscale', 'funnel', 'status'])
    if code != 0 or not out:
        return False
    # Aktivní funnel obsahuje URL nebo číslo portu
    return '8765' in out or 'fedora.tail' in out


def load_systems():
    if SYSTEMS_FILE.exists():
        return json.loads(SYSTEMS_FILE.read_text(encoding='utf-8'))
    return {'services': [], 'modes': []}


def build_html():
    data = load_systems()
    ts = datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')

    # --- Services ---
    svc_rows = []
    for s in data.get('services', []):
        st = svc_status(s['systemd'], s.get('user_service', False))
        dot = 'active' if st == 'active' else 'inactive' if st == 'inactive' else 'unknown'
        badge = 'badge-on' if st == 'active' else 'badge-off'
        port = f":{s['port']}" if 'port' in s else ''
        url = s.get('url_public', '')
        link = f' <a href="{url}" target="_blank">↗</a>' if url else ''
        svc_rows.append(
            f'<div class="row">'
            f'<div class="dot {dot}"></div>'
            f'<div class="name">{s["name"]}</div>'
            f'<div class="port">{port}</div>'
            f'<div class="desc">{s.get("description", "")}{link}</div>'
            f'<div class="badge {badge}">{st.upper()}</div>'
            f'</div>'
        )

    # --- Modes ---
    mode_rows = []
    for m in data.get('modes', []):
        if m['id'] == 'remote':
            active = remote_mode_active()
        else:
            cmd = m.get('check_cmd', '').split()
            _, code = run_cmd(cmd) if cmd else ('', 1)
            active = (code == 0)
        dot = 'active' if active else 'inactive'
        badge = 'badge-on' if active else 'badge-off'
        label = 'ON' if active else 'OFF'
        mode_rows.append(
            f'<div class="row">'
            f'<div class="dot {dot}"></div>'
            f'<div class="name">{m["name"]}</div>'
            f'<div class="desc">{m.get("description", "")}</div>'
            f'<div class="badge {badge}">{label}</div>'
            f'</div>'
        )

    return (HTML
            .replace('STAMP', ts)
            .replace('SERVICES', '\n  '.join(svc_rows))
            .replace('MODES', '\n  '.join(mode_rows)))


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # tiché logy

    def do_GET(self):
        if self.path not in ('/', '/index.html'):
            self.send_response(404)
            self.end_headers()
            return
        body = build_html().encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    server = HTTPServer(('', PORT), DashboardHandler)
    print(f'Dashboard: http://localhost:{PORT}/')
    server.serve_forever()
