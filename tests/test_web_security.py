"""The web version follows the same account rules as the terminal app and
does not ship with insecure defaults (fixed secret key, debugger on)."""

import os
import runpy
from unittest import mock

import pytest

from app import create_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = {"username": "tester", "password": "Test1234!"}


# ---- Account rules (same as the terminal) -------------------------------------


@pytest.mark.parametrize(
    "creds, message",
    [
        ({"username": "ab", "password": "Test1234!"}, b"Username must be 3-20"),
        ({"username": "a" * 21, "password": "Test1234!"}, b"Username must be 3-20"),
        ({"username": "bad-name", "password": "Test1234!"}, b"Username must be 3-20"),
        ({"username": "tester", "password": "a"}, b"at least 8 characters"),
        ({"username": "tester", "password": "abcdefgh"}, b"at least one digit"),
        ({"username": "tester", "password": "12345678"}, b"at least one letter"),
        ({"username": "tester", "password": ""}, b"are required"),
    ],
)
def test_the_register_page_uses_the_terminal_rules(app, client, creds, message):
    page = client.post("/register", data=creds)
    assert message in page.data
    assert app.extensions["data"].load_users() == {}


@pytest.mark.parametrize(
    "body",
    [
        {"username": "tester", "password": "short"},
        {"username": "x", "password": "Test1234!"},
        {"username": 5, "password": "Test1234!"},
        {"username": "tester", "password": 12345678},
        {"username": ["tester"], "password": "Test1234!"},
    ],
)
def test_the_api_refuses_weak_or_odd_accounts_without_crashing(app, client, body):
    response = client.post("/api/register", json=body)
    assert response.status_code == 400
    assert response.json["error"]
    assert app.extensions["data"].load_users() == {}


def test_usernames_are_not_case_sensitive(client):
    client.post("/register", data={"username": "Tester", "password": "Test1234!"})
    page = client.post("/login", data=GOOD, follow_redirects=True)
    assert b"Past audits" in page.data
    client.post("/logout")
    response = client.post("/api/login", json={"username": "TESTER", "password": "Test1234!"})
    assert response.status_code == 200


# ---- No insecure defaults ------------------------------------------------------


def only_these_settings(tmp_path, **settings):
    """An environment with nothing but `settings`, the test encryption key
    and a temporary data folder (so a real users.json is never touched)."""
    env = {
        "DATA_ENCRYPTION_KEY": os.environ["DATA_ENCRYPTION_KEY"],
        "DATA_DIR": str(tmp_path),
    }
    env.update(settings)
    return env


def test_without_a_secret_key_setting_each_start_gets_a_random_key(tmp_path):
    with mock.patch.dict(os.environ, only_these_settings(tmp_path), clear=True):
        config = {"TESTING": True, "DATA_DIR": str(tmp_path)}
        first = create_app(config).config["SECRET_KEY"]
        second = create_app(config).config["SECRET_KEY"]
    assert first != second
    assert len(first) >= 32 and "dev-only" not in first


def test_the_secret_key_setting_is_used_when_given(tmp_path):
    with mock.patch.dict(os.environ, {"FLASK_SECRET_KEY": "from-the-env-file"}):
        app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path)})
        assert app.config["SECRET_KEY"] == "from-the-env-file"


@pytest.mark.parametrize("setting, expected", [(None, False), ("0", False), ("1", True)])
def test_the_debugger_is_off_unless_asked_for(tmp_path, setting, expected):
    env = {} if setting is None else {"FLASK_DEBUG": setting}
    with (
        mock.patch.dict(os.environ, only_these_settings(tmp_path, **env), clear=True),
        mock.patch("flask.Flask.run") as run,
    ):
        runpy.run_path(os.path.join(ROOT, "app.py"), run_name="__main__")
    assert run.call_args.kwargs["debug"] is expected


def test_the_web_server_used_in_docker_is_installed():
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as file:
        packages = [line.split(">")[0].split("=")[0].strip().lower() for line in file]
    assert "gunicorn" in packages
