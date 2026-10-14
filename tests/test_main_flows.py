"""Tests for the controller (main.py). The I/O Manager is replaced by
mocks, so no terminal, keyboard or AI is needed."""

import os
from unittest import mock
import data_manager as dm
import main
from tests.helpers import temp_data_dir, raises


def run_session_quietly(username):
    """main.run_session without the 'you have N saved audits' line."""
    with mock.patch.object(main.in_and_out, "show_audit_count"):
        return main.run_session(username)


def rec(company):
    """A minimal record the Data Manager accepts as a saved audit record."""
    return {"Company Name": company, "Proposal Narrative": "text"}


def test_save_asks_for_a_name_and_saves():
    with temp_data_dir():
        records = [rec("A")]
        with (
            mock.patch.object(
                main.in_and_out, "retrieve_json_filename", return_value="mine"
            ) as ask,
            mock.patch.object(main.in_and_out, "display_save_result") as shown,
        ):
            name = main.save_records_flow(records, "")
        ask.assert_called_once_with(dm.INVALID_FILENAME_CHARS)
        shown.assert_called_once_with("saved", "mine.json")
        assert name == "mine.json"
        assert dm.load_data_from_json("mine")[0] == records


def test_save_reuses_the_name_from_earlier():
    with temp_data_dir():
        with (
            mock.patch.object(main.in_and_out, "retrieve_json_filename") as ask,
            mock.patch.object(main.in_and_out, "display_save_result"),
        ):
            main.save_records_flow([], "again.json")
        ask.assert_not_called()


def test_save_to_an_existing_file_can_be_cancelled():
    with temp_data_dir():
        dm.save_data_to_json([rec("old")], "mine")
        with (
            mock.patch.object(
                main.in_and_out, "ask_existing_file_action", return_value="cancel"
            ),
            mock.patch.object(main.in_and_out, "display_save_result"),
        ):
            main.save_records_flow([rec("new")], "mine")
        assert dm.load_data_from_json("mine")[0] == [rec("old")]


def test_save_to_an_existing_file_can_add_to_it():
    with temp_data_dir():
        dm.save_data_to_json([rec("old")], "mine")
        with (
            mock.patch.object(
                main.in_and_out, "ask_existing_file_action", return_value="add"
            ),
            mock.patch.object(main.in_and_out, "display_save_result"),
        ):
            main.save_records_flow([rec("new")], "mine")
        assert [r["Company Name"] for r in dm.load_data_from_json("mine")[0]] == [
            "old",
            "new",
        ]


def test_save_to_an_existing_file_can_replace_it():
    with temp_data_dir():
        dm.save_data_to_json([rec("old")], "mine")
        with (
            mock.patch.object(
                main.in_and_out, "ask_existing_file_action", return_value="replace"
            ),
            mock.patch.object(main.in_and_out, "display_save_result"),
        ):
            main.save_records_flow([rec("new")], "mine")
        assert [r["Company Name"] for r in dm.load_data_from_json("mine")[0]] == ["new"]


def test_invalid_name_is_reported_and_forgotten():
    with temp_data_dir():
        with mock.patch.object(main.in_and_out, "display_save_result") as shown:
            name = main.save_records_flow([], "bad/name")
        assert name == ""
        assert shown.call_args.args[0] == "invalid_name"


def test_load_replaces_the_records():
    with temp_data_dir():
        dm.save_data_to_json([rec("saved")], "mine")
        with (
            mock.patch.object(
                main.in_and_out, "retrieve_json_filename", return_value="mine"
            ),
            mock.patch.object(main.in_and_out, "display_load_result"),
        ):
            records, name = main.load_records_flow([], "")
        assert (records, name) == ([rec("saved")], "mine.json")


