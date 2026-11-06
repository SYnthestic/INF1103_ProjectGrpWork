import os
import secrets

from flask import Flask
from managers import DataManager, LogicManager
from managers.ai_manager import AIManager


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
    if config:
        app.config.update(config)

    from flask import request
    from flask import session as flask_session

    app.config["BOOT_ID"] = secrets.token_hex(16)    # new value on every start

    @app.before_request
    def drop_stale_session():
        """A cookie from before the last restart is no longer valid."""
        if "username" in flask_session and flask_session.get("boot") != app.config["BOOT_ID"]:
            flask_session.clear()

    @app.after_request
    def no_store(response):
        """Stops the browser re-showing cached pages (Back button) after logout."""
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    app.extensions["ai"] = AIManager()
    app.extensions["logic"] = LogicManager()
    app.extensions["data"] = DataManager(data_dir=app.config.get("DATA_DIR"))
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")   # blocks most cross-site form posts

    
    

    from web.auth import bp as auth_bp
    from web.audits import bp as audits_bp
    from web.pages import bp as pages_bp
    from web.workspace import Workspaces

    app.extensions["workspaces"] = Workspaces()
    app.register_blueprint(auth_bp)
    app.register_blueprint(audits_bp)
    app.register_blueprint(pages_bp)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        return {"message": "Grant Audit API", "health": "/health"}

    return app




if __name__ == "__main__":
    create_app().run(debug=True)