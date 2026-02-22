"""
Router — model routing pravidla a výběr backendu.

Extrahováno z token_tracker.py.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from _meta.billing import normalize_model

if TYPE_CHECKING:
    from _meta.plugins.base import Backend

# ─── Konfigurace ─────────────────────────────────────────────────────────────

LOCAL_MODEL      = 'qwen2.5-coder:14b'
DEEPSEEK_MODEL   = 'deepseek-coder:33b'
OLLAMA_CHAT_URL  = 'http://localhost:11434/api/chat'

ROUTING_RULES: dict[str, str] = {
    'doc_update':    'local',
    'boilerplate':   'local',
    'info_sync':     'local',
    'code_review':   'sonnet',
    'architecture':  'opus',
    'debug_complex': 'sonnet',
    'deepseek':      'deepseek',
    '_default':      'sonnet',
}

CACHE_TTL: dict[str, int] = {
    'doc_update':   24,
    'boilerplate':  48,
    'info_sync':    12,
    'code_review':   0,
    'architecture':  0,
    'debug':         0,
    'deepseek':      0,
    '_default':     24,
}


# ─── Funkce ───────────────────────────────────────────────────────────────────

def get_cache_ttl(operation: str) -> int:
    """Vrátí TTL v hodinách pro danou operaci. 0 = žádná cache."""
    return CACHE_TTL.get(operation, CACHE_TTL['_default'])


def resolve_model(operation: str, model: str) -> str:
    """
    Rozhodne jaký model použít.
      'auto'     → ROUTING_RULES[operation] nebo '_default'
      'local'    → LOCAL_MODEL s prefixem 'ollama/'
      'deepseek' → DEEPSEEK_MODEL s prefixem 'ollama/'
      alias      → plný název Claude modelu
    """
    if model == 'auto':
        dest = ROUTING_RULES.get(operation, ROUTING_RULES['_default'])
    else:
        dest = model

    if dest == 'local':
        return f'ollama/{LOCAL_MODEL}'
    if dest in ('deepseek', 'deepseek-coder'):
        return f'ollama/{DEEPSEEK_MODEL}'
    return normalize_model(dest)


def select_backend(operation: str, backends: list['Backend'],
                   model_hint: str = '') -> 'Backend':
    """
    Vybere dostupný backend dle routing pravidel.

    Priorita pro cloud modely: claude-code (Pro, zdarma) → claude API → Ollama
    Priorita pro lokální modely: Ollama → claude-code → claude API
    model_hint: pokud začíná 'ollama/', vynutí Ollama backend.
    """
    dest = ROUTING_RULES.get(operation, ROUTING_RULES['_default'])

    # Explicitní Ollama model (z resolve_model)
    if model_hint.startswith('ollama/'):
        for b in backends:
            if b.name == 'ollama' and b.is_available():
                return b
        raise RuntimeError(
            f"Ollama backend nedostupný (model: {model_hint})\n"
            "  Spusť: ollama serve"
        )

    if dest in ('local', 'deepseek'):
        # Lokální model přes Ollamu, fallback na cloud
        for b in backends:
            if b.name == 'ollama' and b.is_available():
                return b
        for name in ('claude-code', 'claude'):
            for b in backends:
                if b.name == name and b.is_available():
                    return b
    else:
        # Cloud model: claude-code (Pro) → claude API → Ollama (fallback)
        for name in ('claude-code', 'claude', 'ollama'):
            for b in backends:
                if b.name == name and b.is_available():
                    return b

    # Poslední záchrana — první dostupný
    for b in backends:
        if b.is_available():
            return b

    raise RuntimeError(
        f"Žádný backend není dostupný pro operaci '{operation}'.\n"
        "  Zkontroluj ANTHROPIC_API_KEY nebo spusť: ollama serve"
    )
