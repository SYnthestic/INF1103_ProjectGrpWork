"""Tests for the controller (main.py). The I/O Manager is replaced by
mocks, so no terminal, keyboard or AI is needed."""

import os
import tempfile
import unittest
from unittest import mock

import data_manager as dm
import main


def rec(company):
    """A minimal record the Data Manager accepts as a saved audit record."""
    return {"Company Name": company, "Proposal Narrative": "text"}


class TempDataDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = dm.DATA_DIR
        dm.DATA_DIR = self._tmp.name
        dm.set_active_user(None)

    def tearDown(self):
        dm.set_active_user(None)
        dm.DATA_DIR = self._old_dir
        self._tmp.cleanup()


class SaveLoadFlowTests(TempDataDir):
    def test_save_asks_for_a_name_and_saves(self):
        records = [rec("A")]
        with mock.patch.object(main.in_and_out, "retrieve_json_filename", return_value="mine") as ask, \
                mock.patch.object(main.in_and_out, "display_save_result") as shown:
            name = main.save_records_flow(records, "")
        ask.assert_called_once_with(dm.INVALID_FILENAME_CHARS)
        shown.assert_called_once_with("saved", "mine.json")
        self.assertEqual(name, "mine.json")
        self.assertEqual(dm.load_data_from_json("mine")[0], records)

    def test_save_reuses_the_name_from_earlier(self):
        with mock.patch.object(main.in_and_out, "retrieve_json_filename") as ask, \
                mock.patch.object(main.in_and_out, "display_save_result"):
            main.save_records_flow([], "again.json")
        ask.assert_not_called()

    def test_save_to_an_existing_file_can_be_cancelled(self):
        dm.save_data_to_json([rec("old")], "mine")
        with mock.patch.object(main.in_and_out, "confirm_append_to_existing_file", return_value=False), \
                mock.patch.object(main.in_and_out, "display_save_result"):
            main.save_records_flow([rec("new")], "mine")
        self.assertEqual(dm.load_data_from_json("mine")[0], [rec("old")])

    def test_save_to_an_existing_file_can_add_to_it(self):
        dm.save_data_to_json([rec("old")], "mine")
        with mock.patch.object(main.in_and_out, "confirm_append_to_existing_file", return_value=True), \
                mock.patch.object(main.in_and_out, "display_save_result"):
            main.save_records_flow([rec("new")], "mine")
        self.assertEqual([r["Company Name"] for r in dm.load_data_from_json("mine")[0]], ["old", "new"])

    def test_invalid_name_is_reported_and_forgotten(self):
        with mock.patch.object(main.in_and_out, "display_save_result") as shown:
            name = main.save_records_flow([], "bad/name")
        self.assertEqual(name, "")
        self.assertEqual(shown.call_args.args[0], "invalid_name")

    def test_load_replaces_the_records(self):
        dm.save_data_to_json([rec("saved")], "mine")
        with mock.patch.object(main.in_and_out, "retrieve_json_filename", return_value="mine"), \
                mock.patch.object(main.in_and_out, "display_load_result"):
            records, name = main.load_records_flow([], "")
        self.assertEqual((records, name), ([rec("saved")], "mine.json"))

    def test_load_can_be_cancelled_when_records_exist(self):
        current = [rec("mine")]
        with mock.patch.object(main.in_and_out, "confirm_overwrite_records", return_value=False), \
                mock.patch.object(main.in_and_out, "retrieve_json_filename") as ask:
            records, name = main.load_records_flow(current, "x.json")
        ask.assert_not_called()
        self.assertEqual((records, name), (current, "x.json"))

    def test_failed_load_keeps_the_current_records(self):
        with mock.patch.object(main.in_and_out, "retrieve_json_filename", return_value="missing"), \
                mock.patch.object(main.in_and_out, "display_load_result") as shown:
            records, name = main.load_records_flow([], "")
        self.assertEqual((records, name), ([], ""))
        self.assertEqual(shown.call_args.args[0], "not_found")


