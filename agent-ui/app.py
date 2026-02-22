#!/usr/bin/env python3
"""Agent UI — webové rozhraní pro orchestrátor. Port 8100."""

import sys
import os
import subprocess
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import date
from pathlib import Path
from flask import Flask, render_template, request, redirect, jsonify

from _meta.orchestrator import Orchestrator
from _meta.plugins.claude_code import ClaudeCodeBackend
from _meta.plugins.claude import ClaudeBackend
from _meta.plugins.ollama import OllamaBackend
from _meta.billing import init_db
from _meta.router import ROUTING_RULES, CACHE_TTL, LOCAL_MODEL, DEEPSEEK_MODEL
from _meta.conversations import (
    init_conv_db,
    template_list, template_get, template_create, template_update, template_delete,
    conv_list, conv_get, conv_create, conv_rename, conv_close,
    msg_list, msg_last_id, msg_save_user, msg_save_assistant, msg_get_unanswered,
    summary_list, summary_save,
)

app = Flask(__name__)

claude_code_backend = ClaudeCodeBackend()
claude_backend      = ClaudeBackend()
ollama_backend      = OllamaBackend()

orc = Orchestrator()
orc.register(claude_code_backend)
orc.register(claude_backend)
orc.register(ollama_backend)

# Operace s popisem modelu a cache pro UI
_MODEL_LABEL = {
    'local':    f'Qwen ({LOCAL_MODEL})',
    'deepseek': f'DeepSeek ({DEEPSEEK_MODEL})',
    'sonnet':   'Sonnet',
    'opus':     'Opus',
    'haiku':    'Haiku',
}
OPERATIONS = []
for _op, _dest in ROUTING_RULES.items():
    if _op.startswith('_'):
        continue
    _ttl   = CACHE_TTL.get(_op, CACHE_TTL['_default'])
    _cache = f'cache {_ttl}h' if _ttl > 0 else 'bez cache'
    _model = _MODEL_LABEL.get(_dest, _dest)
    OPERATIONS.append({'value': _op, 'label': f'{_op}  ({_model}, {_cache})'})


# ─── Datové funkce ────────────────────────────────────────────────────────────

def billing_today() -> dict:
    try:
        conn  = init_db()
        today = date.today().isoformat()
        row   = conn.execute("""
            SELECT
                COUNT(*)                                          AS total_calls,
                SUM(CASE WHEN cache_hit = 0 THEN 1 ELSE 0 END)  AS real_calls,
                SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END)  AS cache_hits,
                COALESCE(SUM(tokens_in),  0)                     AS total_in,
                COALESCE(SUM(tokens_out), 0)                     AS total_out,
                COALESCE(SUM(cost_usd),   0.0)                   AS total_cost
            FROM token_log
            WHERE DATE(timestamp) = ?
        """, (today,)).fetchone()
        conn.close()
        return dict(row) if row else {}
    except Exception as exc:
        return {'error': str(exc)}


