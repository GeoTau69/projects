# MODEL.md — AI-to-AI Handoff

> Účel: Session log + aktuální stav projektu
> Poslední update: 2026-02-22
> Signální fráze: `štafeta` (handoff) · `konec zvonec` (full checkpoint)

---

## SESSION LOG (nejnovější nahoře)

| Datum | Model | Co | Status |
|-------|-------|----|--------|
| 2026-02-23 | Opus+Sonnet | IC-AFT setup Režim A kompletní, fedoraOS docs (8 kapitol + web :8081), docserver cross-link | ✅ |
| 2026-02-22 | Sonnet | Golden Rule: {projekt}/CLAUDE.md = Sonnet vlastnictví, Haiku pouze čte | ✅ |
| 2026-02-22 | Haiku | AI docs: Golden Rules (3 pravidla), Orchestrator kapitola, ai/CLAUDE.md aktualizace | ✅ |
| 2026-02-22 | Sonnet | Orchestrátor: billing.py, router.py, plugins/{base,claude,ollama}.py, semantic_cache.py, orchestrator.py, token_tracker refaktor + agent ask + Spinner | ✅ |
| 2026-02-22 | Opus | Delta analýza, opravy nekonzistencí po Sonnet+Haiku | ✅ |
| 2026-02-22 | Haiku | docs/data/docs.json vygenerován (10 sekcí, 20 kB HTML) | ✅ |
| 2026-02-22 | Sonnet | MODEL.md slim, ai/CLAUDE.md cleanup, session.md smazán, todo sanitace | ✅ |
| 2026-02-22 | Opus | Audit persistence, Golden Rule update (3 role, štafeta/konec zvonec, dual MEMORY.md) | ✅ |
| 2026-02-21 | Haiku | AI docs: Persistence paměti sekce do ai/CLAUDE.md + docs/data/ai.json | ✅ |

---

## Stav projektu

| Komponenta | Status | Poznámka |
|-----------|--------|----------|
| Token Tracker | ✅ | `ai/_meta/token_tracker.py`, CLI `agent` |
| Prompt Cache | ✅ | TTL dedup v token_tracker.py |
| Semantic Search | ✅ | `ai/_meta/chroma_indexer.py`, SQLite+numpy |
| Model Routing | ✅ | Ollama local / Claude cloud |
| Docs Pipeline | ✅ | JSON→HTML, všechny projekty dokumentovány |
| Persistence systém | ✅ | MEMORY.md dual-path, Golden Rule, sanitize.py |
| Git post-commit hook | ❌ | TODO: auto `agent index --diff` |
