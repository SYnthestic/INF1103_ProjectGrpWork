import pytest


@pytest.fixture(autouse=True)
def no_admin_from_the_environment(monkeypatch):
    """ADMIN_USERNAME from the developer's shell or .env must not change the
    tests. Tests that need an administrator pass admin_username explicitly."""
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
