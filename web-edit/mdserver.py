#!/usr/bin/env python3
"""
Micro MD Collaborative Editor
Requires: pip install aiohttp
Usage:    python3 code/mdserver.py [directory] [port]
Default:  python3 code/mdserver.py .. 8765
          (when run from code/, serves parent directory)
"""

import asyncio
import datetime
import json
import pathlib
import sys

try:
    import aiohttp
    from aiohttp import web
except ImportError:
    print("Chybí aiohttp. Instaluji...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp"])
    import aiohttp
    from aiohttp import web

ROOT = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else pathlib.Path(__file__).parent.parent.resolve()
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
BACKUP_DIR = ROOT / 'tmp'

# Subdirectories to exclude from file listing
EXCLUDED_DIRS = {'code', 'tmp', 'verze', '.claude'}

# { filename: set of WebSocketResponse }
rooms: dict[str, set] = {}

# ─── HTML ─────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MD Editor · ConWare</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: system-ui, -apple-system, sans-serif;
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: #1e1e2e;
    color: #cdd6f4;
    overflow: hidden;
  }

  /* ── Top bar ── */
  .topbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 14px;
    background: #181825;
    border-bottom: 1px solid #313244;
    flex-shrink: 0;
    min-height: 40px;
  }
  .topbar select {
    padding: 3px 8px;
    background: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    font-size: 13px;
    max-width: 340px;
  }
  .btn {
    padding: 3px 14px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
  }
  .btn-save { background: #a6e3a1; color: #1e1e2e; }
  .btn-save:hover { background: #94d3a2; }
  .btn-save.saved { background: #89dceb; }
  .btn-save.saving { background: #fab387; color: #1e1e2e; }
  .btn-saveas { background: #cba6f7; color: #1e1e2e; }
  .btn-saveas:hover { background: #b490e0; }
  .btn-shutdown { background: #f38ba8; color: #1e1e2e; margin-left: auto; }
  .btn-shutdown:hover { background: #e06c88; }

  .status {
    font-size: 11px;
    padding: 2px 10px;
    border-radius: 10px;
    font-weight: 600;
    white-space: nowrap;
  }
  .status.online  { background: #a6e3a1; color: #1e1e2e; }
  .status.offline { background: #f38ba8; color: #1e1e2e; }

  .users { font-size: 12px; color: #a6adc8; margin-left: auto; white-space: nowrap; }

  /* ── Split panes ── */
  .panes {
    display: flex;
    flex: 1;
    overflow: hidden;
  }
  .pane {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    flex: 1;
  }
  .pane-label {
    padding: 4px 12px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    background: #181825;
    border-bottom: 1px solid #313244;
    color: #6c7086;
    flex-shrink: 0;
  }

  /* ── Divider ── */
  .divider {
    width: 5px;
    background: #313244;
    cursor: col-resize;
    flex-shrink: 0;
    transition: background 0.15s;
  }
  .divider:hover, .divider.dragging { background: #89b4fa; }

  /* ── Editor ── */
  #editor {
    flex: 1;
    width: 100%;
    background: #1e1e2e;
    color: #cdd6f4;
    border: none;
    outline: none;
    padding: 20px 24px;
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
    font-size: 13.5px;
    line-height: 1.75;
    resize: none;
    tab-size: 2;
  }
  #editor::placeholder { color: #45475a; }

  /* ── Preview iframe ── */
  #preview-frame {
    flex: 1;
    border: none;
    background: white;
  }

  /* ── Filename tag ── */
  .filetag {
    font-size: 12px;
    color: #89b4fa;
    font-weight: 600;
    max-width: 240px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
</head>
<body>

<div class="topbar">
  <select id="file-select" onchange="loadFile()">
    <option value="">— vyberte soubor —</option>
  </select>
  <span class="filetag" id="filetag"></span>
  <button class="btn btn-save" id="save-btn" onclick="saveFile()" title="Ctrl+S">Uložit</button>
  <button class="btn btn-saveas" id="saveas-btn" onclick="saveAsFile()" title="Uložit jako">Uložit jako</button>
  <span class="status offline" id="ws-status">Offline</span>
  <span class="users" id="users-info"></span>
  <button class="btn btn-shutdown" onclick="shutdownServer()">Ukončit</button>
</div>

<div class="panes" id="panes">
  <div class="pane" id="pane-left" style="width:50%">
    <div class="pane-label">✏ Markdown editor</div>
    <textarea id="editor" spellcheck="false" placeholder="Vyberte .md soubor ze seznamu výše…"></textarea>
  </div>
  <div class="divider" id="divider"></div>
  <div class="pane" id="pane-right">
    <div class="pane-label">👁 HTML preview</div>
    <iframe id="preview-frame" sandbox="allow-same-origin"></iframe>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
// ─── Marked setup ─────────────────────────────────────────────────────────────
marked.setOptions({ breaks: true, gfm: true });

// ─── ConWare preview CSS ──────────────────────────────────────────────────────
const PREVIEW_CSS = `
  :root {
    --primary: #1a3a5c;
    --accent: #0078d4;
    --accent-light: #e8f3fc;
    --text: #2c3e50;
    --muted: #6c757d;
    --border: #dee2e6;
    --success: #1a7a4a;
    --bg: #f8f9fa;
    --white: #ffffff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-size: 14px;
    line-height: 1.75;
    color: var(--text);
    background: var(--white);
    padding: 32px 48px;
    max-width: 960px;
    margin: 0 auto;
  }
  h1 {
    font-size: 26px; color: var(--primary);
    margin-bottom: 16px; padding-bottom: 10px;
    border-bottom: 3px solid var(--accent);
  }
  h2 {
    font-size: 20px; color: var(--primary);
    border-bottom: 2px solid var(--accent);
    padding-bottom: 8px; margin: 44px 0 16px;
    scroll-margin-top: 20px;
  }
  h2:first-child { margin-top: 0; }
  h3 { font-size: 16px; color: var(--primary); margin: 26px 0 10px; font-weight: 600; }
  h4 { font-size: 14px; color: var(--text); margin: 16px 0 8px; font-weight: 600; }
  p { margin-bottom: 12px; }
  ul, ol { margin: 8px 0 14px 22px; }
  li { margin-bottom: 3px; }
  strong { font-weight: 700; }
  em { font-style: italic; }
  code {
    background: #f0f4f8; padding: 1px 5px; border-radius: 3px;
    font-family: 'Consolas', monospace; font-size: 12px; color: #c0392b;
  }
  pre {
    background: #1e1e2e; color: #cdd6f4;
    padding: 16px; border-radius: 6px; overflow-x: auto; margin: 12px 0;
  }
  pre code { background: none; color: inherit; padding: 0; }
  table { width: 100%; border-collapse: collapse; margin: 16px 0 24px; font-size: 13px; }
  thead tr { background: var(--primary); color: #fff; }
  thead th { padding: 10px 14px; text-align: left; font-weight: 600; font-size: 12px; }
  tbody tr:nth-child(even) { background: var(--bg); }
  tbody td { padding: 9px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
  blockquote {
    border-left: 4px solid var(--accent);
    padding: 10px 16px; margin: 12px 0;
    background: var(--accent-light); border-radius: 0 4px 4px 0;
  }
  hr { border: none; border-top: 1px solid var(--border); margin: 36px 0; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
`;

// ─── State ────────────────────────────────────────────────────────────────────
let ws = null;
let currentFile = null;
let debounceTimer = null;
let isRemoteUpdate = false;
let autoSaveTimer = null;
let lastSavedContent = null;

// ─── Preview ──────────────────────────────────────────────────────────────────
function renderPreview(md) {
  const frame = document.getElementById('preview-frame');
  const doc = frame.contentDocument || frame.contentWindow.document;
  const scrollY = doc.documentElement ? doc.documentElement.scrollTop : 0;
  const html = marked.parse(md || '');
  doc.open();
  doc.write(`<!DOCTYPE html><html><head>
    <meta charset="UTF-8">
    <style>${PREVIEW_CSS}</style>
  </head><body>${html}</body></html>`);
  doc.close();
  requestAnimationFrame(() => {
    if (doc.documentElement) doc.documentElement.scrollTop = scrollY;
  });
}

// ─── File list ────────────────────────────────────────────────────────────────
async function loadFileList(selectFile) {
  const res = await fetch('/api/files');
  const files = await res.json();
  const sel = document.getElementById('file-select');
  // Keep first placeholder option, remove rest
  while (sel.options.length > 1) sel.remove(1);
  files.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f;
    opt.textContent = f;
    sel.appendChild(opt);
  });
  if (selectFile && files.includes(selectFile)) {
    sel.value = selectFile;
    loadFile();
  } else if (files.length === 1) {
    sel.value = files[0];
    loadFile();
  }
}

async function loadFile() {
  const sel = document.getElementById('file-select');
  const file = sel.value;
  if (!file) return;
  currentFile = file;
  document.getElementById('filetag').textContent = file;

  const res = await fetch(`/api/content?file=${encodeURIComponent(file)}`);
  const data = await res.json();
  document.getElementById('editor').value = data.content;
  lastSavedContent = data.content;
  renderPreview(data.content);
  connectWS(file);
  startAutoBackup();
}

// ─── Save ─────────────────────────────────────────────────────────────────────
async function saveFile() {
  if (!currentFile) return;
  const btn = document.getElementById('save-btn');
  btn.textContent = 'Ukládám…';
  btn.className = 'btn btn-save saving';
  await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file: currentFile, content: document.getElementById('editor').value })
  });
  lastSavedContent = document.getElementById('editor').value;
  btn.textContent = 'Uloženo ✓';
  btn.className = 'btn btn-save saved';
  setTimeout(() => { btn.textContent = 'Uložit'; btn.className = 'btn btn-save'; }, 1800);
}

// ─── Save As ──────────────────────────────────────────────────────────────────
async function saveAsFile() {
  if (!currentFile) return;
  let newName = prompt('Nový název souboru:', currentFile);
  if (!newName) return;
  if (!newName.endsWith('.md')) newName += '.md';

  const res = await fetch('/api/save-as', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file: currentFile,
      new_name: newName,
      content: document.getElementById('editor').value
    })
  });
  const data = await res.json();
  if (data.ok) {
    await loadFileList(newName);
  } else {
    alert('Chyba: ' + (data.error || 'neznámá'));
  }
}

// ─── Shutdown ─────────────────────────────────────────────────────────────────
async function shutdownServer() {
  if (!confirm('Opravdu ukončit server?')) return;
  await fetch('/api/shutdown', { method: 'POST' });
  document.getElementById('ws-status').textContent = 'Server ukončen';
  document.getElementById('ws-status').className = 'status offline';
}

// ─── Editor events ────────────────────────────────────────────────────────────
document.getElementById('editor').addEventListener('input', () => {
  const content = document.getElementById('editor').value;
  renderPreview(content);
  if (isRemoteUpdate) return;

  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'update', content }));
    }
  }, 250);
});

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault();
    saveFile();
  }
});

