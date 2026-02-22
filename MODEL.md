# MODEL.md — AI-to-AI Handoff

> Účel: Session log + aktuální stav projektu
> Poslední update: 2026-02-22
> Signální fráze: `štafeta` (handoff) · `konec zvonec` (full checkpoint)

---

## SESSION LOG (nejnovější nahoře)

| Datum | Model | Co | Status |
|-------|-------|----|--------|
| 2026-02-22 | Opus | Audit persistence systému, Golden Rule update (3 role, štafeta/konec zvonec, dual MEMORY.md), specifikace pro Sonnet | ✅ |
| 2026-02-22 | Sonnet | Implementace Opus specifikace: MODEL.md slim, ai/CLAUDE.md cleanup, session.md smazán, todo sanitace | ✅ |
| 2026-02-21 | Haiku | AI docs: Persistence paměti sekce do ai/CLAUDE.md + docs/data/ai.json | ✅ |
| 2026-02-21 | Sonnet | Persistent session systém: MEMORY.md, session.md, Golden Rule v CLAUDE.md | ✅ |
| 2026-02-20 | Sonnet | Sanitace systém: tools/sanitize.py, /maintenance portál, docs/INFO.md | ✅ |

---

## Stav projektu

| Komponenta | Status | Poznámka |
|-----------|--------|----------|
| Token Tracker | ✅ | `ai/_meta/token_tracker.py`, CLI `agent` |
| Prompt Cache | ✅ | TTL dedup v token_tracker.py |
| Semantic Search | ✅ | `ai/_meta/chroma_indexer.py`, SQLite+numpy |
| Model Routing | ✅ | Ollama local / Claude cloud |
| Docs Pipeline | ✅ | JSON→HTML (Jinja2), build.py, schema |
| Persistence systém | ✅ | MEMORY.md dual-path, Golden Rule, sanitize.py |
| Git post-commit hook | ❌ | TODO: auto `agent index --diff` |
| docs.json | ❌ | TODO: Haiku vygeneruje dokumentaci pro docs/ projekt |
