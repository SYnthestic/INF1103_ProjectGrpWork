from flask import Flask
from web.routes import bp

def create_app():
    app = Flask(__name__)
    app.config.from_prefixed_env()   # reads FLASK_* from .env
    app.register_blueprint(bp)
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)