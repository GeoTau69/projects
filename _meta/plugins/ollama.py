"""Ollama backend plugin."""

import json
import urllib.request
import urllib.error
from _meta.plugins.base import Backend, Response
from _meta.router import OLLAMA_CHAT_URL, LOCAL_MODEL


class OllamaBackend(Backend):
    name = 'ollama'
    models: list[str] = []  # dynamicky doplňováno přes is_available / list

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(
                'http://localhost:11434/',
                method='HEAD'
            )
            with urllib.request.urlopen(req, timeout=2):
                return True
        except Exception:
            return False

    def get_pricing(self, model: str) -> dict[str, float]:
        return {'in': 0.0, 'out': 0.0}

    def execute(self, messages: list[dict], model: str,
                system: str | None = None, max_tokens: int = 4096) -> Response:
        # model může být 'local', 'ollama/<název>' nebo přímo '<název>'
        if model == 'local':
            model_name = LOCAL_MODEL
        elif model.startswith('ollama/'):
            model_name = model.removeprefix('ollama/')
        else:
            model_name = model

        ollama_messages = []
        if system:
            ollama_messages.append({'role': 'system', 'content': system})
        ollama_messages.extend(messages)

        payload = json.dumps({
            'model':    model_name,
            'messages': ollama_messages,
            'stream':   False,
            'options':  {'num_predict': max_tokens},
        }).encode()

        req = urllib.request.Request(
            OLLAMA_CHAT_URL, data=payload,
            headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Ollama nedostupná ({OLLAMA_CHAT_URL}): {e}\n"
                "  Spusť: ollama serve"
            )

        text       = data['message']['content']
        tokens_in  = data.get('prompt_eval_count', 0)
        tokens_out = data.get('eval_count', 0)

        return Response(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=f'ollama/{model_name}',
            cost=0.0,
        )
