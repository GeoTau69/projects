"""Claude (Anthropic) backend plugin."""

import os
from _meta.plugins.base import Backend, Response
from _meta.billing import MODEL_PRICES, MODEL_ALIASES, normalize_model, calc_cost


class ClaudeBackend(Backend):
    name = 'claude'
    models = [
        'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5',
        'opus', 'sonnet', 'haiku',
    ]

    def is_available(self) -> bool:
        return bool(os.environ.get('ANTHROPIC_API_KEY'))

    def get_pricing(self, model: str) -> dict[str, float]:
        full = normalize_model(model)
        return MODEL_PRICES.get(full) or MODEL_PRICES.get(model) or {'in': 0.0, 'out': 0.0}

    def execute(self, messages: list[dict], model: str,
                system: str | None = None, max_tokens: int = 4096) -> Response:
        try:
            import anthropic as ant
        except ImportError:
            raise ImportError(
                "Chybí balíček 'anthropic'.\n"
                "  pip install anthropic\n"
                "  export ANTHROPIC_API_KEY=sk-ant-..."
            )

        full_model = normalize_model(model)
        kwargs: dict = dict(model=full_model, max_tokens=max_tokens, messages=messages)
        if system:
            kwargs['system'] = system

        client   = ant.Anthropic()
        response = client.messages.create(**kwargs)

        text       = response.content[0].text
        tokens_in  = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cost       = calc_cost(full_model, tokens_in, tokens_out)

        return Response(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=full_model,
            cost=cost,
        )