class AuditFlowTests(TempDataDir):
    def session(self):
        return {"username": "alice", "records": [], "ai_audit": {}, "jsonfile_name": ""}

    def run_flow(self, ai_audit, result):
        session = self.session()
        io = main.in_and_out
        with mock.patch.object(main, "collect_application", return_value={"Company Name": "A"}), \
                mock.patch.object(main, "run_audit", return_value=(ai_audit, result)), \
                mock.patch.object(io, "display_applied_grants"), \
                mock.patch.object(io, "confirm_save_to_json", return_value=False), \
                mock.patch.object(io, "show_audit_saved_to_history") as saved, \
                mock.patch.object(io, "show_audit_not_saved_ai_failed") as not_saved:
            main.new_application_flow(session, 1)
        return session, saved, not_saved

    def test_a_good_audit_is_saved_to_history(self):
        decision = {"decision_status": "PRE_APPROVED_TIER_1"}
        session, saved, not_saved = self.run_flow({"ai_status": "ok"}, decision)
        saved.assert_called_once()
        not_saved.assert_not_called()
        self.assertEqual(len(dm.get_user_audits("alice")), 1)
        self.assertEqual(session["records"], [{"Company Name": "A"}])

    def test_a_failed_ai_call_is_not_saved(self):
        _, saved, not_saved = self.run_flow({"ai_status": "failed"}, {"decision_status": "MANUAL_REVIEW"})
        saved.assert_not_called()
        not_saved.assert_called_once()
        self.assertEqual(dm.get_user_audits("alice"), [])

    def test_a_crashed_step_is_not_saved(self):
        _, saved, not_saved = self.run_flow({}, None)
        saved.assert_not_called()
        not_saved.assert_not_called()
        self.assertEqual(dm.get_user_audits("alice"), [])


class AttemptTests(unittest.TestCase):
    def test_success_returns_the_result(self):
        self.assertEqual(main.attempt(lambda a, b: a + b, 1, 2), (True, 3))

    def test_an_error_is_reported_instead_of_raised(self):
        with mock.patch.object(main.in_and_out, "show_unexpected_error") as shown:
            ok, value = main.attempt(lambda: 1 / 0)
        self.assertEqual((ok, value), (False, None))
        shown.assert_called_once()

    def test_ctrl_c_and_end_of_input_still_exit(self):
        def interrupt():
            raise KeyboardInterrupt
        def end_of_input():
            raise EOFError
        with self.assertRaises(KeyboardInterrupt):
            main.attempt(interrupt)
        with self.assertRaises(EOFError):
            main.attempt(end_of_input)


class SessionTests(TempDataDir):
    def test_exit_ends_the_program(self):
        with mock.patch.object(main.in_and_out, "get_menu_choice", side_effect=[0]), \
                mock.patch.object(main.in_and_out, "show_goodbye"):
            self.assertFalse(main.run_session("alice"))

    def test_logout_returns_to_the_login_screen_and_clears_the_user(self):
        with mock.patch.object(main.in_and_out, "get_menu_choice", side_effect=[main.in_and_out.MENU_LOGOUT]), \
                mock.patch.object(main.in_and_out, "show_logged_out"):
            self.assertTrue(main.run_session("alice"))
        self.assertIsNone(dm.get_active_user())

    def test_records_are_saved_in_the_users_own_folder(self):
        with mock.patch.object(main.in_and_out, "get_menu_choice", side_effect=[2, 0]), \
                mock.patch.object(main.in_and_out, "retrieve_json_filename", return_value="mine"), \
                mock.patch.object(main.in_and_out, "display_save_result"), \
                mock.patch.object(main.in_and_out, "show_goodbye"):
            main.run_session("alice")
        self.assertTrue(os.path.exists(os.path.join(self._tmp.name, "records", "alice", "mine.json")))

    def test_a_wrong_menu_number_shows_an_error_and_continues(self):
        with mock.patch.object(main.in_and_out, "get_menu_choice", side_effect=[99, 0]), \
                mock.patch.object(main.in_and_out, "show_wrong_option_error") as shown, \
                mock.patch.object(main.in_and_out, "show_goodbye"):
            main.run_session("alice")
        shown.assert_called_once()


