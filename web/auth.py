from flask import Blueprint, current_app, jsonify, request
from flask import session as flask_session

from web import service


bp = Blueprint("auth", __name__, url_prefix="/api")


@bp.post("/register")
def register():
    if "username" in flask_session:
        return jsonify(error="already logged in; log out first"), 409
    body = request.get_json(silent=True) or {}
    password = body.get("password", "")
    username = service.clean_username(body.get("username", ""))
    data, logic = current_app.extensions["data"], current_app.extensions["logic"]
    problem = service.account_problem(username, password)
    if problem:
        return jsonify(error=problem), 400
    if service.username_is_taken(data, logic, username):
        return jsonify(error="username taken"), 409
    if not data.save_new_user(logic.build_new_user_record(username, password)):
        return jsonify(error="could not save account"), 500
    return jsonify(username=username), 201


@bp.post("/login")
def login():
    if "username" in flask_session:
        return jsonify(error="already logged in; log out first"), 409
    body = request.get_json(silent=True) or {}
    username = service.clean_username(body.get("username", ""))
    password = body.get("password", "")
    data, logic = current_app.extensions["data"], current_app.extensions["logic"]
    if logic.verify_password(password, data.get_user(username)):
        service.start_session(username)
        return jsonify(username=username)
    return jsonify(error="invalid credentials"), 401


@bp.post("/logout")
def logout():
    flask_session.clear()
    return "", 204