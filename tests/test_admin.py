"""Tests for the administrator feature: who is an admin (AccessPolicy), the
account changes the Data Manager makes (list, role, password, archive on
delete) and the admin console flows in the controller. The I/O Manager is
mocked, so no keyboard is needed."""

import json
import os
from unittest import mock

from main import Application
from managers.io_manager import IOManager
from managers.logic_manager import AccessPolicy, LogicManager, RuleConfig
from tests.helpers import raises, temp_data_dir

BOSS = "boss"  # the ADMIN_USERNAME used in these tests


def make_logic():
    return LogicManager(admin_username=BOSS)


def add_user(dm, logic, name, password="secret123", role="user"):
    assert dm.save_new_user(logic.build_new_user_record(name, password, role=role))


def admin_app(dm):
    """An Application whose ADMIN_USERNAME is BOSS, with BOSS, alice and bob."""
    app = Application(logic=make_logic(), data=dm)
    for name in (BOSS, "alice", "bob"):
        add_user(dm, app.logic, name, role="admin" if name == BOSS else "user")
    return app


def read_json(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


# ---- AccessPolicy (Logic Manager) --------------------------------------------


def test_roles_come_from_the_record_or_the_admin_setting():
    policy = AccessPolicy(" Boss ")  # tidied like a typed username
    assert policy.bootstrap_admin == "boss"
    assert policy.is_admin("boss", None)
    assert policy.is_admin("carol", {"role": "admin"})
    assert not policy.is_admin("carol", {"role": "user"})
    assert not policy.is_admin("carol", {})
    assert not policy.is_admin("carol", None)
    assert not AccessPolicy(None).is_admin("", None)


def test_admins_cannot_demote_or_delete_themselves_or_the_main_admin():
    policy = AccessPolicy("boss")
    assert policy.role_change_problem("ann", "ann", "user")
    assert policy.role_change_problem("ann", "boss", "user")
    assert policy.role_change_problem("ann", "carl", "superuser")
    assert policy.role_change_problem("ann", "carl", "admin") is None
    assert policy.role_change_problem("ann", "carl", "user") is None
    assert policy.deletion_problem("ann", "ann")
    assert policy.deletion_problem("ann", "boss")
    assert policy.deletion_problem("ann", "carl") is None


def test_the_admin_name_is_read_from_the_environment():
    with mock.patch.dict(os.environ, {"ADMIN_USERNAME": "chief"}):
        assert LogicManager().access.bootstrap_admin == "chief"
    with mock.patch.dict(os.environ, {}, clear=True):
        assert LogicManager().access.bootstrap_admin is None


def test_new_accounts_get_a_role():
    logic = make_logic()
    assert logic.build_new_user_record("a_user", "secret123")["role"] == "user"
    assert logic.build_new_user_record("an_admin", "secret123", "admin")["role"] == "admin"
    with raises(ValueError):
        logic.build_new_user_record("x_user", "secret123", "owner")


# ---- Account management (Data Manager) ---------------------------------------


def test_the_user_list_never_contains_password_data():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        dm.append_user_audit("alice", {"Company Name": "A"}, {}, {})
        users = dm.list_users()
        assert [u["username"] for u in users] == ["alice", "bob", BOSS]
        assert {u["username"]: u["audit_count"] for u in users} == {
            "alice": 1,
            "bob": 0,
            BOSS: 0,
        }
        for user in users:
            assert set(user) == {"username", "role", "created_at", "audit_count"}
        assert app.is_admin(BOSS)


def test_old_accounts_without_a_role_are_ordinary_users():
    with temp_data_dir() as (dm, _):
        logic = make_logic()
        record = logic.build_new_user_record("olduser", "secret123")
        del record["role"]  # as saved by the Phase 1 version
        dm.save_new_user(record)
        assert dm.list_users()[0]["role"] == "user"
        assert not logic.is_admin("olduser", dm.get_user("olduser"))


def test_a_role_can_be_changed():
    with temp_data_dir() as (dm, _):
        logic = make_logic()
        add_user(dm, logic, "alice")
        assert dm.set_user_role("alice", "admin")
        assert logic.is_admin("alice", dm.get_user("alice"))
        assert not dm.set_user_role("nobody", "admin")


def test_a_password_reset_replaces_only_the_password():
    with temp_data_dir() as (dm, _):
        logic = make_logic()
        add_user(dm, logic, "alice", password="oldpass123")
        created = dm.get_user("alice")["created_at"]
        assert dm.set_user_password("alice", logic.hash_password("newpass456"))
        stored = dm.get_user("alice")
        assert logic.verify_password("newpass456", stored)
        assert not logic.verify_password("oldpass123", stored)
        assert stored["created_at"] == created and stored["role"] == "user"
        assert "newpass456" not in json.dumps(stored)
        assert not dm.set_user_password("nobody", logic.hash_password("x1234567"))


def test_deleting_a_user_archives_everything_and_removes_the_login():
    with temp_data_dir() as (dm, folder):
        logic = make_logic()
        add_user(dm, logic, "alice")
        add_user(dm, logic, "bob")
        dm.append_user_audit("alice", {"Company Name": "A"}, {}, {})
        dm.append_user_audit("bob", {"Company Name": "B"}, {}, {})
        dm.active_user = "alice"
        dm.save_data_to_json([{"Company Name": "A", "Proposal Narrative": "x"}], "mine")
        dm.active_user = None

        archive, status = dm.archive_user("alice", deleted_by=BOSS)

        assert status == "archived"
        assert archive.startswith(os.path.abspath(os.path.join(folder, "archive", "alice_")))
        account = read_json(os.path.join(archive, "account.json"))
        assert account["username"] == "alice" and account["deleted_by"] == BOSS
        for secret in dm.PASSWORD_FIELDS:
            assert secret not in account
        assert len(read_json(os.path.join(archive, "audit_history.json"))) == 1
        assert os.path.isfile(os.path.join(archive, "records", "mine.json"))
        assert not os.path.exists(os.path.join(folder, "records", "alice"))
        # alice can no longer log in; bob is untouched
        assert dm.get_user("alice") is None and dm.get_user_audits("alice") == []
        assert dm.get_user("bob") is not None and len(dm.get_user_audits("bob")) == 1


def test_deleting_a_user_without_saved_files_still_works():
    with temp_data_dir() as (dm, _):
        add_user(dm, make_logic(), "alice")
        archive, status = dm.archive_user("alice", deleted_by=BOSS)
        assert status == "archived" and os.path.isdir(archive)


def test_deleting_the_same_name_twice_keeps_both_archives():
    with temp_data_dir() as (dm, _):
        logic = make_logic()
        add_user(dm, logic, "alice")
        first, _ = dm.archive_user("alice", deleted_by=BOSS)
        add_user(dm, logic, "alice")
        second, _ = dm.archive_user("alice", deleted_by=BOSS)
        assert first != second and os.path.isdir(first) and os.path.isdir(second)


def test_deleting_unknown_or_unsafe_names_changes_nothing():
    with temp_data_dir() as (dm, folder):
        add_user(dm, make_logic(), "alice")
        assert dm.archive_user("nobody", deleted_by=BOSS) == (None, "not_found")
        assert dm.archive_user("../alice", deleted_by=BOSS) == (None, "unsafe_name")
        assert dm.get_user("alice") is not None
        assert not os.path.exists(os.path.join(folder, "archive"))


def test_a_failed_delete_leaves_the_account_and_files_in_place():
    with temp_data_dir() as (dm, folder):
        add_user(dm, make_logic(), "alice")
        dm.active_user = "alice"
        dm.save_data_to_json([{"Company Name": "A", "Proposal Narrative": "x"}], "mine")
        dm.active_user = None
        real_write = dm._store.write_json_file

        def fail_users_file(name, data):
            return False if name == dm.USERS_FILE else real_write(name, data)

        with mock.patch.object(dm._store, "write_json_file", side_effect=fail_users_file):
            assert dm.archive_user("alice", deleted_by=BOSS) == (None, "io_error")
        assert dm.get_user("alice") is not None
        assert os.path.isfile(os.path.join(folder, "records", "alice", "mine.json"))


# ---- Start-up: the ADMIN_USERNAME account ------------------------------------


def test_the_admin_account_is_created_on_first_run():
    with temp_data_dir() as (dm, _):
        app = Application(logic=make_logic(), data=dm)
        with (
            mock.patch.object(app.io, "show_admin_setup") as told,
            mock.patch.object(app.io, "retrieve_new_password", return_value="secret123"),
            mock.patch.object(app.io, "show_account_created"),
        ):
            app.ensure_admin_account()
        told.assert_called_once_with(BOSS)
        assert app.is_admin(BOSS)
        assert app.logic.verify_password("secret123", dm.get_user(BOSS))


def test_an_existing_admin_account_is_left_alone():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        with mock.patch.object(app.io, "retrieve_new_password") as asked:
            app.ensure_admin_account()
        asked.assert_not_called()


def test_no_admin_setting_means_no_setup_and_no_admin():
    with temp_data_dir() as (dm, _):
        app = Application(logic=LogicManager(admin_username=""), data=dm)
        with mock.patch.object(app.io, "retrieve_new_password") as asked:
            app.ensure_admin_account()
        asked.assert_not_called()
        assert dm.load_users() == {}


def test_an_unusable_admin_name_is_reported():
    with temp_data_dir() as (dm, _):
        app = Application(logic=LogicManager(admin_username="bad name!"), data=dm)
        with (
            mock.patch.object(app.io, "show_admin_name_invalid") as told,
            mock.patch.object(app.io, "retrieve_new_password") as asked,
        ):
            app.ensure_admin_account()
        told.assert_called_once()
        asked.assert_not_called()


def test_nobody_else_can_register_the_admin_name():
    with temp_data_dir() as (dm, _):
        app = Application(logic=make_logic(), data=dm)
        assert app.username_is_taken(BOSS)
        with (
            mock.patch.object(app.io, "retrieve_new_username", side_effect=[BOSS, "carol"]),
            mock.patch.object(app.io, "show_username_taken") as taken,
            mock.patch.object(app.io, "retrieve_new_password", return_value="secret123"),
            mock.patch.object(app.io, "show_account_created"),
        ):
            app.create_account_flow()
        taken.assert_called_once_with(BOSS)
        assert dm.get_user(BOSS) is None and dm.get_user("carol")["role"] == "user"


# ---- The menu ----------------------------------------------------------------


def run_menu(app, username, choices):
    with (
        mock.patch.object(app.io, "show_audit_count"),
        mock.patch.object(app.io, "get_menu_choice", side_effect=choices) as menu,
        mock.patch.object(app.io, "show_goodbye"),
        mock.patch.object(app.io, "show_wrong_option_error") as wrong,
        mock.patch.object(app, "admin_console_flow") as console,
    ):
        app.run_session(username)
    return menu, wrong, console


def test_only_admins_see_and_can_open_the_admin_console():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        menu, wrong, console = run_menu(app, BOSS, [IOManager.MENU_ADMIN, 0])
        assert menu.call_args.args == (BOSS, True)
        console.assert_called_once_with(BOSS)
        wrong.assert_not_called()

        menu, wrong, console = run_menu(app, "alice", [IOManager.MENU_ADMIN, 0])
        assert menu.call_args.args == ("alice", False)
        console.assert_not_called()
        wrong.assert_called_once()


def test_the_console_closes_if_the_user_is_no_longer_an_admin():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        with (
            mock.patch.object(app.io, "show_admin_only") as refused,
            mock.patch.object(app.io, "get_admin_choice") as asked,
        ):
            app.admin_console_flow("alice")
        refused.assert_called_once()
        asked.assert_not_called()


def console(app, actor, choices, **io_answers):
    """Runs the admin console with the given menu choices (0 is appended)."""
    patches = [
        mock.patch.object(app.io, "get_admin_choice", side_effect=[*choices, 0]),
        mock.patch.object(app.io, "show_admin_message"),
        mock.patch.object(app.io, "display_user_list"),
        mock.patch.object(app.io, "display_rule_config"),
    ]
    for name, value in io_answers.items():
        if isinstance(value, list):
            patches.append(mock.patch.object(app.io, name, side_effect=value))
        else:
            patches.append(mock.patch.object(app.io, name, return_value=value))
    started = [patch.start() for patch in patches]
    try:
        app.admin_console_flow(actor)
    finally:
        for patch in patches:
            patch.stop()
    return dict(zip(["choice", "message", "user_list", "rules"], started))


def last_message(mocks):
    return mocks["message"].call_args.args


# ---- Admin console: accounts -------------------------------------------------


def test_listing_users_shows_effective_roles():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        mocks = console(app, BOSS, [1])
        shown = mocks["user_list"].call_args.args[0]
        assert {u["username"]: u["role"] for u in shown} == {
            "alice": "user",
            "bob": "user",
            BOSS: "admin",
        }


def test_an_admin_can_create_a_user_with_a_role():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        console(
            app,
            BOSS,
            [2],
            retrieve_new_username="carol",
            retrieve_role="admin",
            retrieve_new_password="secret123",
        )
        assert app.is_admin("carol")
        assert app.logic.verify_password("secret123", dm.get_user("carol"))


def test_creating_a_user_can_be_cancelled_at_the_role():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        console(app, BOSS, [2], retrieve_new_username="carol", retrieve_role=None)
        assert dm.get_user("carol") is None


def test_an_admin_can_reset_a_password():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        console(
            app,
            BOSS,
            [3],
            select_user="alice",
            retrieve_new_password="fresh9999",
        )
        assert app.logic.verify_password("fresh9999", dm.get_user("alice"))


def test_an_admin_can_promote_and_demote_others():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        console(app, BOSS, [4], select_user="alice", retrieve_role="admin")
        assert app.is_admin("alice")
        console(app, BOSS, [4], select_user="alice", retrieve_role="user")
        assert not app.is_admin("alice")


def test_role_changes_that_break_the_rules_are_refused():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        dm.set_user_role("alice", "admin")
        mocks = console(app, "alice", [4], select_user="alice", retrieve_role="user")
        assert last_message(mocks)[1] is False
        assert app.is_admin("alice")
        mocks = console(app, "alice", [4], select_user=BOSS, retrieve_role="user")
        assert last_message(mocks)[1] is False
        assert app.is_admin(BOSS)


def test_an_admin_can_delete_a_user_and_the_data_is_archived():
    with temp_data_dir() as (dm, folder):
        app = admin_app(dm)
        mocks = console(app, BOSS, [5], select_user="bob", confirm_delete_user=True)
        assert dm.get_user("bob") is None
        assert "archived" in last_message(mocks)[0]
        assert os.listdir(os.path.join(folder, "archive"))[0].startswith("bob_")


def test_deleting_needs_the_typed_confirmation():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        console(app, BOSS, [5], select_user="bob", confirm_delete_user=False)
        assert dm.get_user("bob") is not None


def test_an_admin_cannot_delete_themselves_or_the_main_admin():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        dm.set_user_role("alice", "admin")
        for target in ("alice", BOSS):
            mocks = console(
                app, "alice", [5], select_user=target, confirm_delete_user=True
            )
            assert last_message(mocks)[1] is False
            assert dm.get_user(target) is not None


# ---- Admin console: grant rule thresholds ------------------------------------


def test_changing_a_threshold_saves_it_and_applies_it():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        console(app, BOSS, [7], select_rule_setting=1, retrieve_threshold_value=12.0)
        assert app.logic.rule_config.provisional_min_pct == 12.0
        values, status = dm.load_rule_config()
        assert status == "loaded" and values["provisional_min_pct"] == 12.0


def test_an_invalid_threshold_is_explained_and_not_saved():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        with mock.patch.object(app.io, "show_rule_problems") as problems:
            console(app, BOSS, [7], select_rule_setting=0, retrieve_threshold_value=50.0)
        assert problems.call_args.args[0]  # e.g. "must not decrease"
        assert app.logic.rule_config == RuleConfig()
        assert dm.load_rule_config() == (None, "missing")


def test_changing_a_threshold_can_be_cancelled():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        console(app, BOSS, [7], select_rule_setting=1, retrieve_threshold_value=None)
        console(app, BOSS, [7], select_rule_setting=None)
        assert dm.load_rule_config() == (None, "missing")


def test_a_failed_save_does_not_change_the_thresholds():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        with mock.patch.object(dm, "save_rule_config", return_value=False):
            console(app, BOSS, [7], select_rule_setting=1, retrieve_threshold_value=12.0)
        assert app.logic.rule_config == RuleConfig()


def test_thresholds_can_be_reset_to_the_defaults():
    with temp_data_dir() as (dm, _):
        app = admin_app(dm)
        console(app, BOSS, [7], select_rule_setting=1, retrieve_threshold_value=12.0)
        console(app, BOSS, [8], confirm_reset_rules=True)
        assert app.logic.rule_config == RuleConfig()
        assert dm.load_rule_config()[0] == RuleConfig().to_dict()


def test_saved_thresholds_are_used_at_the_next_login():
    with temp_data_dir() as (dm, _):
        dm.save_rule_config(
            dict(RuleConfig().to_dict(), provisional_min_pct=12.0), changed_by=BOSS
        )
        app = Application(logic=make_logic(), data=dm)
        app.load_rule_settings()
        assert app.logic.rule_config.provisional_min_pct == 12.0


def test_unusable_saved_thresholds_fall_back_to_the_defaults_with_a_warning():
    with temp_data_dir() as (dm, folder):
        app = Application(logic=make_logic(), data=dm)
        app.logic.use_rule_config(RuleConfig().with_value("provisional_min_pct", 12))
        dm.save_rule_config({"minimum_impact_pct": "ten"}, changed_by="x")
        with mock.patch.object(app.io, "show_rule_settings_problem") as warned:
            app.load_rule_settings()
        assert warned.call_args.args[0] == "invalid"
        assert app.logic.rule_config == RuleConfig()

        with open(os.path.join(folder, dm.RULES_CONFIG_FILE), "w") as file:
            file.write("{broken")
        with mock.patch.object(app.io, "show_rule_settings_problem") as warned:
            app.load_rule_settings()
        assert warned.call_args.args[0] == "corrupt"


def test_new_audits_record_the_thresholds_in_use():
    with temp_data_dir() as (dm, _):
        app = Application(logic=make_logic(), data=dm)
        app.logic.use_rule_config(RuleConfig().with_value("provisional_min_pct", 12))
        session = mock.Mock(records=[], username="alice", ai_audit={})
        with (
            mock.patch.object(app, "collect_application", return_value={"Company Name": "A"}),
            mock.patch.object(
                app, "run_audit", return_value=({"ai_status": "ok"}, {"decision_status": "X"})
            ),
            mock.patch.object(app.io, "display_applied_grants"),
            mock.patch.object(app.io, "show_audit_saved_to_history"),
            mock.patch.object(app.io, "confirm_save_to_json", return_value=False),
        ):
            app.new_application_flow(session, 1)
        assert dm.get_user_audits("alice")[0]["rules_used"]["provisional_min_pct"] == 12.0
