"""The AI provider contract."""

from abc import ABC, abstractmethod
from typing import Any


class AIClient(ABC):
    """Anything that can turn a system prompt and a user message into the
    model's answer text."""

    @abstractmethod
    def complete(self, system_prompt: str, user_message: str) -> Any:
        """Returns the model's answer (normally a string). Raises on failure."""