def test_load_can_be_cancelled_when_records_exist():
    with temp_data_dir():
        current = [rec("mine")]
        with (
            mock.patch.object(
                main.in_and_out, "confirm_overwrite_records", return_value=False
            ),
            mock.patch.object(main.in_and_out, "retrieve_json_filename") as ask,
        ):
            records, name = main.load_records_flow(current, "x.json")
        ask.assert_not_called()
        assert (records, name) == (current, "x.json")


def test_failed_load_keeps_the_current_records():
    with temp_data_dir():
        with (
            mock.patch.object(
                main.in_and_out, "retrieve_json_filename", return_value="missing"
            ),
            mock.patch.object(main.in_and_out, "display_load_result") as shown,
        ):
            records, name = main.load_records_flow([], "")
        assert (records, name) == ([], "")
        assert shown.call_args.args[0] == "not_found"


def audit_flow_session():
    return {"username": "alice", "records": [], "ai_audit": {}, "jsonfile_name": ""}


def audit_flow_run_flow(ai_audit, result):
    session = audit_flow_session()
    io = main.in_and_out
    with (
        mock.patch.object(
            main, "collect_application", return_value={"Company Name": "A"}
        ),
        mock.patch.object(main, "run_audit", return_value=(ai_audit, result)),
        mock.patch.object(io, "display_applied_grants"),
        mock.patch.object(io, "confirm_save_to_json", return_value=False),
        mock.patch.object(io, "show_audit_saved_to_history") as saved,
        mock.patch.object(io, "show_audit_not_saved_ai_failed") as not_saved,
    ):
        main.new_application_flow(session, 1)
    return (session, saved, not_saved)


def test_a_good_audit_is_saved_to_history():
    with temp_data_dir():
        decision = {"decision_status": "PRE_APPROVED_TIER_1"}
        session, saved, not_saved = audit_flow_run_flow({"ai_status": "ok"}, decision)
        saved.assert_called_once()
        not_saved.assert_not_called()
        assert len(dm.get_user_audits("alice")) == 1
        assert session["records"] == [{"Company Name": "A"}]


def test_a_failed_ai_call_is_not_saved():
    with temp_data_dir():
        _, saved, not_saved = audit_flow_run_flow(
            {"ai_status": "failed"}, {"decision_status": "MANUAL_REVIEW"}
        )
        saved.assert_not_called()
        not_saved.assert_called_once()
        assert dm.get_user_audits("alice") == []


def test_a_crashed_step_is_not_saved():
    with temp_data_dir():
        _, saved, not_saved = audit_flow_run_flow({}, None)
        saved.assert_not_called()
        not_saved.assert_not_called()
        assert dm.get_user_audits("alice") == []


def edit_and_delete_flow_session():
    return {
        "username": "alice",
        "ai_audit": {},
        "jsonfile_name": "",
        "records": [
            dict(rec("A"), **{"Proposal Type": "Equipment / Energy Upgrade"}),
            rec("B"),
        ],
    }


def test_update_changes_one_field_of_one_record():
    io = main.in_and_out
    session = edit_and_delete_flow_session()
    with (
        mock.patch.object(io, "select_record_index", return_value=1),
        mock.patch.object(io, "select_field_to_edit", return_value="Company Name"),
        mock.patch.object(io, "retrieve_field_value", return_value="Renamed"),
        mock.patch.object(io, "show_record_updated") as shown,
    ):
        main.update_record_flow(session)
    shown.assert_called_once_with("Renamed", "Company Name")
    assert [r["Company Name"] for r in session["records"]] == ["A", "Renamed"]


def test_update_can_be_cancelled_at_either_step():
    io = main.in_and_out
    for index, field in ((None, None), (0, None)):
        session = edit_and_delete_flow_session()
        before = [dict(r) for r in session["records"]]
        with (
            mock.patch.object(io, "select_record_index", return_value=index),
            mock.patch.object(io, "select_field_to_edit", return_value=field),
            mock.patch.object(io, "retrieve_field_value") as ask,
        ):
            main.update_record_flow(session)
        ask.assert_not_called()
        assert session["records"] == before


