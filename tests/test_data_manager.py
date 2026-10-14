"""Tests for the Data Manager. Every test works in its own temporary
folder (DATA_DIR is redirected), so real data is never touched."""

import json
import os
import io_manager as logic
import data_manager as dm
from tests.helpers import temp_data_dir, raises
import pytest


def test_inspect_save_file_statuses():
    with temp_data_dir():
        dm.save_data_to_json([], "here")
        assert dm.inspect_save_file("here") == ("here.json", "exists")
        assert dm.inspect_save_file("absent") == ("absent.json", "not_found")
        assert dm.inspect_save_file("") == ("", "no_name")
        assert dm.inspect_save_file("a/b") == ("", "invalid_name")


def test_is_data_loaded():
    assert not dm.is_data_loaded([], "")
    assert dm.is_data_loaded([{"Company Name": "A"}], "")
    assert dm.is_data_loaded([], "mine.json")


def test_failed_save_keeps_the_old_file_and_leaves_no_temp_file():
    with temp_data_dir() as folder:
        dm.save_data_to_json([save_load_sample_record()], "mine")
        assert dm.save_data_to_json([object()], "mine") == (None, "io_error")
        assert dm.load_data_from_json("mine")[2] == "loaded"
        assert os.listdir(folder) == ["mine.json"]


def test_single_record_file_loads_as_a_one_item_list():
    with temp_data_dir() as folder:
        record = save_load_sample_record()
        with open(os.path.join(folder, "one.json"), "w") as file:
            json.dump(record, file)
        loaded, _, status = dm.load_data_from_json("one")
        assert status == "loaded" and loaded == [record]


def test_empty_list_and_empty_file():
    with temp_data_dir() as folder:
        dm.save_data_to_json([], "empty")
        assert dm.load_data_from_json("empty")[:3:2] == ([], "loaded")
        open(os.path.join(folder, "blank.json"), "w").close()
        assert dm.load_data_from_json("blank")[2] == "invalid_json"


def test_list_with_one_bad_record_is_refused_whole():
    with temp_data_dir() as folder:
        with open(os.path.join(folder, "mixed.json"), "w") as file:
            json.dump([save_load_sample_record(), {"junk": 1}], file)
        assert dm.load_data_from_json("mixed")[2] == "invalid_format"


def test_non_utf8_file_is_treated_as_corrupt():
    with temp_data_dir() as folder:
        with open(os.path.join(folder, "bytes.json"), "wb") as file:
            file.write(b"\xff\xfe\x00bad")
        assert dm.load_data_from_json("bytes")[2] == "invalid_json"


def test_unicode_survives_a_round_trip():
    with temp_data_dir():
        record = save_load_sample_record()
        record["company_profile"]["company_name"] = "Café 緑 ✓"
        dm.save_data_to_json([record], "uni")
        assert dm.load_data_from_json("uni")[0] == [record]


def test_audit_ids_actually_increase():
    records = []
    seen = []
    for _ in range(3):
        audit_id = dm.generate_audit_id(records)
        seen.append(audit_id)
        records.append(save_load_sample_record(audit_id))
    assert len(set(seen)) == 3
    assert seen == sorted(seen)


def test_record_validity_rules():
    assert dm.is_valid_audit_record(save_load_sample_record())
    assert dm.is_valid_audit_record({"Company Name": "A", "Proposal Narrative": "x"})
    for bad in (None, 5, "x", [], {}, {"Company Name": "A"}):
        assert not dm.is_valid_audit_record(bad)


def test_add_audit_record_recovers_from_a_bad_list():
    assert dm.add_audit_record(None, {"a": 1}) == [{"a": 1}]
    assert dm.add_audit_record([{"b": 2}], {"a": 1}) == [{"b": 2}, {"a": 1}]


def test_nested_record_converts_to_display_format():
    flat = logic.audit_record_to_display_format(save_load_sample_record())
    assert flat["Company Name"] == "Acme"
    assert flat["Reporting Advisory Fee"] == 0.0


def test_history_refuses_unsafe_usernames():
    with temp_data_dir() as folder:
        for bad in ("../x", "a/b", "", None, 5):
            try:
                result = dm.append_user_audit(bad, {}, {}, {})
            except ValueError:
                continue
            assert not result
        assert dm.get_user_audits("../x") == []
        assert not os.path.exists(os.path.join(os.path.dirname(folder), "x"))


