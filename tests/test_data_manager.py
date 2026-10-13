"""Tests for the Data Manager. Every test works in its own temporary
folder (DATA_DIR is redirected), so real data is never touched."""

import json
import os
import tempfile
import unittest

import data_manager as dm


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


class FilenameTests(unittest.TestCase):
    def test_extension_is_added_once(self):
        self.assertEqual(dm.normalise_filename("grants"), "grants.json")
        self.assertEqual(dm.normalise_filename(" grants.JSON "), "grants.JSON")

    def test_valid_and_invalid_names(self):
        self.assertTrue(dm.is_valid_filename("grants.json"))
        for bad in ("a/b.json", "..\\x.json", ".json", " .json", "a\x00b.json", 'q"x.json'):
            self.assertFalse(dm.is_valid_filename(bad), bad)

    def test_generated_company_filename_is_safe(self):
        name = dm.generate_company_save_filename("Acme / Pte. Ltd: <test>")
        self.assertTrue(dm.is_valid_filename(name))
        self.assertTrue(name.endswith(".json"))


class SaveLoadTests(TempDataDir):
    def sample_record(self, audit_id="AUD-0001"):
        profile = {"company_name": "Acme"}
        return dm.create_audit_record(audit_id, profile, {"proposal_type": "x"}, {"scope_category": "Scope-1"},
                                      {"decision_status": "PRE_APPROVED_TIER_1"})

    def test_round_trip(self):
        records = [self.sample_record()]
        self.assertEqual(dm.save_data_to_json(records, "mine"), ("mine.json", "saved"))
        loaded, name, status = dm.load_data_from_json("mine")
        self.assertEqual((name, status), ("mine.json", "loaded"))
        self.assertEqual(loaded, records)

    def test_no_temp_file_is_left_behind(self):
        dm.save_data_to_json([], "mine")
        self.assertEqual(os.listdir(self._tmp.name), ["mine.json"])

    def test_bad_names_are_refused(self):
        self.assertEqual(dm.save_data_to_json([], "")[1], "no_name")
        self.assertEqual(dm.save_data_to_json([], "../x")[1], "invalid_name")

    def test_missing_file_reports_not_found(self):
        self.assertEqual(dm.load_data_from_json("nothing")[2], "not_found")

    def test_corrupt_file_is_set_aside(self):
        path = os.path.join(self._tmp.name, "broken.json")
        with open(path, "w") as file:
            file.write("{not json")
        self.assertEqual(dm.load_data_from_json("broken")[2], "invalid_json")
        self.assertFalse(os.path.exists(path))
        self.assertTrue(any(name.startswith("broken") and "corrupt" in name for name in os.listdir(self._tmp.name)))

    def test_valid_json_of_the_wrong_shape_is_refused(self):
        path = os.path.join(self._tmp.name, "wrong.json")
        with open(path, "w") as file:
            json.dump({"a": 1}, file)
        self.assertEqual(dm.load_data_from_json("wrong")[2], "invalid_format")

    def test_audit_ids_increase(self):
        first = self.sample_record(dm.generate_audit_id([]))
        second_id = dm.generate_audit_id([first])
        self.assertNotEqual(first["audit_id"], second_id)

    def test_merge_does_not_duplicate_ids(self):
        existing = [self.sample_record("AUD-0001")]
        duplicate = dict(existing[0])
        fresh = self.sample_record("AUD-0002")
        merged = dm.merge_records(existing, [duplicate, fresh])
        self.assertEqual(merged, [existing[0], fresh])