def test_update_with_no_records_says_so():
    session = {"records": []}
    with mock.patch.object(main.in_and_out, "display_no_records_message") as shown:
        main.update_record_flow(session)
    shown.assert_called_once()


def test_update_converts_a_nested_record_to_the_screen_layout():
    nested = {"company_profile": {"company_name": "N"}, "proposal": {}}
    session = {"records": [nested]}
    io = main.in_and_out
    with (
        mock.patch.object(io, "select_record_index", return_value=0),
        mock.patch.object(io, "select_field_to_edit", return_value="Company Industry"),
        mock.patch.object(io, "retrieve_field_value", return_value="mining"),
        mock.patch.object(io, "show_record_updated"),
    ):
        main.update_record_flow(session)
    assert session["records"][0]["Company Name"] == "N"
    assert session["records"][0]["Company Industry"] == "mining"


def test_delete_removes_the_chosen_record():
    io = main.in_and_out
    session = edit_and_delete_flow_session()
    with (
        mock.patch.object(io, "select_record_index", return_value=0),
        mock.patch.object(io, "confirm_delete_record", return_value=True),
        mock.patch.object(io, "show_record_deleted") as shown,
    ):
        main.delete_record_flow(session)
    shown.assert_called_once_with("A")
    assert [r["Company Name"] for r in session["records"]] == ["B"]


def test_delete_needs_confirmation():
    io = main.in_and_out
    session = edit_and_delete_flow_session()
    with (
        mock.patch.object(io, "select_record_index", return_value=0),
        mock.patch.object(io, "confirm_delete_record", return_value=False),
        mock.patch.object(io, "show_record_not_changed") as shown,
    ):
        main.delete_record_flow(session)
    shown.assert_called_once()
    assert len(session["records"]) == 2


def test_delete_can_be_cancelled():
    session = edit_and_delete_flow_session()
    with (
        mock.patch.object(main.in_and_out, "select_record_index", return_value=None),
        mock.patch.object(main.in_and_out, "confirm_delete_record") as ask,
    ):
        main.delete_record_flow(session)
    ask.assert_not_called()
    assert len(session["records"]) == 2


def test_success_returns_the_result():
    assert main.attempt(lambda a, b: a + b, 1, 2) == (True, 3)


def test_an_error_is_reported_instead_of_raised():
    with mock.patch.object(main.in_and_out, "show_unexpected_error") as shown:
        ok, value = main.attempt(lambda: 1 / 0)
    assert (ok, value) == (False, None)
    shown.assert_called_once()


def test_ctrl_c_and_end_of_input_still_exit():

    def interrupt():
        raise KeyboardInterrupt

    def end_of_input():
        raise EOFError

    with raises(KeyboardInterrupt):
        main.attempt(interrupt)
    with raises(EOFError):
        main.attempt(end_of_input)


def test_exit_ends_the_program():
    with temp_data_dir():
        with (
            mock.patch.object(main.in_and_out, "get_menu_choice", side_effect=[0]),
            mock.patch.object(main.in_and_out, "show_goodbye"),
        ):
            assert not run_session_quietly("alice")


def test_logout_returns_to_the_login_screen_and_clears_the_user():
    with temp_data_dir():
        with (
            mock.patch.object(
                main.in_and_out,
                "get_menu_choice",
                side_effect=[main.in_and_out.MENU_LOGOUT],
            ),
            mock.patch.object(main.in_and_out, "show_logged_out"),
        ):
            assert run_session_quietly("alice")
        assert dm.get_active_user() is None


def test_records_are_saved_in_the_users_own_folder():
    with temp_data_dir() as folder:
        with (
            mock.patch.object(main.in_and_out, "get_menu_choice", side_effect=[2, 0]),
            mock.patch.object(
                main.in_and_out, "retrieve_json_filename", return_value="mine"
            ),
            mock.patch.object(main.in_and_out, "display_save_result"),
            mock.patch.object(main.in_and_out, "show_goodbye"),
        ):
            run_session_quietly("alice")
        assert os.path.exists(os.path.join(folder, "records", "alice", "mine.json"))


