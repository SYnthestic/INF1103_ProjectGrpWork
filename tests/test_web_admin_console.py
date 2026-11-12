"""The web admin console (/admin): only admins get in, and accounts and
thresholds change with the same rules as the terminal admin console."""

import html
import os
import re

import pytest

from managers.logic_manager import LogicManager, RuleConfig

BOSS = {"username": "boss", "password": "Boss1234!"}      # the ADMIN_USERNAME account
ALICE = {"username": "alice", "password": "Alice1234!"}   # an ordinary user


def flashes(page):
    """The flash messages on a page, as plain text (Jinja escapes quotes)."""
    found = re.findall(rb'<div class="flash">(.*?)</div>', page.data)
    return [html.unescape(m.decode()) for m in found]


@pytest.fixture
def site(app, client):
    """An app whose ADMIN_USERNAME is 'boss', with boss (admin) and alice."""
    logic = LogicManager(admin_username="boss")
    app.extensions["logic"] = logic
    data = app.extensions["data"]
    data.save_new_user(logic.build_new_user_record("boss", BOSS["password"], role="admin"))
    data.save_new_user(logic.build_new_user_record("alice", ALICE["password"]))
    return app, client, data, logic


def log_in(client, who):
    client.post("/logout", data={"force": "1"})
    client.post("/login", data=who)


@pytest.fixture
def admin(site):
    app, client, data, logic = site
    log_in(client, BOSS)
    return client, data, logic


# ---- Who gets in ---------------------------------------------------------------


def test_visitors_are_sent_to_log_in(site):
    _, client, _, _ = site
    response = client.get("/admin")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_ordinary_users_are_refused(site):
    _, client, data, _ = site
    log_in(client, ALICE)
    page = client.get("/admin")
    assert page.status_code == 403 and b"Administrators only" in page.data
    assert client.post("/admin/users/boss/delete", data={"confirm": "boss"}).status_code == 403
    assert data.get_user("boss") is not None


def test_only_admins_see_the_admin_link(site):
    _, client, _, _ = site
    log_in(client, ALICE)
    assert b'href="/admin"' not in client.get("/history").data
    log_in(client, BOSS)
    assert b'href="/admin"' in client.get("/history").data


def test_the_console_lists_users_without_password_data(admin):
    client, _, _ = admin
    page = client.get("/admin").data.decode()
    assert "alice" in page and "boss" in page and "main admin" in page
    assert "password_hash" not in page and "salt" not in page


def test_a_demoted_admin_loses_access_at_once(admin):
    client, data, _ = admin
    data.save_new_user(LogicManager(admin_username="").build_new_user_record(
        "carol", "Carol1234!", role="admin"))
    log_in(client, {"username": "carol", "password": "Carol1234!"})
    assert client.get("/admin").status_code == 200
    data.set_user_role("carol", "user")
    assert client.get("/admin").status_code == 403


# ---- Accounts ------------------------------------------------------------------


def test_an_admin_can_create_a_user_with_a_role(admin):
    client, data, logic = admin
    page = client.post(
        "/admin/users",
        data={"username": "Dave_01", "password": "Dave1234!", "role": "admin"},
        follow_redirects=True,
    )
    assert "Account 'dave_01' created as admin." in flashes(page)
    assert logic.is_admin("dave_01", data.get_user("dave_01"))


@pytest.mark.parametrize(
    "form, message",
    [
        ({"username": "ab", "password": "Dave1234!", "role": "user"}, "Username must be"),
        ({"username": "dave", "password": "short", "role": "user"}, "at least 8 characters"),
        ({"username": "alice", "password": "Dave1234!", "role": "user"}, "already taken"),
        ({"username": "dave", "password": "Dave1234!", "role": "owner"}, "Choose a role"),
    ],
)
def test_bad_new_accounts_are_refused(admin, form, message):
    client, data, _ = admin
    page = client.post("/admin/users", data=form, follow_redirects=True)
    assert any(message in text for text in flashes(page)), flashes(page)
    assert data.get_user("dave") is None


