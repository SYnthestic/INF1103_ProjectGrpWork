from flask import current_app

from models import ApplicationRecord

REQUIRED_TEXT = ("Company Name", "Company Industry", "Proposal Narrative")
REQUIRED_NUMBERS = ("Company Total Revenue", "Total Employees", "Local Equity")


def validate_application(record) -> str | None:
    """Error message, or None if acceptable.
    TODO: replace with the exact ranges from IOManager's retrieve_* methods."""
    if not isinstance(record, dict):
        return "JSON object required"
    for key in REQUIRED_TEXT:
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"{key} is required"
    for key in REQUIRED_NUMBERS:
        value = record.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            return f"{key} must be a non-negative number"
    if record["Local Equity"] > 100:
        return "Local Equity must be between 0 and 100"
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
        result = logic.evaluate_grant_application(wrapped.to_profile(), ai_audit)
    except Exception:
        current_app.logger.exception("Grant evaluation raised")
        return None, "grant evaluation failed", 500

    saved = data.append_user_audit(username, record, ai_audit, result)
    if saved is None:
        return None, "could not save audit", 500
    return saved, None, 201