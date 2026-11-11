"""AuditService: runs one application through the managers, as the
terminal's Application.run_audit does, and saves it to the user's history."""

from typing import Any

from models import ApplicationRecord
from .application_validator import ApplicationValidator


class AuditService:
    """Runs one application through the managers, as the terminal's
    Application.run_audit does, and saves it to the user's history."""

    def __init__(self, ai: Any, logic: Any, data: Any, logger: Any) -> None:
        self._ai = ai
        self._logic = logic
        self._data = data
        self._logger = logger
        self._validator = ApplicationValidator()

    @property
    def validator(self) -> ApplicationValidator:
        return self._validator

    def use_saved_rules(self) -> None:
        """Uses the grant rule thresholds an administrator saved in the
        terminal admin console, so web decisions match terminal decisions.
        Falls back to the defaults if none are saved or they are unusable."""
        values, status = self._data.load_rule_config()
        if status == "loaded" and not self._logic.rule_config_problems(values):
            self._logic.use_rule_config(self._logic.rule_config_from_dict(values))
        else:
            self._logic.use_rule_config(self._logic.default_rule_config())

    def ask_ai(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """The AI audit of a record's narrative, or None if the call failed."""
        try:
            ai_audit = self._ai.get_ai_response(
                ApplicationRecord(record).narrative, lambda *a, **k: None
            )
        except Exception:
            self._logger.exception("AI call raised")
            return None
        return None if self._ai.ai_call_failed(ai_audit) else ai_audit

    def decide(self, record: dict[str, Any], ai_audit: dict[str, Any]) -> dict[str, Any] | None:
        """The grant decision with the saved thresholds, or None if it raised."""
        try:
            self.use_saved_rules()
            return self._logic.evaluate_grant_application(
                ApplicationRecord(record).to_profile(), ai_audit
            )
        except Exception:
            self._logger.exception("Grant evaluation raised")
            return None

    def create_audit(
        self, username: str, record: Any
    ) -> tuple[dict[str, Any] | None, str | None, int]:
        """Validate -> AI -> grant logic -> save. Returns (audit, error, http_status)."""
        error = self._validator.problem(record)
        if error:
            return None, error, 400
        ai_audit = self.ask_ai(record)
        if ai_audit is None:
            return None, "AI call failed", 502
        result = self.decide(record, ai_audit)
        if result is None:
            return None, "grant evaluation failed", 500
        saved = self._data.append_user_audit(
            username, record, ai_audit, result, rules_used=self._logic.rule_config.to_dict()
        )
        if saved is None:
            return None, "could not save audit", 500
        return saved, None, 201
