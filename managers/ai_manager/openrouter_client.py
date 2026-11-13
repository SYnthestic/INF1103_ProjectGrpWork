"""AIClient implementation backed by OpenRouter."""

import os
from collections.abc import Callable
from typing import Any

from openai import OpenAI

from .ai_client import AIClient
from .ai_config import AI_TIMEOUT_SECONDS


class OpenRouterClient(AIClient):
    """AIClient backed by the OpenRouter chat-completions API."""

    BASE_URL = "https://openrouter.ai/api/v1"
    MODEL = "openrouter/free"

    def __init__(
        self,
        timeout_seconds: int = AI_TIMEOUT_SECONDS,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._client_factory = client_factory or self.setup_ai_client

    def setup_ai_client(self) -> OpenAI:
        api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add it to your .env file (see README)."
            )
        return OpenAI(
            base_url=self.BASE_URL,
            api_key=api_key,
            max_retries=0,
            timeout=self._timeout,
        )

    def complete(self, system_prompt: str, user_message: str) -> Any:
        client = self._client_factory()
        response = client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            timeout=self._timeout,
        )
        return response.choices[0].message.content