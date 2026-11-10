from flask import current_app
from flask import session as flask_session

import math
from typing import Any

from managers.io_manager import InputValidator, IOManager
from models import REPORTING_PROPOSAL, ApplicationRecord

REQUIRED_TEXT = ("Company Name", "Company Industry", "Proposal Narrative")
REQUIRED_NUMBERS = ("Company Total Revenue", "Total Employees", "Local Equity")
MONEY_FIELDS = (
    "Baseline Energy Expenditure",
    "Estimated Retrofit Cost",
    "Reporting Advisory Fee",
)
# Which money fields each kind of proposal asks for (the others are 0), as in
# the terminal's EquipmentProposal / ReportingProposal.
REPORTING_MONEY = ("Reporting Advisory Fee",)
EQUIPMENT_MONEY = ("Baseline Energy Expenditure", "Estimated Retrofit Cost")



def account_problem(username, password) -> str | None:
    """Why a new web account cannot be created with these details, or None.
    Uses the same rules as the terminal app (InputValidator), so an account
    made on the web works in the terminal and the other way round."""
    if not isinstance(username, str) or not isinstance(password, str):
        return "Username and password must be text."
    if not username or not password:
        return "Username and password are required."
    if not InputValidator.is_valid_username(username):
        return (
            f"Username must be {InputValidator.USERNAME_MIN_LEN}-"
            f"{InputValidator.USERNAME_MAX_LEN} characters: letters, digits or _."
        )
    problems = InputValidator.password_problems(password)
    if problems:
        return "Password must " + ", ".join(problems) + "."
    return None


def clean_username(value) -> str:
    """Usernames are not case-sensitive, as in the terminal app."""
    return value.strip().lower() if isinstance(value, str) else ""


def username_is_taken(data, logic, username: str) -> bool:
    """Taken by an account, or reserved for the ADMIN_USERNAME administrator
    (so the web pages cannot be used to claim the admin name)."""
    return data.user_exists(username) or username == logic.access.bootstrap_admin


def use_saved_rules(logic, data) -> None:
    """Uses the grant rule thresholds an administrator saved in the terminal
    admin console, so web decisions match terminal decisions. Falls back to the
    defaults if none are saved or the saved values cannot be used."""
    values, status = data.load_rule_config()
    if status == "loaded" and not logic.rule_config_problems(values):
        logic.use_rule_config(logic.rule_config_from_dict(values))
    else:
        logic.use_rule_config(logic.default_rule_config())


def start_session(username: str) -> None:
    flask_session.clear()
    flask_session["username"] = username
    flask_session["boot"] = current_app.config["BOOT_ID"]


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


def is_number(value: Any) -> bool:
    """A real, finite number (JSON can carry NaN and Infinity, and True is
    an int in Python, so a plain isinstance check is not enough)."""
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def money_fields_for(proposal_type: Any) -> tuple[str, ...]:
    return REPORTING_MONEY if proposal_type == REPORTING_PROPOSAL else EQUIPMENT_MONEY


def validate_application(record, strict_costs: bool = False) -> str | None:
    """Error message, or None if acceptable. The same limits as the terminal
    prompts (IOManager.retrieve_*):

        Company Total Revenue   above 0
        Total Employees         a whole number above 0
        Local Equity            above 0 and at most 100
        money fields            0 or more when given

    strict_costs (the web forms) also requires, like the terminal, a baseline
    energy spend and retrofit cost above 0 for equipment proposals. The JSON
    API leaves them optional; a missing baseline then goes to manual review."""
    if not isinstance(record, dict):
        return "JSON object required"
    for key in REQUIRED_TEXT:
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"{key} is required"
    if len(record["Company Name"]) > IOManager.COMPANY_NAME_MAX_LEN:
        return f"Company Name must be at most {IOManager.COMPANY_NAME_MAX_LEN} characters"
    if len(record["Proposal Narrative"]) > IOManager.NARRATIVE_MAX_LEN:
        return f"Proposal Narrative must be at most {IOManager.NARRATIVE_MAX_LEN} characters"

    revenue = record.get("Company Total Revenue")
    if not is_number(revenue) or revenue <= 0:
        return "Company Total Revenue must be a number above 0"
    employees = record.get("Total Employees")
    if not is_number(employees) or employees <= 0 or employees != int(employees):
        return "Total Employees must be a whole number above 0"
    equity = record.get("Local Equity")
    if not is_number(equity) or not 0 < equity <= 100:
        return "Local Equity must be between 0 and 100 (above 0)"

    for key in MONEY_FIELDS:
        if key in record and not (is_number(record[key]) and record[key] >= 0):
            return f"{key} must be a number of 0 or more"
    if strict_costs:
        for key in money_fields_for(record.get("Proposal Type")):
            if key != "Reporting Advisory Fee" and not record.get(key, 0) > 0:
                return f"{key} must be above 0 for an equipment proposal"
    return None


def create_audit(username: str, record) -> tuple[dict | None, str | None, int]:
    """Validate -> AI -> grant logic -> save. Returns (audit, error, http_status)."""
    error = validate_application(record)
    if error:
        return None, error, 400

    ai = current_app.extensions["ai"]
    logic = current_app.extensions["logic"]
    data = current_app.extensions["data"]
    wrapped = ApplicationRecord(record)

    try:
        ai_audit = ai.get_ai_response(wrapped.narrative, lambda *a, **k: None)
    except Exception:
        current_app.logger.exception("AI call raised")
        return None, "AI call failed", 502
    if ai.ai_call_failed(ai_audit):
        return None, "AI call failed", 502

    try:
        use_saved_rules(logic, data)
        result = logic.evaluate_grant_application(wrapped.to_profile(), ai_audit)
    except Exception:
        current_app.logger.exception("Grant evaluation raised")
        return None, "grant evaluation failed", 500

    saved = data.append_user_audit(
        username, record, ai_audit, result, rules_used=logic.rule_config.to_dict()
    )
    if saved is None:
        return None, "could not save audit", 500
    return saved, None, 201