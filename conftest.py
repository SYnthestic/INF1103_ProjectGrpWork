import pytest
from app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True})
    # redirect DataManager paths to tmp_path here
    return app.test_client()
