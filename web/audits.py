from functools import wraps
from flask import Blueprint, current_app, jsonify, request
from flask import session as flask_session
from models import ApplicationRecord

bp = Blueprint("audits", __name__, url_prefix="/api")


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if "username" not in flask_session:
            return jsonify(error="login required"), 401
        return view(*a, **kw)
    return wrapper


@bp.post("/audits")
@login_required
def create_audit():
    record = request.get_json(silent=True)
    if not record:
        return jsonify(error="JSON body required"), 400

    ai, logic, data = (current_app.extensions[k] for k in ("ai", "logic", "data"))
    wrapped = ApplicationRecord(record)

    ai_audit = ai.get_ai_response(wrapped.narrative, lambda *a, **k: None)  # no progress bar
    if ai.ai_call_failed(ai_audit):
        return jsonify(error="AI call failed"), 502

    result = logic.evaluate_grant_application(wrapped.to_profile(), ai_audit)
    saved = data.append_user_audit(flask_session["username"], record, ai_audit, result)
    return jsonify(audit=saved, ai_audit=ai_audit, result=result), 201


@bp.get("/audits")
@login_required
def list_audits():
    data = current_app.extensions["data"]
    return jsonify(data.get_user_audits(flask_session["username"]))