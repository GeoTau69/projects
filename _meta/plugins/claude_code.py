"""Claude Code CLI backend plugin (Pro/Max licence).

Volá `claude -p` jako subprocess — nepotřebuje ANTHROPIC_API_KEY.
Tokeny jsou odhadovány (1 slovo ≈ 1.35 tok, 1 znak ≈ 1/3.8 tok).
Cena je orientační dle API ceníku (Pro = paušál, ale pro porovnání).
"""

import os
import shutil
import subprocess

from _meta.plugins.base import Backend, Response
from _meta.billing import calc_cost, normalize_model


def _estimate_tokens(text: str) -> int:
    """Odhadne počet tokenů kombinací word-count a char-count metod."""
    words = len(text.split())
    chars = len(text)
    by_words = int(words * 1.35)
    by_chars = int(chars / 3.8)
    return max(1, (by_words + by_chars) // 2)


class ClaudeCodeBackend(Backend):
    name = 'claude-code'
    models = [
        'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5',
        'opus', 'sonnet', 'haiku',
    ]

    def is_available(self) -> bool:
        return shutil.which('claude') is not None

    def get_pricing(self, model: str) -> dict[str, float]:
        from _meta.billing import MODEL_PRICES
        full = normalize_model(model)
        return MODEL_PRICES.get(full) or MODEL_PRICES.get(model) or {'in': 0.0, 'out': 0.0}

    def execute(self, messages: list[dict], model: str,
                system: str | None = None, max_tokens: int = 4096) -> Response:
        # Sestavení promptu
        parts = []
        if system:
            parts.append(f'[System: {system}]')
        for m in messages:
            role = m.get('role', 'user')
            content = m.get('content', '')
            if role == 'user':
                parts.append(content)
            elif role == 'assistant':
                parts.append(f'[Assistant: {content}]')
        prompt = '\n'.join(parts)

        # Prostředí bez CLAUDECODE (umožní nested session)
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDECODE'}

        # Model pro CLI (full name)
        cli_model = model if model.startswith('claude-') else normalize_model(model)

        result = subprocess.run(
            ['claude', '-p', '--model', cli_model, '--no-session-persistence', prompt],
            env=env, capture_output=True, text=True, timeout=120,
        )

        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"claude CLI selhal (kód {result.returncode}): {err}")

        text = result.stdout.strip()

        # Odhad tokenů a orientační cena dle API ceníku
        tokens_in  = _estimate_tokens(prompt)
        tokens_out = _estimate_tokens(text)
        cost       = calc_cost(cli_model, tokens_in, tokens_out)

        return Response(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=f'claude-code/{cli_model}',
            cost=cost,
        )
