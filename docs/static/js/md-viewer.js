/* md-viewer.js — Docserver :8080 SPA logika
   loadProjects, selectProject, autoRefresh, escapeHtml, navigace */

// ── Stav ──
let currentDir = null;
let autoRefreshTimer = null;
const AUTO_REFRESH_INTERVAL = 30000; // 30s

// ── Inicializace ──
window.addEventListener('DOMContentLoaded', () => {
    loadProjects();
});

// ── Projekty: sidebar ──
async function loadProjects() {
    let projects;
    try {
        const r = await fetch('/api/projects');
        projects = await r.json();
    } catch (e) {
        document.getElementById('nav-list').innerHTML =
            '<div class="nav-item" style="color:var(--red);">Chyba načítání projektů</div>';
        return;
    }

    const nav = document.getElementById('nav-list');
    nav.innerHTML = '';

    // ── PORTÁL ──
    nav.appendChild(makeSep('portál'));
    nav.appendChild(makeNavItem('master', '📋', 'Workspace', '', null));
    nav.appendChild(makeNavItem('todo', '☑️', 'Backlog', '', null));

    // ── SLUŽBY (mají port) ──
    const services = projects.filter(p => p.port);
    const libraries = projects.filter(p => !p.port);

    nav.appendChild(makeSep('služby'));
    for (const p of services) {
        const portLabel = `:${p.port}`;
        const liveIcon = p.port_ok === true ? '🟢' : p.port_ok === false ? '🔴' : p.status_icon;
        nav.appendChild(makeNavItem(p.dir, liveIcon, p.dir, portLabel, p));
    }

    // ── KNIHOVNY (nemají port) ──
    nav.appendChild(makeSep('knihovny'));
    for (const p of libraries) {
        const liveIcon = p.status_icon;
        nav.appendChild(makeNavItem(p.dir, liveIcon, p.dir, '', p));
    }
}

function makeSep(text) {
    return Object.assign(document.createElement('div'), {
        className: 'nav-sep', textContent: `── ${text} ──`
    });
}

function makeNavItem(dir, icon, label, port, project) {
    const el = document.createElement('div');
    el.className = 'nav-item';
    el.dataset.dir = dir;
    el.title = project ? project.description : '';

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

// ── Zobrazení markdown ──
async function selectProject(dir, navEl) {
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
        mdEl.innerHTML = `<pre style="white-space:pre-wrap;color:var(--text2);">${escapeHtml(mdText)}</pre>
            <p style="color:var(--red);margin-top:1rem;">⚠ marked.js nedostupný — jsi offline? Markdown není renderován.</p>`;
    } else {
        mdEl.innerHTML = marked.parse(mdText);
    }
}

function escapeHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Auto-refresh ──
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