def test_a_wrong_menu_number_shows_an_error_and_continues():
    with temp_data_dir():
        with (
            mock.patch.object(main.in_and_out, "get_menu_choice", side_effect=[99, 0]),
            mock.patch.object(main.in_and_out, "show_wrong_option_error") as shown,
            mock.patch.object(main.in_and_out, "show_goodbye"),
        ):
            run_session_quietly("alice")
        shown.assert_called_once()


def test_account_can_be_created_and_logged_into():
    with temp_data_dir():
        io = main.in_and_out
        with (
            mock.patch.object(io, "retrieve_new_username", return_value="alice"),
            mock.patch.object(io, "retrieve_new_password", return_value="password123"),
            mock.patch.object(io, "show_account_created"),
        ):
            main.create_account_flow()
        with (
            mock.patch.object(io, "retrieve_username", return_value="alice"),
            mock.patch.object(io, "retrieve_password", return_value="password123"),
            mock.patch.object(io, "show_login_success"),
        ):
            assert main.login_flow() == "alice"


def test_wrong_password_fails():
    with temp_data_dir():
        io = main.in_and_out
        dm.save_new_user(main.logic.build_new_user_record("alice", "password123"))
        with (
            mock.patch.object(io, "retrieve_username", return_value="alice"),
            mock.patch.object(io, "retrieve_password", return_value="nope-nope"),
            mock.patch.object(io, "show_login_failed") as failed,
        ):
            assert main.login_flow() is None
        failed.assert_called_once()


def test_taken_usernames_are_asked_for_again():
    with temp_data_dir():
        io = main.in_and_out
        dm.save_new_user({"username": "alice"})
        with (
            mock.patch.object(
                io, "retrieve_new_username", side_effect=["alice", "bob"]
            ),
            mock.patch.object(io, "retrieve_new_password", return_value="password123"),
            mock.patch.object(io, "show_username_taken") as taken,
            mock.patch.object(io, "show_account_created") as created,
        ):
            main.create_account_flow()
        taken.assert_called_once_with("alice")
        created.assert_called_once_with("bob")


def test_login_screen_exit_returns_none():
    with temp_data_dir():
        with (
            mock.patch.object(main.in_and_out, "get_auth_choice", side_effect=[0]),
            mock.patch.object(main.in_and_out, "show_goodbye"),
        ):
            assert main.login_screen() is None


def test_login_screen_retries_until_success():
    with temp_data_dir():
        with (
            mock.patch.object(
                main.in_and_out, "get_auth_choice", side_effect=[1, 7, 1]
            ),
            mock.patch.object(main, "login_flow", side_effect=[None, "alice"]),
            mock.patch.object(main.in_and_out, "show_wrong_option_error"),
        ):
            assert main.login_screen() == "alice"


def make_audit(audit_id, company, status):
    return {
        "audit_id": audit_id,
        "timestamp": "2026-10-13T10:00:00",
        "application": {"Company Name": company, "Proposal Narrative": "text"},
        "ai_audit": {"scope_category": "Scope-1", "ai_status": "ok"},
        "result": {"decision_status": status, "approved_subsidy_sgd": 100.0},
    }


def test_history_filter_returns_only_matching_audits():
    audits = [
        make_audit(1, "Apex", "PRE_APPROVED_TIER_1"),
        make_audit(2, "Bolt", "MANUAL_REVIEW"),
    ]
    io = main.in_and_out
    with mock.patch.object(
        io, "retrieve_history_filter", return_value=("status", "MANUAL_REVIEW")
    ):
        assert main.apply_history_filter(audits) == [audits[1]]
    with mock.patch.object(
        io, "retrieve_history_filter", return_value=("company", "ape")
    ):
        assert main.apply_history_filter(audits) == [audits[0]]