class PerUserFolderTests(TempDataDir):
    def test_records_go_into_the_active_users_folder(self):
        dm.set_active_user("alice")
        dm.save_data_to_json([], "mine")
        self.assertTrue(os.path.exists(os.path.join(self._tmp.name, "records", "alice", "mine.json")))

    def test_one_user_cannot_see_anothers_files(self):
        dm.set_active_user("alice")
        dm.save_data_to_json([], "mine")
        dm.set_active_user("bob")
        self.assertEqual(dm.load_data_from_json("mine")[2], "not_found")

    def test_unsafe_usernames_are_refused(self):
        for bad in ("..", "a/b", "Alice", "", "x" * 65, 5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                dm.set_active_user(bad)
        self.assertIsNone(dm.get_active_user())


class UserAccountTests(TempDataDir):
    def test_new_user_is_stored_and_found(self):
        self.assertFalse(dm.user_exists("alice"))
        self.assertTrue(dm.save_new_user({"username": "alice", "password_hash": "x"}))
        self.assertTrue(dm.user_exists("alice"))
        self.assertEqual(dm.get_user("alice")["username"], "alice")
        self.assertIn("created_at", dm.get_user("alice"))

    def test_duplicate_username_is_refused(self):
        dm.save_new_user({"username": "alice"})
        self.assertFalse(dm.save_new_user({"username": "alice"}))

    def test_unknown_user_is_none(self):
        self.assertIsNone(dm.get_user("nobody"))

    def test_damaged_users_file_is_kept_as_a_backup(self):
        path = os.path.join(self._tmp.name, "users.json")
        with open(path, "w") as file:
            file.write("{broken")
        self.assertTrue(dm.save_new_user({"username": "alice"}))
        backups = [name for name in os.listdir(self._tmp.name) if "corrupt" in name]
        self.assertEqual(len(backups), 1)
        with open(os.path.join(self._tmp.name, backups[0])) as file:
            self.assertEqual(file.read(), "{broken")

    def test_damaged_user_record_still_blocks_the_name(self):
        with open(os.path.join(self._tmp.name, "users.json"), "w") as file:
            json.dump({"alice": "garbage"}, file)
        self.assertTrue(dm.user_exists("alice"))
        self.assertIsNone(dm.get_user("alice"))


class AuditHistoryTests(TempDataDir):
    def test_history_is_kept_per_user(self):
        dm.append_user_audit("alice", {"Company Name": "A"}, {"x": 1}, {"decision_status": "MANUAL_REVIEW"})
        dm.append_user_audit("alice", {"Company Name": "B"}, {"x": 1}, {"decision_status": "MANUAL_REVIEW"})
        dm.append_user_audit("bob", {"Company Name": "C"}, {"x": 1}, {"decision_status": "MANUAL_REVIEW"})
        self.assertEqual([a["application"]["Company Name"] for a in dm.get_user_audits("alice")], ["A", "B"])
        self.assertEqual(len(dm.get_user_audits("bob")), 1)
        self.assertEqual(dm.get_user_audits("nobody"), [])

    def test_audit_ids_are_unique(self):
        for _ in range(3):
            dm.append_user_audit("alice", {}, {}, {})
        ids = [audit["audit_id"] for audit in dm.get_user_audits("alice")]
        self.assertEqual(len(ids), len(set(ids)))

    def test_damaged_history_entries_are_skipped(self):
        with open(os.path.join(self._tmp.name, "audit_history.json"), "w") as file:
            json.dump({"alice": [1, "x", {"audit_id": "A1"}]}, file)
        self.assertEqual(dm.get_user_audits("alice"), [{"audit_id": "A1"}])

    def test_damaged_history_is_kept_as_a_backup(self):
        path = os.path.join(self._tmp.name, "audit_history.json")
        with open(path, "w") as file:
            file.write("{broken")
        self.assertIsNotNone(dm.append_user_audit("alice", {}, {}, {}))
        self.assertEqual(len(dm.get_user_audits("alice")), 1)
        self.assertTrue(any("corrupt" in name for name in os.listdir(self._tmp.name)))


class LockTests(TempDataDir):
    def test_lock_file_is_removed_afterwards(self):
        with dm._file_lock("users.json") as locked:
            self.assertTrue(locked)
        self.assertFalse(any(name.endswith(".lock") for name in os.listdir(self._tmp.name)))


class FilterTests(unittest.TestCase):
    def records(self):
        def record(audit_id, company, status):
            return {"audit_id": audit_id,
                    "company_profile": {"company_name": company},
                    "proposal": {}, "ai_audit": {},
                    "evaluation": {"decision_status": status,
                                   "audit_passed": status.startswith("PRE_APPROVED")}}
        return [record("1", "Acme Pte Ltd", "PRE_APPROVED_TIER_1"),
                record("2", "Beta Co", "REJECT_NON_SME"),
                record("3", "acme holdings", "MANUAL_REVIEW")]

    def test_filter_by_status(self):
        self.assertEqual([r["audit_id"] for r in dm.filter_by_decision_status(self.records(), "REJECT_NON_SME")], ["2"])

    def test_approved_records(self):
        self.assertEqual([r["audit_id"] for r in dm.filter_approved_records(self.records())], ["1"])

    def test_company_search_is_an_exact_case_insensitive_match(self):
        found = dm.find_records_by_company(self.records(), "  acme pte ltd ")
        self.assertEqual([r["audit_id"] for r in found], ["1"])
        self.assertEqual(dm.find_records_by_company(self.records(), "acme"), [])

    def test_available_statuses(self):
        self.assertEqual(sorted(dm.available_decision_statuses(self.records())),
                         ["MANUAL_REVIEW", "PRE_APPROVED_TIER_1", "REJECT_NON_SME"])


if __name__ == "__main__":
    unittest.main()
