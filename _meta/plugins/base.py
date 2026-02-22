"""Backend ABC interface pro orchestrátor."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Response:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    cost: float


class Backend(ABC):
    name: str
    models: list[str]

    @abstractmethod
    def execute(self, messages: list[dict], model: str,
                system: str | None = None, max_tokens: int = 4096) -> Response: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def get_pricing(self, model: str) -> dict[str, float]: ...
