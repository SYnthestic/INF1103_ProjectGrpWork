import os
from flask import Flask
from managers.ai_manager import AIManager
from managers.data_manager import DataManager
from managers.logic_manager import LogicManager


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
    if config:
        app.config.update(config)

    app.extensions["ai"] = AIManager()
    app.extensions["logic"] = LogicManager()
    app.extensions["data"] = DataManager(data_dir=app.config.get("DATA_DIR"))
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")   # blocks most cross-site form posts

    
    

    from web.auth import bp as auth_bp
    from web.audits import bp as audits_bp
    from web.pages import bp as pages_bp

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