def test_logging_out_clears_the_active_user():
    with temp_data_dir():
        dm.set_active_user("alice")
        dm.set_active_user(None)          # logout
        assert dm.get_active_user() is None


def test_delete_and_update_reject_odd_indexes():
    old = edit_and_delete_records()
    assert dm.delete_record(old, -1)[1] == "bad_index"
    assert dm.delete_record(old, True)[1] == "bad_index"
    assert dm.delete_record("nope", 0)[1] == "bad_index"


def test_every_editable_field_can_be_updated():
    for field in dm.EDITABLE_RECORD_FIELDS:
        new, status = dm.update_record_field([{"Company Name": "A"}], 0, field, "v")
        assert status == "updated", field
        assert new[0][field] == "v"


def test_filters_survive_damaged_records():
    junk = [None, 5, {}, {"evaluation": "x"}, {"company_profile": []}]
    assert dm.filter_by_decision_status(junk, "MANUAL_REVIEW") == []
    assert dm.filter_approved_records(junk) == []
    assert dm.find_records_by_company(junk, "a") == []
    assert dm.available_decision_statuses(junk) == []


def test_pdf_handles_markup_characters_and_unicode():
    with temp_data_dir():
        dm.set_active_user("alice")
        audit = history_audit(2, "R&D <Ltd> Café", "MANUAL_REVIEW")
        audit["application"]["Proposal Narrative"] = "Swap <b>old</b> & 'new' kit ✓"
        name, status = dm.export_audit_to_pdf(audit)
        if status == "missing_dependency":
            pytest.skip("reportlab is not installed")
        assert status == "exported"


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


def history_audit(audit_id, company, status):
    return {
        "audit_id": audit_id,
        "timestamp": "2026-10-13T10:00:00",
        "application": {
            "Company Name": company,
            "Company Industry": "Logistics",
            "Company Total Revenue": 8450000.0,
            "Total Employees": 38,
            "Local Equity": 85.0,
            "Proposal Type": "Equipment / Energy Upgrade",
            "Sustainability Grant": "EEG",
            "Proposal Narrative": "Replace 6 diesel vans.",
            "Baseline Energy Expenditure": 120000.0,
            "Estimated Retrofit Cost": 150000.0,
            "Reporting Advisory Fee": 0.0,
        },
        "ai_audit": {
            "scope_category": "Scope-1",
            "estimated_energy_reduction_pct": 25.0,
            "ai_reasoning_summary": "EV vans.",
            "ai_status": "ok",
        },
        "result": {
            "decision_status": status,
            "is_sme": True,
            "audit_passed": True,
            "approved_subsidy_sgd": 30000.0,
            "reasons": ["Meets SME criteria."],
            "recommendations": [],
            "matched_schemes": ["EEG"],
        },
    }


def test_audit_history_filters():
    audits = [
        history_audit(1, "Apex Haulage", "PRE_APPROVED_TIER_1"),
        history_audit(2, "Bolt Foods", "MANUAL_REVIEW"),
        {"audit_id": 3},
    ]
    assert dm.available_audit_statuses(audits) == ["MANUAL_REVIEW", "PRE_APPROVED_TIER_1"]
    assert dm.filter_audits_by_status(audits, "MANUAL_REVIEW") == [audits[1]]
    assert dm.search_audits_by_company(audits, " APEX ") == [audits[0]]
    assert dm.search_audits_by_company(audits, "nothing") == []


def test_history_entry_becomes_a_complete_report_record():
    audit = history_audit(4, "Apex", "PRE_APPROVED_TIER_1")
    record = dm.audit_to_report_record(audit)
    assert record["Company Name"] == "Apex"
    assert record["Grant Decision"]["decision_status"] == "PRE_APPROVED_TIER_1"
    assert record["AI Audit"]["scope_category"] == "Scope-1"
    assert record["Audit ID"] == 4
    assert dm.is_valid_audit_record(record)


