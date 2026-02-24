# MODEL.md — AI-to-AI Handoff

> Účel: Session log + aktuální stav projektu
> Poslední update: 2026-02-22
> Signální fráze: `štafeta` (handoff) · `konec zvonec` (full checkpoint)

---

## SESSION LOG (nejnovější nahoře)

| Datum | Model | Co | Status |
|-------|-------|----|--------|
| 2026-02-24 | Opus | fedoraOS docs pipeline (7 kroků), MANIFEST 7 principů, principy 2+4+5 do CLAUDE.md, ic-atf symlink+project.yaml, smazán backup-scripts-analysis, make docs (8 projektů) | ✅ |
| 2026-02-23 | Opus | IC-AFT→IC ATF rename, metadata refaktoring (symlink MEMORY, de-dup Golden Rules, ~/CLAUDE.md root loader, "ulož si práci"), CLAUDE.md pro ic-atf + fedoraOS | ✅ |
| 2026-02-23 | Opus+Sonnet | IC ATF setup Režim A kompletní, fedoraOS docs (8 kapitol + web :8081), docserver cross-link | ✅ |
| 2026-02-22 | Sonnet | Golden Rule: {projekt}/CLAUDE.md = Sonnet vlastnictví, Haiku pouze čte | ✅ |
| 2026-02-22 | Haiku | AI docs: Golden Rules (3 pravidla), Orchestrator kapitola, ai/CLAUDE.md aktualizace | ✅ |
| 2026-02-22 | Sonnet | Orchestrátor: billing.py, router.py, plugins/{base,claude,ollama}.py, semantic_cache.py, orchestrator.py, token_tracker refaktor + agent ask + Spinner | ✅ |
| 2026-02-22 | Opus | Delta analýza, opravy nekonzistencí po Sonnet+Haiku | ✅ |
| 2026-02-22 | Haiku | docs/data/docs.json vygenerován (10 sekcí, 20 kB HTML) | ✅ |
| 2026-02-22 | Sonnet | MODEL.md slim, ai/CLAUDE.md cleanup, session.md smazán, todo sanitace | ✅ |
| 2026-02-22 | Opus | Audit persistence, Golden Rule update (3 role, štafeta/konec zvonec, dual MEMORY.md) | ✅ |
| 2026-02-21 | Haiku | AI docs: Persistence paměti sekce do ai/CLAUDE.md + docs/data/ai.json | ✅ |