// ─── Auto-backup every 60s (only if content changed) ─────────────────────────
function startAutoBackup() {
  if (autoSaveTimer) clearInterval(autoSaveTimer);
  autoSaveTimer = setInterval(async () => {
    if (!currentFile) return;
    const content = document.getElementById('editor').value;
    if (content !== lastSavedContent) {
      lastSavedContent = content;
      await fetch('/api/auto-backup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file: currentFile, content })
      });
    }
  }, 60000);
}

// ─── WebSocket ────────────────────────────────────────────────────────────────
function connectWS(file) {
  if (ws) { ws.onclose = null; ws.close(); }
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws?file=${encodeURIComponent(file)}`);

  ws.onopen = () => {
    document.getElementById('ws-status').textContent = 'Online';
    document.getElementById('ws-status').className = 'status online';
  };

  ws.onclose = () => {
    document.getElementById('ws-status').textContent = 'Offline';
    document.getElementById('ws-status').className = 'status offline';
    document.getElementById('users-info').textContent = '';
    setTimeout(() => { if (currentFile) connectWS(currentFile); }, 3000);
  };

  ws.onerror = () => ws.close();

  ws.onmessage = ({ data }) => {
    const msg = JSON.parse(data);
    if (msg.type === 'update') {
      isRemoteUpdate = true;
      const editor = document.getElementById('editor');
      const pos = editor.selectionStart;
      editor.value = msg.content;
      editor.selectionStart = editor.selectionEnd = Math.min(pos, msg.content.length);
      renderPreview(msg.content);
      isRemoteUpdate = false;
    } else if (msg.type === 'users') {
      document.getElementById('users-info').textContent =
        msg.count > 1 ? `👥 ${msg.count} uživatelé` : '';
    }
  };
}

// ─── Resizable divider ────────────────────────────────────────────────────────
(function () {
  const div = document.getElementById('divider');
  const panes = document.getElementById('panes');
  const left = document.getElementById('pane-left');
  let dragging = false;

  div.addEventListener('mousedown', e => {
    dragging = true;
    div.classList.add('dragging');
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const rect = panes.getBoundingClientRect();
    const pct = Math.max(20, Math.min(80, ((e.clientX - rect.left) / rect.width) * 100));
    left.style.flex = 'none';
    left.style.width = pct + '%';
  });
  document.addEventListener('mouseup', () => {
    dragging = false;
    div.classList.remove('dragging');
  });
})();

// ─── Init ─────────────────────────────────────────────────────────────────────
loadFileList();
</script>
</body>
</html>
"""

# ─── Helpers ─────────────────────────────────────────────────────────────────
def safe_path(filename: str) -> pathlib.Path:
    """Resolve path and ensure it stays within ROOT and is a .md file."""
    path = (ROOT / pathlib.Path(filename).name).resolve()
    if path.parent != ROOT or path.suffix.lower() != '.md':
        raise web.HTTPForbidden(reason="Access denied")
    return path


def create_backup(path: pathlib.Path):
    """Create a timestamped backup in BACKUP_DIR before overwriting."""
    if not path.exists():
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    stem = path.stem
    ts = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    backup_name = f"{stem}_{ts}.md"
    backup_path = BACKUP_DIR / backup_name
    backup_path.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')


async def broadcast(filename: str, msg: dict, exclude=None):
    dead = set()
    for client in list(rooms.get(filename, set())):
        if client is exclude:
            continue
        if client.closed:
            dead.add(client)
            continue
        try:
            await client.send_json(msg)
        except Exception:
            dead.add(client)
    rooms.get(filename, set()).difference_update(dead)


async def broadcast_users(filename: str):
    count = len(rooms.get(filename, set()))
    await broadcast(filename, {"type": "users", "count": count})

# ─── Handlers ────────────────────────────────────────────────────────────────
async def handle_root(request):
    return web.Response(text=HTML, content_type='text/html', charset='utf-8')


async def handle_files(request):
    files = sorted(f.name for f in ROOT.glob('*.md'))
    return web.json_response(files)


async def handle_content(request):
    filename = request.rel_url.query.get('file', '')
    path = safe_path(filename)
    content = path.read_text(encoding='utf-8')
    return web.json_response({'content': content})


async def handle_save(request):
    data = await request.json()
    path = safe_path(data.get('file', ''))
    content = data.get('content', '')
    create_backup(path)
    path.write_text(content, encoding='utf-8')
    return web.json_response({'ok': True})


async def handle_auto_backup(request):
    """Save timestamped backup to tmp/ only if content differs from disk."""
    data = await request.json()
    path = safe_path(data.get('file', ''))
    content = data.get('content', '')
    # Compare with what's on disk
    disk_content = path.read_text(encoding='utf-8') if path.exists() else ''
    if content != disk_content:
        BACKUP_DIR.mkdir(exist_ok=True)
        stem = path.stem
        ts = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
        backup_name = f"{stem}_{ts}.md"
        (BACKUP_DIR / backup_name).write_text(content, encoding='utf-8')
        return web.json_response({'ok': True, 'backup': backup_name})
    return web.json_response({'ok': True, 'backup': None})


async def handle_save_as(request):
    data = await request.json()
    new_name = data.get('new_name', '')
    content = data.get('content', '')
    try:
        new_path = safe_path(new_name)
    except web.HTTPForbidden:
        return web.json_response({'ok': False, 'error': 'Neplatný název souboru'})
    if new_path.exists():
        return web.json_response({'ok': False, 'error': 'Soubor již existuje'})
    new_path.write_text(content, encoding='utf-8')
    return web.json_response({'ok': True})


async def handle_shutdown(request):
    """Shut down the server after sending response."""
    import os
    resp = web.json_response({'ok': True})
    await resp.prepare(request)
    await resp.write_eof()
    os._exit(0)


async def handle_ws(request):
    filename = request.rel_url.query.get('file', '')
    if not filename:
        raise web.HTTPBadRequest()

    ws_resp = web.WebSocketResponse(heartbeat=30)
    await ws_resp.prepare(request)

    rooms.setdefault(filename, set()).add(ws_resp)
    await broadcast_users(filename)

    try:
        async for msg in ws_resp:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get('type') == 'update':
                    content = data.get('content', '')
                    await broadcast(filename, {'type': 'update', 'content': content}, exclude=ws_resp)
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                break
    finally:
        rooms.get(filename, set()).discard(ws_resp)
        await broadcast_users(filename)

    return ws_resp

# ─── App ─────────────────────────────────────────────────────────────────────
def main():
    app = web.Application()
    app.router.add_get('/',            handle_root)
    app.router.add_get('/api/files',   handle_files)
    app.router.add_get('/api/content', handle_content)
    app.router.add_post('/api/save',   handle_save)
    app.router.add_post('/api/save-as', handle_save_as)
    app.router.add_post('/api/auto-backup', handle_auto_backup)
    app.router.add_post('/api/shutdown', handle_shutdown)
    app.router.add_get('/ws',          handle_ws)

    print(f"\n  MD Collaborative Editor")
    print(f"  ──────────────────────────────────────")
    print(f"  Adresář : {ROOT}")
    print(f"  Lokálně : http://localhost:{PORT}")
    print(f"  Tailscale: http://<tvoje-ts-ip>:{PORT}")
    print(f"\n  Ctrl+S = uložit  |  tažením středního okraje = resize\n")

    web.run_app(app, host='0.0.0.0', port=PORT, print=lambda *_: None)


if __name__ == '__main__':
    main()
