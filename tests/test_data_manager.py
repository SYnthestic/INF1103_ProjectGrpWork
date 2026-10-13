"""Tests for the Data Manager. Every test works in its own temporary
folder (DATA_DIR is redirected), so real data is never touched."""

import json
import os
import data_manager as dm
from tests.helpers import temp_data_dir, raises


def test_extension_is_added_once():
    assert dm.normalise_filename("grants") == "grants.json"
    assert dm.normalise_filename(" grants.JSON ") == "grants.JSON"


def test_valid_and_invalid_names():
    assert dm.is_valid_filename("grants.json")
    for bad in ("a/b.json", "..\\x.json", ".json", " .json", "a\x00b.json", 'q"x.json'):
        assert not dm.is_valid_filename(bad)


def test_generated_company_filename_is_safe():
    name = dm.generate_company_save_filename("Acme / Pte. Ltd: <test>")
    assert dm.is_valid_filename(name)
    assert name.endswith(".json")


def save_load_sample_record(audit_id="AUD-0001"):
    profile = {"company_name": "Acme"}
    return dm.create_audit_record(
        audit_id,
        profile,
        {"proposal_type": "x"},
        {"scope_category": "Scope-1"},
        {"decision_status": "PRE_APPROVED_TIER_1"},
    )


def test_round_trip():
    with temp_data_dir():
        records = [save_load_sample_record()]
        assert dm.save_data_to_json(records, "mine") == ("mine.json", "saved")
        loaded, name, status = dm.load_data_from_json("mine")
        assert (name, status) == ("mine.json", "loaded")
        assert loaded == records


def test_no_temp_file_is_left_behind():
    with temp_data_dir() as folder:
        dm.save_data_to_json([], "mine")
        assert os.listdir(folder) == ["mine.json"]


def test_bad_names_are_refused():
    with temp_data_dir():
        assert dm.save_data_to_json([], "")[1] == "no_name"
        assert dm.save_data_to_json([], "../x")[1] == "invalid_name"


def test_missing_file_reports_not_found():
    with temp_data_dir():
        assert dm.load_data_from_json("nothing")[2] == "not_found"


def test_corrupt_file_is_set_aside():
    with temp_data_dir() as folder:
        path = os.path.join(folder, "broken.json")
        with open(path, "w") as file:
            file.write("{not json")
        assert dm.load_data_from_json("broken")[2] == "invalid_json"
        assert not os.path.exists(path)
        assert any((name.startswith("broken") and "corrupt" in name for name in os.listdir(folder)))


def test_valid_json_of_the_wrong_shape_is_refused():
    with temp_data_dir() as folder:
        path = os.path.join(folder, "wrong.json")
        with open(path, "w") as file:
            json.dump({"a": 1}, file)
        assert dm.load_data_from_json("wrong")[2] == "invalid_format"


def test_audit_ids_increase():
    with temp_data_dir():
        first = save_load_sample_record(dm.generate_audit_id([]))
        second_id = dm.generate_audit_id([first])
        assert first["audit_id"] != second_id


def test_merge_does_not_duplicate_ids():
    with temp_data_dir():
        existing = [save_load_sample_record("AUD-0001")]
        duplicate = dict(existing[0])
        fresh = save_load_sample_record("AUD-0002")
        merged = dm.merge_records(existing, [duplicate, fresh])
        assert merged == [existing[0], fresh]


def test_records_go_into_the_active_users_folder():
    with temp_data_dir() as folder:
        dm.set_active_user("alice")
        dm.save_data_to_json([], "mine")
        assert os.path.exists(os.path.join(folder, "records", "alice", "mine.json"))


def test_one_user_cannot_see_anothers_files():
    with temp_data_dir():
        dm.set_active_user("alice")
        dm.save_data_to_json([], "mine")
        dm.set_active_user("bob")
        assert dm.load_data_from_json("mine")[2] == "not_found"


def test_unsafe_usernames_are_refused():
    with temp_data_dir():
        for bad in ("..", "a/b", "Alice", "", "x" * 65, 5):
            with raises(ValueError):
                dm.set_active_user(bad)
        assert dm.get_active_user() is None


def test_new_user_is_stored_and_found():
    with temp_data_dir():
        assert not dm.user_exists("alice")
        assert dm.save_new_user({"username": "alice", "password_hash": "x"})
        assert dm.user_exists("alice")
        assert dm.get_user("alice")["username"] == "alice"
        assert "created_at" in dm.get_user("alice")


def test_duplicate_username_is_refused():
    with temp_data_dir():
        dm.save_new_user({"username": "alice"})
        assert not dm.save_new_user({"username": "alice"})


def test_unknown_user_is_none():
    with temp_data_dir():
        assert dm.get_user("nobody") is None


def test_damaged_users_file_is_kept_as_a_backup():
    with temp_data_dir() as folder:
        path = os.path.join(folder, "users.json")
        with open(path, "w") as file:
            file.write("{broken")
        assert dm.save_new_user({"username": "alice"})
        backups = [name for name in os.listdir(folder) if "corrupt" in name]
        assert len(backups) == 1
        with open(os.path.join(folder, backups[0])) as file:
            assert file.read() == "{broken"