def test_pdf_file_name_is_safe():
    audit = history_audit(7, 'A/B: "Co"', "MANUAL_REVIEW")
    name = dm.audit_pdf_filename(audit)
    assert name == "audit_7_A_B_ _Co_.pdf"
    assert dm.is_valid_filename(name)
    assert dm.audit_pdf_filename({"audit_id": 1}) == "audit_1_Company.pdf"


def test_export_audit_to_pdf_writes_a_pdf_with_the_decision():
    with temp_data_dir() as folder:
        dm.set_active_user("alice")
        name, status = dm.export_audit_to_pdf(history_audit(1, "Apex", "PRE_APPROVED_TIER_1"))
        if status == "missing_dependency":
            return  # reportlab is not installed on this machine
        assert status == "exported"
        path = os.path.join(folder, "records", "alice", name)
        with open(path, "rb") as file:
            assert file.read(5) == b"%PDF-"
        assert dm.get_records_folder() == os.path.abspath(os.path.dirname(path))


def test_export_of_nothing_fails_cleanly():
    with temp_data_dir():
        assert dm.export_audit_to_pdf({}) == (None, "pdf_error")
        assert dm.export_audit_to_pdf(None) == (None, "pdf_error")


def test_logging_goes_to_the_data_folder_and_is_set_up_once():
    import logging

    with temp_data_dir() as folder:
        assert dm.setup_logging() is True
        assert dm.setup_logging() is True
        root = logging.getLogger()
        handlers = [h for h in root.handlers if getattr(h, "baseFilename", "").startswith(folder)]
        try:
            assert len(handlers) == 1
            logging.getLogger("some.layer").error("something went wrong")
            handlers[0].flush()
            with open(os.path.join(folder, "app.log"), encoding="utf-8") as file:
                assert "something went wrong" in file.read()
        finally:
            for handler in handlers:
                root.removeHandler(handler)
                handler.close()


def test_logging_setup_fails_quietly_when_the_folder_cannot_be_used():
    with temp_data_dir() as folder:
        blocker = os.path.join(folder, "blocker")
        with open(blocker, "w", encoding="utf-8") as file:
            file.write("a file where a folder is needed")
        dm.DATA_DIR = os.path.join(blocker, "inside")
        assert dm.setup_logging() is False


# --- PDF report helpers (the pure-text parts, no ReportLab needed) ---

def test_pdf_name_defaults_to_the_source_name():
    assert dm._resolve_pdf_name("audits.json", None) == "audits.pdf"
    assert dm._resolve_pdf_name("audits.json", "report") == "report.pdf"


def test_pdf_name_rejects_unsafe_names():
    for bad in ("../x.pdf", "a/b.pdf", "bad*.pdf", "tab\t.pdf"):
        assert dm._resolve_pdf_name("audits.json", bad) is None


def test_outcome_wording_follows_the_decision_status():
    assert dm._outcome_for({"decision_status": "MANUAL_REVIEW"})[1] == "amber"
    assert dm._outcome_for({"decision_status": "REJECT_NON_SME"})[1] == "red"
    assert dm._outcome_for({"audit_passed": True})[1] == "teal"
    assert dm._outcome_for({})[1] == "amber"


def test_screening_result_for_unknown_status_goes_to_review():
    assert dm._screening_result_for({}) == "Not recorded"
    assert dm._screening_result_for({"decision_status": "ODD"}) == "Further review required"
    assert dm._screening_result_for({"decision_status": "X", "audit_passed": True}) == "Passed"


def test_report_values_are_written_as_prose():
    assert dm._readable_value(1234.5, "annual_revenue_sgd") == "SGD 1,234.50"
    assert dm._readable_value(True) == "Yes"
    assert dm._readable_value([], "x") == "None recorded"
    assert dm._readable_value("REJECT_NON_SME", "decision_status").startswith("Did not qualify")


def test_report_sections_handle_both_record_layouts():
    flat = {"Company Name": "Flat Co", "Audit ID": 7}
    profile, proposal, ai_audit, evaluation, record_id, _ = dm._report_sections(flat, 0)
    assert profile["company_name"] == "Flat Co" and record_id == 7
    assert ai_audit == {} and evaluation == {}
    assert dm._report_company_name([flat]) == "Flat Co"
    assert dm._report_company_name([]) == "the named company"
