from functools import wraps

from web import service
from flask import Blueprint, current_app, jsonify, request
from flask import session as flask_session


bp = Blueprint("audits", __name__, url_prefix="/api")

REQUIRED_TEXT = ("Company Name", "Company Industry", "Proposal Narrative")
REQUIRED_NUMBERS = ("Company Total Revenue", "Total Employees", "Local Equity")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "username" not in flask_session:
            return jsonify(error="login required"), 401
        return view(*args, **kwargs)

    return wrapper


def validate_application(record) -> str | None:
    """Returns an error message, or None if the record is acceptable.
    TODO: reuse the exact ranges from IOManager's retrieve_* methods."""
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


@bp.post("/audits")
@login_required
def create_audit():
    audit, error, status = service.create_audit(
        flask_session["username"], request.get_json(silent=True)
    )
    if error:
        return jsonify(error=error), status
    return jsonify(audit=audit), status


@bp.get("/audits")
@login_required
def list_audits():
    data = current_app.extensions["data"]
    return jsonify(data.get_user_audits(flask_session["username"]))


@bp.get("/audits/<int:audit_id>")
@login_required
def get_audit(audit_id: int):
    data = current_app.extensions["data"]
    for audit in data.get_user_audits(flask_session["username"]):
        if audit.get("audit_id") == audit_id:
            return jsonify(audit)
    return jsonify(error="audit not found"), 404