def test_damaged_user_record_still_blocks_the_name():
    with temp_data_dir() as folder:
        with open(os.path.join(folder, "users.json"), "w") as file:
            json.dump({"alice": "garbage"}, file)
        assert dm.user_exists("alice")
        assert dm.get_user("alice") is None


def test_history_is_kept_per_user():
    with temp_data_dir():
        dm.append_user_audit(
            "alice", {"Company Name": "A"}, {"x": 1}, {"decision_status": "MANUAL_REVIEW"}
        )
        dm.append_user_audit(
            "alice", {"Company Name": "B"}, {"x": 1}, {"decision_status": "MANUAL_REVIEW"}
        )
        dm.append_user_audit(
            "bob", {"Company Name": "C"}, {"x": 1}, {"decision_status": "MANUAL_REVIEW"}
        )
        assert [a["application"]["Company Name"] for a in dm.get_user_audits("alice")] == ["A", "B"]
        assert len(dm.get_user_audits("bob")) == 1
        assert dm.get_user_audits("nobody") == []


def test_audit_ids_are_unique():
    with temp_data_dir():
        for _ in range(3):
            dm.append_user_audit("alice", {}, {}, {})
        ids = [audit["audit_id"] for audit in dm.get_user_audits("alice")]
        assert len(ids) == len(set(ids))


def test_damaged_history_entries_are_skipped():
    with temp_data_dir() as folder:
        with open(os.path.join(folder, "audit_history.json"), "w") as file:
            json.dump({"alice": [1, "x", {"audit_id": "A1"}]}, file)
        assert dm.get_user_audits("alice") == [{"audit_id": "A1"}]


def test_damaged_history_is_kept_as_a_backup():
    with temp_data_dir() as folder:
        path = os.path.join(folder, "audit_history.json")
        with open(path, "w") as file:
            file.write("{broken")
        assert dm.append_user_audit("alice", {}, {}, {}) is not None
        assert len(dm.get_user_audits("alice")) == 1
        assert any(("corrupt" in name for name in os.listdir(folder)))


def test_lock_file_is_removed_afterwards():
    with temp_data_dir() as folder:
        with dm._file_lock("users.json") as locked:
            assert locked
        assert not any((name.endswith(".lock") for name in os.listdir(folder)))


def edit_and_delete_records():
    return [{"Company Name": "A", "Local Equity": 50.0}, {"Company Name": "B"}]


def test_update_returns_a_new_list_and_leaves_the_old_one():
    old = edit_and_delete_records()
    new, status = dm.update_record_field(old, 0, "Local Equity", 80.0)
    assert status == "updated"
    assert new[0]["Local Equity"] == 80.0
    assert old[0]["Local Equity"] == 50.0
    assert new[1] == old[1]


def test_update_rejects_bad_input():
    old = edit_and_delete_records()
    assert dm.update_record_field(old, 5, "Company Name", "x") == (old, "bad_index")
    assert dm.update_record_field(old, -1, "Company Name", "x") == (old, "bad_index")
    assert dm.update_record_field(old, True, "Company Name", "x")[1] == "bad_index"
    assert dm.update_record_field(old, 0, "Proposal Type", "x")[1] == "bad_field"
    assert (
        dm.update_record_field([{"company_profile": {}}], 0, "Company Name", "x")[1]
        == "not_editable"
    )
    assert dm.update_record_field("nope", 0, "Company Name", "x")[1] == "bad_index"


def test_delete_removes_one_record():
    old = edit_and_delete_records()
    new, status = dm.delete_record(old, 0)
    assert (status, [r["Company Name"] for r in new]) == ("deleted", ["B"])
    assert len(old) == 2


def test_delete_rejects_a_bad_index():
    old = edit_and_delete_records()
    assert dm.delete_record(old, 2) == (old, "bad_index")
    assert dm.delete_record([], 0)[1] == "bad_index"


def filter_records():

    def record(audit_id, company, status):
        return {
            "audit_id": audit_id,
            "company_profile": {"company_name": company},
            "proposal": {},
            "ai_audit": {},
            "evaluation": {
                "decision_status": status,
                "audit_passed": status.startswith("PRE_APPROVED"),
            },
        }

    return [
        record("1", "Acme Pte Ltd", "PRE_APPROVED_TIER_1"),
        record("2", "Beta Co", "REJECT_NON_SME"),
        record("3", "acme holdings", "MANUAL_REVIEW"),
    ]


def test_filter_by_status():
    assert [
        r["audit_id"] for r in dm.filter_by_decision_status(filter_records(), "REJECT_NON_SME")
    ] == ["2"]


def test_approved_records():
    assert [r["audit_id"] for r in dm.filter_approved_records(filter_records())] == ["1"]


def test_company_search_is_an_exact_case_insensitive_match():
    found = dm.find_records_by_company(filter_records(), "  acme pte ltd ")
    assert [r["audit_id"] for r in found] == ["1"]
    assert dm.find_records_by_company(filter_records(), "acme") == []


def test_available_statuses():
    assert sorted(dm.available_decision_statuses(filter_records())) == [
        "MANUAL_REVIEW",
        "PRE_APPROVED_TIER_1",
        "REJECT_NON_SME",
    ]
