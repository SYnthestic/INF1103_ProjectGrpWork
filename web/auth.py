"""JSON API for accounts: register, log in, log out (under /api)."""

from typing import Any

from flask import jsonify, request

from web.routes import Route, RouteGroup
from web.service import AccountRules


class AuthApi(RouteGroup):
    """Accounts for API clients, with the same rules as the terminal app."""

    name = "auth"
    url_prefix = "/api"

    def __init__(self, rules: AccountRules | None = None) -> None:
        self._rules = rules or AccountRules()

    def routes(self) -> list[Route]:
        return [
            Route("/register", self.register, ("POST",)),
            Route("/login", self.login, ("POST",)),
            Route("/logout", self.logout, ("POST",)),
        ]

    def not_logged_in(self) -> Any:
        return jsonify(error="login required"), 401

    def credentials(self) -> tuple[str, Any]:
        body = request.get_json(silent=True) or {}
        return self._rules.clean_username(body.get("username", "")), body.get("password", "")

    def register(self) -> Any:
        if self.username is not None:
            return jsonify(error="already logged in; log out first"), 409
        username, password = self.credentials()
        problem = self._rules.problem(username, password)
        if problem:
            return jsonify(error=problem), 400
        if self._rules.is_taken(self.data, self.logic, username):
            return jsonify(error="username taken"), 409
        if not self.data.save_new_user(self.logic.build_new_user_record(username, password)):
            return jsonify(error="could not save account"), 500
        return jsonify(username=username), 201

    def login(self) -> Any:
        if self.username is not None:
            return jsonify(error="already logged in; log out first"), 409
        username, password = self.credentials()
        if self.logic.verify_password(password, self.data.get_user(username)):
            self.start_session(username)
            return jsonify(username=username)
        return jsonify(error="invalid credentials"), 401

    def logout(self) -> Any:
        self.end_session()
        return "", 204
