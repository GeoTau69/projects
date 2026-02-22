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
OLLAMA_CHAT_URL  = 'http://localhost:11434/api/chat'

ROUTING_RULES: dict[str, str] = {
    'doc_update':    'local',
    'boilerplate':   'local',
    'info_sync':     'local',
    'code_review':   'sonnet',
    'architecture':  'opus',
    'debug_complex': 'sonnet',
    '_default':      'sonnet',
}

CACHE_TTL: dict[str, int] = {
    'doc_update':   24,
    'boilerplate':  48,
    'info_sync':    12,
    'code_review':   0,
    'architecture':  0,
    'debug':         0,
    '_default':     24,
}


# ─── Funkce ───────────────────────────────────────────────────────────────────

def get_cache_ttl(operation: str) -> int:
    """Vrátí TTL v hodinách pro danou operaci. 0 = žádná cache."""
    return CACHE_TTL.get(operation, CACHE_TTL['_default'])


def resolve_model(operation: str, model: str) -> str:
    """
    Rozhodne jaký model použít.
      'auto'  → ROUTING_RULES[operation] nebo '_default'
      'local' → LOCAL_MODEL s prefixem 'ollama/'
      alias   → plný název Claude modelu
    Vrátí buď 'ollama/<název>' nebo plný Claude model string.
    """
    if model == 'auto':
        dest = ROUTING_RULES.get(operation, ROUTING_RULES['_default'])
    else:
        dest = model

    if dest == 'local':
        return f'ollama/{LOCAL_MODEL}'
    return normalize_model(dest)


def select_backend(operation: str, backends: list['Backend']) -> 'Backend':
    """
    Vybere dostupný backend dle routing pravidel.
    Iteruje backends, kontroluje is_available(), vybírá dle resolve_model().
    """
    dest = ROUTING_RULES.get(operation, ROUTING_RULES['_default'])

    # Preferujeme backend odpovídající routing rule
    if dest == 'local':
        for b in backends:
            if b.name == 'ollama' and b.is_available():
                return b
        # Fallback na cloud pokud Ollama nedostupná
        for b in backends:
            if b.name != 'ollama' and b.is_available():
                return b
    else:
        for b in backends:
            if b.name == 'claude' and b.is_available():
                return b
        # Fallback na Ollama/qwen2.5-coder pokud Claude nedostupný
        for b in backends:
            if b.name == 'ollama' and b.is_available():
                return b

    # Poslední záchrana — první dostupný
    for b in backends:
        if b.is_available():
            return b

    raise RuntimeError(
        f"Žádný backend není dostupný pro operaci '{operation}'.\n"
        "  Zkontroluj ANTHROPIC_API_KEY nebo spusť: ollama serve"
    )