def test_history_filter_cancel_or_no_match_returns_none():
    audits = [make_audit(1, "Apex", "MANUAL_REVIEW")]
    io = main.in_and_out
    with mock.patch.object(io, "retrieve_history_filter", return_value=None):
        assert main.apply_history_filter(audits) is None
    with (
        mock.patch.object(
            io, "retrieve_history_filter", return_value=("company", "zzz")
        ),
        mock.patch.object(io, "show_no_matching_audits") as shown,
    ):
        assert main.apply_history_filter(audits) is None
        shown.assert_called_once()


def test_history_flow_filters_then_opens_and_exports_the_audit():
    audits = [
        make_audit(1, "Apex", "PRE_APPROVED_TIER_1"),
        make_audit(2, "Bolt", "MANUAL_REVIEW"),
    ]
    io = main.in_and_out
    with (
        mock.patch.object(dm, "get_user_audits", return_value=audits),
        mock.patch.object(io, "display_audit_history", return_value=True) as listing,
        mock.patch.object(
            io, "choose_history_action", side_effect=[("filter", None), ("open", 0)]
        ),
        mock.patch.object(
            io, "retrieve_history_filter", return_value=("company", "bolt")
        ),
        mock.patch.object(io, "display_audit_detail") as detail,
        mock.patch.object(io, "confirm_export_pdf", return_value=True),
        mock.patch.object(
            dm, "export_audit_to_pdf", return_value=("a.pdf", "exported")
        ) as export,
        mock.patch.object(io, "show_pdf_result") as result,
        mock.patch.object(io, "wait_for_return"),
    ):
        main.audit_history_flow("alice")
    assert listing.call_args_list[1].args[0] == [audits[1]]
    detail.assert_called_once_with(audits[1])
    export.assert_called_once_with(audits[1])
    assert result.call_args.args[:2] == ("exported", "a.pdf")


def test_history_flow_with_no_audits_returns_straight_away():
    io = main.in_and_out
    with (
        mock.patch.object(dm, "get_user_audits", return_value=[]),
        mock.patch.object(io, "display_audit_history", return_value=False),
        mock.patch.object(io, "choose_history_action") as choose,
    ):
        main.audit_history_flow("alice")
    choose.assert_not_called()


def test_declining_the_pdf_export_creates_nothing():
    io = main.in_and_out
    with (
        mock.patch.object(io, "confirm_export_pdf", return_value=False),
        mock.patch.object(dm, "export_audit_to_pdf") as export,
    ):
        main.export_audit_flow(make_audit(1, "Apex", "MANUAL_REVIEW"))
    export.assert_not_called()


def test_the_interrupt_handler_uses_the_io_layer_to_speak():
    io = main.in_and_out
    with mock.patch.object(io, "show_interrupted") as interrupted:
        main._handle_uncaught(KeyboardInterrupt, KeyboardInterrupt(), None)
    interrupted.assert_called_once()
    with mock.patch.object(io, "show_input_ended") as ended:
        main._handle_uncaught(EOFError, EOFError(), None)
    ended.assert_called_once()


def test_login_shows_how_many_audits_are_saved():
    with temp_data_dir():
        io = main.in_and_out
        with (
            mock.patch.object(io, "get_menu_choice", side_effect=[0]),
            mock.patch.object(io, "show_goodbye"),
            mock.patch.object(io, "show_audit_count") as count,
        ):
            main.run_session("alice")
        count.assert_called_once_with(0)


def test_main_starts_with_the_welcome_screen_through_the_io_layer():
    io = main.in_and_out
    with (
        mock.patch.object(dm, "setup_logging") as logging_on,
        mock.patch.object(io, "show_welcome_sequence") as welcome,
        mock.patch.object(io, "wait_for_continue") as wait,
        mock.patch.object(main, "login_screen", return_value=None),
        mock.patch.object(main.sys, "excepthook", main.sys.excepthook),
    ):
        main.main()
    logging_on.assert_called_once()
    welcome.assert_called_once()
    wait.assert_called_once()