def test_an_admin_can_reset_a_password(admin):
    client, data, logic = admin
    page = client.post("/admin/users/alice/password", data={"password": "Fresh9999"},
                       follow_redirects=True)
    assert "Password for 'alice' changed." in flashes(page)
    assert logic.verify_password("Fresh9999", data.get_user("alice"))
    page = client.post("/admin/users/alice/password", data={"password": "weak"},
                       follow_redirects=True)
    assert any("Not changed" in text for text in flashes(page))


def test_roles_follow_the_access_rules(admin):
    client, data, logic = admin
    client.post("/admin/users/alice/role", data={"role": "admin"})
    assert logic.is_admin("alice", data.get_user("alice"))
    page = client.post("/admin/users/boss/role", data={"role": "user"}, follow_redirects=True)
    assert any("main administrator" in text for text in flashes(page))
    assert logic.is_admin("boss", data.get_user("boss"))


def test_deleting_needs_the_typed_name_and_archives_the_data(admin):
    client, data, _ = admin
    page = client.post("/admin/users/alice/delete", data={"confirm": "alic"},
                       follow_redirects=True)
    assert any("Type 'alice' exactly" in text for text in flashes(page))
    assert data.get_user("alice") is not None

    page = client.post("/admin/users/alice/delete", data={"confirm": "alice"},
                       follow_redirects=True)
    assert any("was deleted" in text for text in flashes(page))
    assert data.get_user("alice") is None
    assert os.listdir(os.path.join(data.data_dir, "archive"))[0].startswith("alice_")


def test_admins_cannot_delete_themselves_or_the_main_admin(admin):
    client, data, _ = admin
    page = client.post("/admin/users/boss/delete", data={"confirm": "boss"},
                       follow_redirects=True)
    assert any("Not changed" in text for text in flashes(page))
    assert data.get_user("boss") is not None


def test_a_deleted_user_is_logged_out_on_their_next_request(site):
    app, client, data, _ = site
    log_in(client, ALICE)
    assert client.get("/history").status_code == 200
    data.archive_user("alice", deleted_by="boss")
    response = client.get("/history")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


# ---- Grant rule thresholds ----------------------------------------------------


def thresholds(**changes):
    values = {name: f"{value:g}" for name, value in RuleConfig().to_dict().items()}
    values.update(changes)
    return values


def test_thresholds_can_be_changed_and_are_used_at_once(admin):
    client, data, logic = admin
    page = client.post("/admin/thresholds", data=thresholds(provisional_min_pct="12"),
                       follow_redirects=True)
    assert "Saved. New decisions use these thresholds." in flashes(page)
    assert logic.rule_config.provisional_min_pct == 12.0
    stored, status = data.load_rule_config()
    assert status == "loaded" and stored["provisional_min_pct"] == 12.0
    assert b"Energy reduction of at least 12%" in client.get("/").data


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"minimum_impact_pct": "16"}, "must not decrease"),
        ({"fast_track_min_pct": "nan"}, "must be a number"),
        ({"eeg_advanced_min_tonnes": "0"}, "must be above 0"),
    ],
)
def test_invalid_thresholds_are_explained_and_not_saved(admin, changes, message):
    client, data, logic = admin
    page = client.post("/admin/thresholds", data=thresholds(**changes), follow_redirects=True)
    assert any(message in text for text in flashes(page)), flashes(page)
    assert data.load_rule_config() == (None, "missing")
    assert logic.rule_config == RuleConfig()


def test_thresholds_can_be_reset_to_the_defaults(admin):
    client, data, logic = admin
    client.post("/admin/thresholds", data=thresholds(provisional_min_pct="12"))
    client.post("/admin/thresholds/reset")
    assert logic.rule_config == RuleConfig()
    assert data.load_rule_config()[0] == RuleConfig().to_dict()
