"""AI Manager: sends a proposal narrative to a language model and returns a
validated, correctly typed audit. It never prints and never decides anything.

Dependency inversion: AIManager depends on the AIClient abstraction, so tests
and future providers plug in a different client without editing this class.
"""

import logging
import threading
from typing import Any

from .ai_client import AIClient
from .ai_config import AI_TIMEOUT_SECONDS, SYSTEM_PROMPT, AiAudit, ProgressCallback
from .audit_response_parser import AuditResponseParser
from .openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class AIManager:
    """Sends the proposal narrative to the model and returns a validated
    audit dict matching the schema the Logic Manager expects."""

    def __init__(self, client: AIClient | None = None) -> None:
        self._client = client or OpenRouterClient()
        self._parser = AuditResponseParser()

    def get_ai_response(
        self,
        proposal_narrative: str,
        show_progress: ProgressCallback | None = None,
    ) -> AiAudit:
        api_done_event = threading.Event()
        thread_results: dict[str, Any] = {"output": None, "error": None}

        def worker_api_call() -> None:
            try:
                thread_results["output"] = self._client.complete(
                    SYSTEM_PROMPT, proposal_narrative
                )
            except Exception as error:
                thread_results["error"] = error
            finally:
                api_done_event.set()

        api_thread = threading.Thread(target=worker_api_call, daemon=True)
        api_thread.start()

        if show_progress is not None:
            show_progress(api_done_event, AI_TIMEOUT_SECONDS)

        api_thread.join()

        error = thread_results["error"]
        if error is not None:
            logger.error(
                "AI call failed (%s: %s); using fallback defaults.",
                type(error).__name__,
                error,
            )
            fallback = self._parser.default_audit()
            fallback["ai_reasoning_summary"] = (
                f"AI call failed ({type(error).__name__}: {error}); "
                "manual review recommended."
            )
            return fallback

        return self._parser.parse(thread_results["output"])

    def parse_ai_audit(self, raw_content: Any) -> AiAudit:
        return self._parser.parse(raw_content)

    def sanitise_ai_audit(self, parsed: Any) -> AiAudit:
        return self._parser.sanitise(parsed)

    @staticmethod
    def ai_call_failed(ai_audit: Any) -> bool:
        return not isinstance(ai_audit, dict) or ai_audit.get("ai_status") != "ok"