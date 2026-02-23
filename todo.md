# AI Dev Agent Stack — Vývojový backlog

> Aktualizováno: 2026-02-22
> Účel: Živý backlog vývoje workspace.

---

## BACKLOG — prioritní pořadí

### [1] DOKUMENTACE — nová architektura (AI generuje minimum)
**Priorita: NEJVYŠŠÍ**
**Status: HOTOVO**

Fáze A (framework) ✅ + Fáze B (migrace) ✅ — všechny projekty dokumentovány:
ai, backup-dashboard, dashboard, web-edit, git, docs.

---

### [6] GIT POST-COMMIT HOOK
**Priorita: NÍZKÁ**
**Status: TODO**

Automatické `agent index --diff` + `build.py` po každém commitu.

---

## Cílová architektura

```
Git commit
    ↓
[Git Hook: post-commit]
    ├── info-sync.py           — SYNC bloky v CLAUDE.md
    ├── generate-docs.py       — tabulka projektů v master CLAUDE.md
    ├── chroma_indexer.py      — re-indexace změněných souborů
    └── git push gitea main && git push github main
```

---

## Hotové milníky

- [x] Hierarchický systém CLAUDE.md (master + slave)
- [x] info-sync.py — SYNC bloky s živým stavem
- [x] generate-docs.py — tabulka projektů v master CLAUDE.md
- [x] Token Tracker + Prompt Cache + Model Routing
- [x] Sémantický vyhledávač (SQLite+numpy)
- [x] Docs pipeline (JSON→HTML, Jinja2, schema)
- [x] Persistence systém (MEMORY.md, Golden Rule, sanitize.py)
- [x] Všechny projekty dokumentovány (ai, backup-dashboard, dashboard, web-edit, git, docs)
- [x] fedoraOS dokumentace (8 kapitol + web :8081)
- [x] IC ATF setup Režim A (Proxmox VM, API token, proxmoxer konektivita)
