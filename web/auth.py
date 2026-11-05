from flask import Blueprint, current_app, jsonify, request
from flask import session as flask_session

bp = Blueprint("auth", __name__, url_prefix="/api")


@bp.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    username, password = body.get("username", ""), body.get("password", "")
    data, logic = current_app.extensions["data"], current_app.extensions["logic"]
    if not username or not password:
        return jsonify(error="username and password required"), 400
    if not data.is_safe_username(username):
        return jsonify(error="username must be 1-64 chars of a-z, 0-9, _"), 400
    if data.user_exists(username):
        return jsonify(error="username taken"), 409
    if not data.save_new_user(logic.build_new_user_record(username, password)):
        return jsonify(error="could not save account"), 500
    return jsonify(username=username), 201


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    username, password = body.get("username", ""), body.get("password", "")
    data, logic = current_app.extensions["data"], current_app.extensions["logic"]
    if logic.verify_password(password, data.get_user(username)):
        flask_session["username"] = username
        return jsonify(username=username)
    return jsonify(error="invalid credentials"), 401


@bp.post("/logout")
def logout():
    flask_session.clear()
    return "", 204