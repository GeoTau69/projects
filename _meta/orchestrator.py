"""
Orchestrator — centrální entry point pro AI requesty.

Postup:
  1. Sémantická cache lookup
  2. Hash cache lookup
  3. Výběr backendu (router)
  4. Vykonání (backend.execute)
  5. Billing log + cache store
  6. Vrátí Response
"""

from _meta.plugins.base import Backend, Response
from _meta.billing import (
    init_db, hash_prompt, calc_cost,
    cache_lookup, cache_store, log_cache_hit,
)
from _meta.router import resolve_model, select_backend, get_cache_ttl
import _meta.semantic_cache as sem_cache


class Orchestrator:
    def __init__(self) -> None:
        self.backends: list[Backend] = []

    def register(self, backend: Backend) -> None:
        self.backends.append(backend)

    def request(self, messages: list[dict], operation: str, project: str,
                model: str = 'auto', system: str | None = None,
                max_tokens: int = 4096, notes: str = '') -> Response:
        """
        Zpracuje request: cache → routing → execute → log → return.
        """
        # Prompt jako text pro sémantické vyhledávání
        prompt_text = ' '.join(
            m.get('content', '') for m in messages if isinstance(m.get('content'), str)
        )

        # ── 1. Sémantická cache ──────────────────────────────────────────────
        sem_hit = sem_cache.lookup(prompt_text, operation)
        if sem_hit:
            full_model = resolve_model(operation, model)
            conn = init_db()
            phash = hash_prompt(messages, system)
            log_cache_hit(conn, project, operation, full_model, phash)
            conn.close()
            return Response(
                text=sem_hit,
                tokens_in=0, tokens_out=0,
                model=full_model, cost=0.0,
            )

        # ── 2. Hash cache ────────────────────────────────────────────────────
        phash = hash_prompt(messages, system)
        ttl   = get_cache_ttl(operation)
        conn  = init_db()
        cached = cache_lookup(conn, phash, operation, ttl)
        if cached:
            full_model = resolve_model(operation, model)
            log_cache_hit(conn, project, operation, full_model, phash)
            conn.close()
            return Response(
                text=cached,
                tokens_in=0, tokens_out=0,
                model=full_model, cost=0.0,
            )
        conn.close()

        # ── 3. Výběr backendu ────────────────────────────────────────────────
        backend = select_backend(operation, self.backends)

        # Určení modelu pro daný backend
        full_model = resolve_model(operation, model)
        if backend.name == 'ollama':
            exec_model = full_model  # 'ollama/<název>'
        else:
            exec_model = full_model

        # ── 4. Execute ───────────────────────────────────────────────────────
        resp = backend.execute(messages, exec_model, system, max_tokens)

        # ── 5. Billing log + hash cache ──────────────────────────────────────
        conn = init_db()
        cache_store(conn, project, operation, resp.model,
                    resp.tokens_in, resp.tokens_out, resp.cost,
                    phash, resp.text, notes)
        conn.close()

        # ── 5b. Sémantická cache store ───────────────────────────────────────
        if ttl > 0:
            sem_cache.store(prompt_text, resp.text, operation, resp.model)

        return resp
