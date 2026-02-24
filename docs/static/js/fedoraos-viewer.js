/* fedoraos-viewer.js — FedoraOS :8081 SPA logika
   loadPages, selectPage, MD inter-link handling */

let currentFile = null;

window.addEventListener('DOMContentLoaded', () => {
    loadPages();
});

async function loadPages() {
    let pages;
    try {
        const r = await fetch('/api/pages');
        pages = await r.json();
    } catch (e) {
        document.getElementById('nav-list').innerHTML =
            '<div class="nav-item" style="color:var(--red);">Chyba</div>';
        return;
    }

    const nav = document.getElementById('nav-list');
    nav.innerHTML = '';

    for (let i = 0; i < pages.length; i++) {
        const p = pages[i];
        const el = document.createElement('div');
        el.className = 'nav-item';
        el.dataset.file = p.file;

        const num = p.file.match(/^(\d+)-/) ? p.file.match(/^(\d+)-/)[1] : '';

        el.innerHTML = `
            <span class="nav-num">${num}</span>
            <span class="nav-label">${p.label}</span>
        `;
        el.addEventListener('click', () => selectPage(p.file, el));
        nav.appendChild(el);
    }

    // Auto-select MANIFEST.md (rozcestnik)
    if (pages.length > 0) {
        const first = nav.querySelector('.nav-item');
        if (first) selectPage(pages[0].file, first);
    }
}

async function selectPage(file, navEl) {
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    if (navEl) navEl.classList.add('active');

    currentFile = file;
    const loading = document.getElementById('loading');
    const mdEl = document.getElementById('md-content');

    loading.textContent = 'Načítám...';
    loading.style.display = 'block';
    mdEl.innerHTML = '';

    let mdText;
    try {
        const r = await fetch(`/api/md?file=${encodeURIComponent(file)}`);
        mdText = await r.text();
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
    } catch (e) {
        loading.style.display = 'none';
        mdEl.innerHTML = `<p style="color:var(--red);">Chyba: ${e.message}</p>`;
        return;
    }

    loading.style.display = 'none';

    if (window._markedMissing || typeof marked === 'undefined') {
        mdEl.innerHTML = `<pre style="white-space:pre-wrap;color:var(--text2);">${escapeHtml(mdText)}</pre>`;
    } else {
        mdEl.innerHTML = marked.parse(mdText);
        // Zachytit relativní .md linky a přesměrovat na kliknutí v sidebaru
        mdEl.querySelectorAll('a').forEach(a => {
            const href = a.getAttribute('href');
            if (href && href.endsWith('.md') && !href.startsWith('http')) {
                a.addEventListener('click', e => {
                    e.preventDefault();
                    const target = document.querySelector(`.nav-item[data-file="${href}"]`);
                    if (target) selectPage(href, target);
                });
            }
        });
    }
}

function escapeHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