def memory_stats() -> dict:
    stats: dict = {}
    try:
        mem: dict[str, int] = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            parts = line.split()
            if parts:
                mem[parts[0].rstrip(':')] = int(parts[1]) if len(parts) > 1 else 0
        total_kb = mem.get('MemTotal', 0)
        avail_kb = mem.get('MemAvailable', 0)
        used_kb  = total_kb - avail_kb
        stats['ram'] = {
            'total_gb': round(total_kb / 1024 / 1024, 1),
            'used_gb':  round(used_kb  / 1024 / 1024, 1),
            'pct':      int(used_kb / total_kb * 100) if total_kb else 0,
        }
    except Exception as exc:
        stats['ram'] = {'error': str(exc)}

    try:
        r = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.used,memory.total',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            gpus = []
            for line in r.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 3:
                    name, used, total = parts[0], int(parts[1]), int(parts[2])
                    gpus.append({
                        'name':     name,
                        'used_gb':  round(used  / 1024, 1),
                        'total_gb': round(total / 1024, 1),
                        'pct':      int(used / total * 100) if total else 0,
                    })
            stats['gpus'] = gpus
    except Exception:
        pass

    try:
        r = subprocess.run(['ollama', 'ps'], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            lines = r.stdout.strip().splitlines()
            loaded = []
            for line in lines[1:]:
                if line.strip():
                    parts = line.split()
                    loaded.append(parts[0] if parts else line.strip())
            stats['ollama_loaded'] = loaded
    except Exception:
        stats['ollama_loaded'] = []

    return stats


def _detect_backend(model: str) -> str:
    if model.startswith('claude-code/'):
        return 'claude-code'
    if model.startswith('ollama/'):
        return 'ollama'
    return 'claude-api'


def _build_conv_messages(conn, cid: int, new_prompt: str,
                         summary_id: int | None = None) -> list[dict]:
    """Sestaví messages list pro AI z historie konverzace + nového promptu."""
    msgs = msg_list(conn, cid)
    result = []

    # Pokud je vybrán souhrn (pro uzavřenou konverzaci), přidej ho jako system kontext
    if summary_id:
        summs = summary_list(conn, cid)
        for s in summs:
            if s['id'] == summary_id:
                result.append({'role': 'user',
                                'content': f'[Kontext předchozí konverzace]: {s["content"]}'})
                result.append({'role': 'assistant', 'content': 'Rozumím kontextu.'})
                break
    else:
        # Přidej historii (template jako první, pak skutečné zprávy)
        for m in msgs:
            if m['role'] in ('user', 'assistant'):
                result.append({'role': m['role'], 'content': m['content']})

    result.append({'role': 'user', 'content': new_prompt})
    return result


# ─── Background: Souhrny + Auto-název ─────────────────────────────────────────

def _run_summary(cid: int, model_id: str, model_name: str, prompt: str) -> None:
    start = time.time()
    try:
        tmp = Orchestrator()
        if model_name.startswith('ollama/'):
            tmp.register(ollama_backend)
        else:
            tmp.register(claude_code_backend)
            tmp.register(claude_backend)
        resp = tmp.request(
            messages=[{'role': 'user', 'content': prompt}],
            operation='_default',
            project='agent-ui-summary',
            model=model_name,
            notes=f'auto-summary/{model_id}',
        )
        elapsed = int((time.time() - start) * 1000)
        conn = init_conv_db()
        summary_save(conn, cid, model_id, resp.text, elapsed)
        conn.close()
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        conn = init_conv_db()
        summary_save(conn, cid, model_id, f'[Chyba: {exc}]', elapsed)
        conn.close()


def _generate_summaries(cid: int, history_text: str) -> None:
    prompt = (
        'Vytvoř stručný kontextový souhrn následující konverzace (max 200 slov). '
        'Zachovej klíčové informace, závěry a nedokončené úkoly. '
        'Souhrn bude sloužit jako vstupní kontext pro navázání na tuto konverzaci.\n\n'
        + history_text
    )
    for model_id, model_name in [
        ('qwen',     f'ollama/{LOCAL_MODEL}'),
        ('deepseek', f'ollama/{DEEPSEEK_MODEL}'),
        ('haiku',    'haiku'),
    ]:
        threading.Thread(
            target=_run_summary, args=(cid, model_id, model_name, prompt), daemon=True
        ).start()


def _generate_conv_name(cid: int, first_exchange: str) -> None:
    """Generuje název konverzace pomocí Haiku po první odpovědi."""
    start = time.time()
    try:
        tmp = Orchestrator()
        tmp.register(claude_code_backend)
        tmp.register(claude_backend)
        resp = tmp.request(
            messages=[{'role': 'user', 'content':
                       f'Navrhni krátký název (max 5 slov, česky) pro tuto konverzaci:\n{first_exchange}'}],
            operation='_default',
            project='agent-ui-naming',
            model='haiku',
            notes='auto-name',
        )
        name = resp.text.strip().strip('"\'').strip()[:100]
        conn = init_conv_db()
        conv_rename(conn, cid, name)
        conn.close()
    except Exception:
        pass


# ─── Routes: Dashboard ────────────────────────────────────────────────────────

@app.route('/')
def index():
    billing = billing_today()
    return render_template('index.html', billing=billing)


@app.route('/status')
def status():
    backends = [
        {'name': 'Claude Code (Pro/Max)', 'id': 'claude-code',
         'available': claude_code_backend.is_available(), 'models': ['opus', 'sonnet', 'haiku'],
         'note': 'CLI · bez API klíče'},
        {'name': 'Claude API (Anthropic)', 'id': 'claude',
         'available': claude_backend.is_available(), 'models': ['opus', 'sonnet', 'haiku'],
         'note': 'ANTHROPIC_API_KEY'},
        {'name': f'Ollama / {LOCAL_MODEL}', 'id': 'ollama-qwen',
         'available': ollama_backend.is_available(), 'models': [LOCAL_MODEL],
         'note': 'lokální · zdarma'},
        {'name': f'Ollama / {DEEPSEEK_MODEL}', 'id': 'ollama-deepseek',
         'available': ollama_backend.is_available(), 'models': [DEEPSEEK_MODEL],
         'note': 'lokální · zdarma'},
    ]
    return render_template('partials/status.html', backends=backends)


@app.route('/memory')
def memory():
    return render_template('partials/memory.html', mem=memory_stats())


@app.route('/memory/header')
def memory_header():
    return render_template('partials/memory_header.html', mem=memory_stats())


# ─── Routes: Stats ────────────────────────────────────────────────────────────

@app.route('/stats')
def stats():
    try:
        conn = init_db()
        rows = conn.execute("""
            SELECT timestamp, project, operation, model,
                   tokens_in, tokens_out, cost_usd, cache_hit, notes
            FROM token_log ORDER BY timestamp DESC LIMIT 50
        """).fetchall()
        history = [dict(r) for r in rows]
        daily = conn.execute("""
            SELECT DATE(timestamp) AS day, COUNT(*) AS calls,
                   SUM(CASE WHEN cache_hit=1 THEN 1 ELSE 0 END) AS cache_hits,
                   COALESCE(SUM(tokens_in),0) AS tokens_in,
                   COALESCE(SUM(tokens_out),0) AS tokens_out,
                   COALESCE(SUM(cost_usd),0.0) AS cost
            FROM token_log GROUP BY DATE(timestamp)
            ORDER BY day DESC LIMIT 7
        """).fetchall()
        daily = [dict(r) for r in daily]
        summary = conn.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN cache_hit=1 THEN 1 ELSE 0 END) AS hits,
                   COALESCE(SUM(cost_usd),0.0) AS total_cost
            FROM token_log
        """).fetchone()
        conn.close()
        return render_template('stats.html', history=history, daily=daily,
                               summary=dict(summary))
    except Exception as exc:
        return render_template('stats.html', history=[], daily=[],
                               summary={}, error=str(exc))


# ─── Routes: Templates ────────────────────────────────────────────────────────

@app.route('/templates')
def templates():
    conn = init_conv_db()
    tmpl = template_list(conn)
    conn.close()
    return render_template('templates_list.html', templates=tmpl)


@app.route('/templates/new', methods=['POST'])
def template_new():
    name    = request.form.get('name', '').strip()
    content = request.form.get('content', '').strip()
    if name and content:
        conn = init_conv_db()
        template_create(conn, name, content)
        conn.close()
    return redirect('/templates')


@app.route('/templates/<int:tid>/edit', methods=['GET', 'POST'])
def template_edit(tid):
    conn = init_conv_db()
    if request.method == 'POST':
        name    = request.form.get('name', '').strip()
        content = request.form.get('content', '').strip()
        if name and content:
            template_update(conn, tid, name, content)
        conn.close()
        return redirect('/templates')
    tmpl = template_get(conn, tid)
    conn.close()
    return render_template('template_edit.html', tmpl=tmpl)


@app.route('/templates/<int:tid>/delete', methods=['POST'])
def template_del(tid):
    conn = init_conv_db()
    template_delete(conn, tid)
    conn.close()
    return redirect('/templates')


# ─── Routes: Conversations ────────────────────────────────────────────────────

@app.route('/conversations')
def conversations():
    conn = init_conv_db()
    convs = conv_list(conn)
    conn.close()
    return render_template('conversations.html', convs=convs)


@app.route('/conversations/new', methods=['POST'])
def conv_new():
    conn = init_conv_db()
    cid  = conv_create(conn)
    conn.close()
    return redirect(f'/ask?conv={cid}')


@app.route('/conversations/<int:cid>/context')
def conv_context(cid):
    """HTMX partial: načte kontext konverzace (unanswered prompt, souhrny)."""
    conn = init_conv_db()
    conv     = conv_get(conn, cid)
    msgs     = msg_list(conn, cid)
    summs    = summary_list(conn, cid)
    unanswered = msg_get_unanswered(conn, cid)
    conn.close()
    return render_template('partials/conv_context.html',
                           conv=conv, msgs=msgs, summaries=summs,
                           unanswered=unanswered)


@app.route('/conversations/<int:cid>/messages')
def conv_messages_view(cid):
    """Zobrazí historii zpráv konverzace."""
    conn  = init_conv_db()
    conv  = conv_get(conn, cid)
    msgs  = msg_list(conn, cid)
    summs = summary_list(conn, cid)
    conn.close()
    return render_template('partials/conv_messages.html',
                           conv=conv, msgs=msgs, summaries=summs)


@app.route('/conversations/<int:cid>/close', methods=['POST'])
def conv_close_route(cid):
    conn = init_conv_db()
    conv_close(conn, cid)
    msgs = msg_list(conn, cid)
    conn.close()
    # Historie jako text pro souhrn
    history = '\n'.join(
        f"[{m['role'].upper()}]: {m['content']}"
        for m in msgs if not m.get('is_template') and m.get('content')
    )
    threading.Thread(
        target=_generate_summaries, args=(cid, history), daemon=True
    ).start()
    return redirect(f'/conversations')


@app.route('/conversations/<int:cid>/summaries')
def conv_summaries_view(cid):
    """HTMX partial: stav souhrnů (polling)."""
    conn  = init_conv_db()
    summs = summary_list(conn, cid)
    conn.close()
    return render_template('partials/summaries.html', summaries=summs, conv_id=cid)


@app.route('/conversations/<int:cid>/rename', methods=['POST'])
def conv_rename_route(cid):
    name = request.form.get('name', '').strip()
    if name:
        conn = init_conv_db()
        conv_rename(conn, cid, name)
        conn.close()
    return redirect(f'/conversations')


# ─── Routes: Ask ──────────────────────────────────────────────────────────────

@app.route('/ask', methods=['GET'])
def ask_get():
    conv_id = request.args.get('conv', type=int)
    conn    = init_conv_db()
    convs   = conv_list(conn)
    tmpls   = template_list(conn)
    conv    = conv_get(conn, conv_id) if conv_id else None
    msgs    = msg_list(conn, conv_id) if conv_id else []
    summs   = summary_list(conn, conv_id) if conv_id else []
    unanswered = msg_get_unanswered(conn, conv_id) if conv_id else None
    conn.close()
    return render_template('ask.html',
                           operations=OPERATIONS, conversations=convs,
                           templates=tmpls, active_conv=conv,
                           conv_messages=msgs, summaries=summs,
                           unanswered=unanswered)


@app.route('/ask', methods=['POST'])
def ask_post():
    prompt        = request.form.get('prompt', '').strip()
    operation     = request.form.get('operation', '_default')
    project       = request.form.get('project', 'agent-ui').strip() or 'agent-ui'
    model         = request.form.get('model', 'auto')
    backend_force = request.form.get('backend_force', 'auto')
    conv_id       = request.form.get('conv_id', type=int)
    template_id   = request.form.get('template_id', type=int)
    summary_id    = request.form.get('summary_id', type=int)

    if not prompt:
        return render_template('partials/response.html',
                               error='Prompt nesmí být prázdný.', response=None)

    conn       = init_conv_db()
    msg_id     = None
    is_new_conv = False

    # ── Uložení promptu do DB ────────────────────────────────────────────────
    if conv_id:
        parent_id = msg_last_id(conn, conv_id)
        # Pokud je to první zpráva a je vybrán template, ulož template jako první záznam
        if template_id and not msg_list(conn, conv_id):
            tmpl = template_get(conn, template_id)
            if tmpl:
                msg_save_user(conn, conv_id, tmpl['content'],
                              parent_id=None, is_template=True)
                parent_id = msg_last_id(conn, conv_id)
        msg_id = msg_save_user(conn, conv_id, prompt, parent_id=parent_id)
        is_new_conv = (parent_id is None or
                       (parent_id is not None and
                        len([m for m in msg_list(conn, conv_id)
                             if m['role'] == 'user' and not m['is_template']]) == 1))

    # ── Sestavení messages pro AI ────────────────────────────────────────────
    if conv_id:
        messages = _build_conv_messages(conn, conv_id, prompt, summary_id)
    else:
        messages = [{'role': 'user', 'content': prompt}]

    # ── Přidat system prompt z template (pokud není v historii) ──────────────
    system = None
    if template_id and not conv_id:
        tmpl = template_get(conn, template_id)
        if tmpl:
            system = tmpl['content']

    conn.close()

    # ── Výběr orchestrátoru dle backend_force ────────────────────────────────
    _BACKEND_MAP = {'claude-code': 'claude-code', 'claude-api': 'claude', 'ollama': 'ollama'}
    if backend_force != 'auto' and backend_force in _BACKEND_MAP:
        forced_name = _BACKEND_MAP[backend_force]
        active_orc  = Orchestrator()
        for b in orc.backends:
            if b.name == forced_name:
                active_orc.register(b)
    else:
        active_orc = orc

    start = time.time()
    try:
        resp = active_orc.request(
            messages=messages,
            operation=operation,
            project=project,
            model=model,
            system=system,
            notes=f'agent-ui/{backend_force}',
        )
        elapsed_ms = int((time.time() - start) * 1000)

        # ── Uložení odpovědi do DB ───────────────────────────────────────────
        if conv_id and msg_id:
            conn = init_conv_db()
            msg_save_assistant(conn, conv_id, msg_id, resp.text,
                               resp.model, _detect_backend(resp.model),
                               resp.tokens_in, resp.tokens_out,
                               resp.cost, elapsed_ms)
            conv = conv_get(conn, conv_id)
            conn.close()
            # Auto-název po první skutečné odpovědi
            if is_new_conv and (not conv or not conv.get('name')):
                snippet = f'Dotaz: {prompt[:200]}\nOdpověď: {resp.text[:200]}'
                threading.Thread(
                    target=_generate_conv_name, args=(conv_id, snippet), daemon=True
                ).start()

        return render_template('partials/response.html', response=resp,
                               error=None, elapsed_ms=elapsed_ms)
    except Exception as exc:
        return render_template('partials/response.html', error=str(exc),
                               response=None, elapsed_ms=None)


if __name__ == '__main__':
    print('Agent UI: http://localhost:8100/')
    app.run(host='0.0.0.0', port=8100, debug=False)