class LoginTests(TempDataDir):
    def test_account_can_be_created_and_logged_into(self):
        io = main.in_and_out
        with mock.patch.object(io, "retrieve_new_username", return_value="alice"), \
                mock.patch.object(io, "retrieve_new_password", return_value="password123"), \
                mock.patch.object(io, "show_account_created"):
            main.create_account_flow()
        with mock.patch.object(io, "retrieve_username", return_value="alice"), \
                mock.patch.object(io, "retrieve_password", return_value="password123"), \
                mock.patch.object(io, "show_login_success"):
            self.assertEqual(main.login_flow(), "alice")

    def test_wrong_password_fails(self):
        io = main.in_and_out
        dm.save_new_user(main.logic.build_new_user_record("alice", "password123"))
        with mock.patch.object(io, "retrieve_username", return_value="alice"), \
                mock.patch.object(io, "retrieve_password", return_value="nope-nope"), \
                mock.patch.object(io, "show_login_failed") as failed:
            self.assertIsNone(main.login_flow())
        failed.assert_called_once()

    def test_taken_usernames_are_asked_for_again(self):
        io = main.in_and_out
        dm.save_new_user({"username": "alice"})
        with mock.patch.object(io, "retrieve_new_username", side_effect=["alice", "bob"]), \
                mock.patch.object(io, "retrieve_new_password", return_value="password123"), \
                mock.patch.object(io, "show_username_taken") as taken, \
                mock.patch.object(io, "show_account_created") as created:
            main.create_account_flow()
        taken.assert_called_once_with("alice")
        created.assert_called_once_with("bob")

    def test_login_screen_exit_returns_none(self):
        with mock.patch.object(main.in_and_out, "get_auth_choice", side_effect=[0]), \
                mock.patch.object(main.in_and_out, "show_goodbye"):
            self.assertIsNone(main.login_screen())

    def test_login_screen_retries_until_success(self):
        with mock.patch.object(main.in_and_out, "get_auth_choice", side_effect=[1, 7, 1]), \
                mock.patch.object(main, "login_flow", side_effect=[None, "alice"]), \
                mock.patch.object(main.in_and_out, "show_wrong_option_error"):
            self.assertEqual(main.login_screen(), "alice")


class UpdateDeleteFlowTests(TempDataDir):
    def test_update_replaces_the_chosen_record(self):
        records = [rec("A"), rec("B")]
        with mock.patch.object(main.in_and_out, "select_record", return_value=2), \
                mock.patch.object(main.in_and_out, "retrieve_updated_record", return_value=rec("B2")), \
                mock.patch.object(main.in_and_out, "display_edit_result") as shown:
            records, name = main.update_record_flow(records, "", 5)
        self.assertEqual([r["Company Name"] for r in records], ["A", "B2"])
        shown.assert_called_once_with("updated", "B2")

    def test_update_does_nothing_when_no_record_chosen(self):
        records = [rec("A")]
        with mock.patch.object(main.in_and_out, "select_record", return_value=None):
            self.assertEqual(main.update_record_flow(records, "f.json", 5), (records, "f.json"))

    def test_delete_removes_the_record_only_after_confirmation(self):
        with mock.patch.object(main.in_and_out, "select_record", return_value=1), \
                mock.patch.object(main.in_and_out, "confirm_delete", return_value=False):
            records, _ = main.delete_record_flow([rec("A")], "", 6)
        self.assertEqual(len(records), 1)
        with mock.patch.object(main.in_and_out, "select_record", return_value=1), \
                mock.patch.object(main.in_and_out, "confirm_delete", return_value=True), \
                mock.patch.object(main.in_and_out, "display_edit_result") as shown:
            records, _ = main.delete_record_flow([rec("A")], "", 6)
        self.assertEqual(records, [])
        shown.assert_called_once_with("deleted", "A")


if __name__ == "__main__":
    unittest.main()
