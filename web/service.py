"""What the web pages and the JSON API share: account rules, checking an
application, and running one audit through the managers.

Class overview
    AccountRules           the terminal's username and password rules
    ApplicationValidator   the terminal's limits for an application's fields
    AuditService           validate -> AI Manager -> Logic Manager -> Data
                           Manager for one application. It is handed the
                           managers (aggregation) and owns its validator
                           (composition).

Nothing here decides a grant; that is the Logic Manager's job.
"""

import math
from typing import Any

from managers.io_manager import InputValidator, IOManager
from models import REPORTING_PROPOSAL, ApplicationRecord


class AccountRules:
    """The terminal app's account rules (InputValidator), so an account made
    on the web works in the terminal and the other way round."""

    def __init__(self, validator: type[InputValidator] = InputValidator) -> None:
        self._validator = validator

    @staticmethod
    def clean_username(value: Any) -> str:
        """Usernames are not case-sensitive, as in the terminal app."""
        return value.strip().lower() if isinstance(value, str) else ""

    def problem(self, username: Any, password: Any) -> str | None:
        """Why a new account cannot be created with these details, or None."""
        if not isinstance(username, str) or not isinstance(password, str):
            return "Username and password must be text."
        if not username or not password:
            return "Username and password are required."
        if not self._validator.is_valid_username(username):
            return (
                f"Username must be {self._validator.USERNAME_MIN_LEN}-"
                f"{self._validator.USERNAME_MAX_LEN} characters: letters, digits or _."
            )
        problems = self._validator.password_problems(password)
        if problems:
            return "Password must " + ", ".join(problems) + "."
        return None

    @staticmethod
    def is_taken(data: Any, logic: Any, username: str) -> bool:
        """Taken by an account, or reserved for the ADMIN_USERNAME
        administrator (so the web cannot be used to claim the admin name)."""
        return data.user_exists(username) or username == logic.access.bootstrap_admin


class ApplicationValidator:
    """The same limits as the terminal prompts (IOManager.retrieve_*):

        Company Total Revenue   above 0
        Total Employees         a whole number above 0
        Local Equity            above 0 and at most 100
        money fields            0 or more when given
    """

    REQUIRED_TEXT = ("Company Name", "Company Industry", "Proposal Narrative")
    MONEY_FIELDS = (
        "Baseline Energy Expenditure",
        "Estimated Retrofit Cost",
        "Reporting Advisory Fee",
    )
    # Which money fields each kind of proposal asks for (the others are 0), as
    # in the terminal's EquipmentProposal / ReportingProposal.
    REPORTING_MONEY = ("Reporting Advisory Fee",)
    EQUIPMENT_MONEY = ("Baseline Energy Expenditure", "Estimated Retrofit Cost")

    def __init__(
        self,
        name_max_len: int = IOManager.COMPANY_NAME_MAX_LEN,
        narrative_max_len: int = IOManager.NARRATIVE_MAX_LEN,
    ) -> None:
        self._name_max_len = name_max_len
        self._narrative_max_len = narrative_max_len

    @staticmethod
    def form_number(text: Any) -> float | None:
        """A typed form value as a finite number, or None. Uses the terminal's
        finite_float, so "nan", "inf" and "1e309" (which float() accepts) are
        refused, while ordinary forms such as "1e5" still work."""
        if not isinstance(text, str):
            return None
        try:
            return InputValidator.finite_float(text.strip())
        except ValueError:
            return None

    @staticmethod
    def is_number(value: Any) -> bool:
        """A real, finite number (JSON can carry NaN and Infinity, and True is
        an int in Python, so a plain isinstance check is not enough)."""
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
        )

    @classmethod
    def money_fields_for(cls, proposal_type: Any) -> tuple[str, ...]:
        if proposal_type == REPORTING_PROPOSAL:
            return cls.REPORTING_MONEY
        return cls.EQUIPMENT_MONEY

    def problem(self, record: Any, strict_costs: bool = False) -> str | None:
        """Error message, or None if acceptable. strict_costs (the web forms)
        also requires, like the terminal, a baseline energy spend and retrofit
        cost above 0 for equipment proposals. The JSON API leaves them
        optional; a missing baseline then goes to manual review."""
        if not isinstance(record, dict):
            return "JSON object required"
        for key in self.REQUIRED_TEXT:
            value = record.get(key)
            if not isinstance(value, str) or not value.strip():
                return f"{key} is required"
        if len(record["Company Name"]) > self._name_max_len:
            return f"Company Name must be at most {self._name_max_len} characters"
        if len(record["Proposal Narrative"]) > self._narrative_max_len:
            return f"Proposal Narrative must be at most {self._narrative_max_len} characters"

        revenue = record.get("Company Total Revenue")
        if not self.is_number(revenue) or revenue <= 0:
            return "Company Total Revenue must be a number above 0"
        employees = record.get("Total Employees")
        if not self.is_number(employees) or employees <= 0 or employees != int(employees):
            return "Total Employees must be a whole number above 0"
        equity = record.get("Local Equity")
        if not self.is_number(equity) or not 0 < equity <= 100:
            return "Local Equity must be between 0 and 100 (above 0)"

        for key in self.MONEY_FIELDS:
            if key in record and not (self.is_number(record[key]) and record[key] >= 0):
                return f"{key} must be a number of 0 or more"
        if strict_costs:
            for key in self.money_fields_for(record.get("Proposal Type")):
                if key != "Reporting Advisory Fee" and not record.get(key, 0) > 0:
                    return f"{key} must be above 0 for an equipment proposal"
        return None


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
