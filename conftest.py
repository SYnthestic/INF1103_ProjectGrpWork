import pytest
from app import create_app


class FakeAI:
    def get_ai_response(self, narrative, progress=None):
        return {"summary": "fake"}

    def ai_call_failed(self, ai_audit):
        return False


class FakeLogic:
    """Wraps the real LogicManager for passwords, fakes only the grant decision."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def evaluate_grant_application(self, profile, ai_audit):
        return {"decision_status": "Approved", "audit_passed": True}


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path)})
    app.extensions["ai"] = FakeAI()
    app.extensions["logic"] = FakeLogic(app.extensions["logic"])
    return app


@pytest.fixture
def client(app):
    return app.test_client()