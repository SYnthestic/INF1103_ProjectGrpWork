"""Flask entry point for the web version.

    WebApplication   builds the Flask app: the same AI, Logic and Data
                     managers the terminal app uses, the per-user records in
                     memory, and the route groups (pages, accounts API,
                     audits API, admin console), each registered the same way.

`create_app` is the one module-level function left on purpose: Flask
(`flask --app app run`) only accepts a plain function called create_app as the
app factory, and gunicorn (`"app:create_app()"`) and the tests call it too. It
just hands over to WebApplication.
"""

import os
import secrets
from typing import Any

from flask import Flask, request
from flask import session as flask_session

from managers import DataManager, LogicManager
from managers.ai_manager.ai_manager import AIManager
from web.admin import AdminRoutes
from web.audits import AuditApi
from web.auth import AuthApi
from web.pages import PageRoutes
from web.routes import RouteGroup
from web.workspace import Workspaces


class WebApplication:
    """Owns one Flask app and everything it is set up with."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._app = Flask(__name__)
        self.configure(config)
        self.add_managers()
        self.add_routes([AuthApi(), AuditApi(), PageRoutes(), AdminRoutes()])

    @classmethod
    def create(cls, config: dict[str, Any] | None = None) -> Flask:
        return cls(config).app

    @property
    def app(self) -> Flask:
        return self._app

    def configure(self, config: dict[str, Any] | None) -> None:
        app = self._app
        # The secret key signs the login cookie. Without FLASK_SECRET_KEY a
        # random key is made at every start (never a fixed one in the code,
        # which anyone could read and use to forge a login). Logins end on
        # restart anyway.
        secret = os.environ.get("FLASK_SECRET_KEY")
        app.config["SECRET_KEY"] = secret or secrets.token_hex(32)
        if config:
            app.config.update(config)
        if not secret and not app.config.get("TESTING"):
            app.logger.warning("FLASK_SECRET_KEY is not set; using a random key for this run.")
        app.config["BOOT_ID"] = secrets.token_hex(16)  # new value on every start
        app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")  # blocks most cross-site posts
        app.before_request(self.drop_stale_session)
        app.after_request(self.no_store)

    def add_managers(self) -> None:
        app = self._app
        app.extensions["ai"] = AIManager()
        logic = LogicManager()
        app.extensions["logic"] = logic
        # No valid key -> EncryptionKeyError, so the server won't start.
        data = DataManager(data_dir=app.config.get("DATA_DIR"), cipher=logic.file_cipher)
        problems = data.check_shared_files()
        if problems:
            details = ", ".join(f"{name} ({reason})" for name, reason in problems)
            raise RuntimeError(
                f"Data files cannot be opened with DATA_ENCRYPTION_KEY: {details}. "
                "Check the key, or run 'python main.py --encrypt-existing-data' "
                "once for old unencrypted files."
            )
        app.extensions["data"] = data
        app.extensions["workspaces"] = Workspaces()

    def add_routes(self, groups: list[RouteGroup]) -> None:
        """Every group is registered the same way, whatever kind it is."""
        for group in groups:
            self._app.register_blueprint(group.blueprint())
        self._app.add_url_rule("/health", "health", self.health)
        self._app.add_url_rule("/", "index", self.index)

    def drop_stale_session(self) -> None:
        """A cookie from before the last restart is no longer valid."""
        if (
            "username" in flask_session
            and flask_session.get("boot") != self._app.config["BOOT_ID"]
        ):
            flask_session.clear()

    @staticmethod
    def no_store(response: Any) -> Any:
        """Stops the browser re-showing cached pages (Back button) after logout."""
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @staticmethod
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @staticmethod
    def index() -> dict[str, str]:
        return {"message": "Grant Audit API", "health": "/health"}


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """The app factory Flask, gunicorn and the tests look for (see above)."""
    return WebApplication.create(config)


if __name__ == "__main__":
    # The debugger lets anyone who can reach the page run code on this
    # machine, so it is only on when asked for: FLASK_DEBUG=1.
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
