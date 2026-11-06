import pytest

from managers.logic_manager import AesGcmCipher


@pytest.fixture(autouse=True)
def no_admin_from_the_environment(monkeypatch):
    """ADMIN_USERNAME from the developer's shell or .env must not change the
    tests. Tests that need an administrator pass admin_username explicitly."""
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)


@pytest.fixture(autouse=True)
def throwaway_encryption_key(monkeypatch):
    """Random key for each test, so the real key and CI secrets aren't needed."""
    monkeypatch.setenv(AesGcmCipher.KEY_ENV_VAR, AesGcmCipher.generate_key())
