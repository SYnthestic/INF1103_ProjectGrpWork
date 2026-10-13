"""Tests for the I/O Manager's pure helpers (validation and record
conversion). Screens and prompts are covered by the end-to-end check in
the README, since they need a real terminal."""

import contextlib
import io
from unittest import mock
import io_manager as io_mgr
from tests.helpers import raises


def key_verifier_check(text):
    with contextlib.redirect_stdout(io.StringIO()):
        return io_mgr.key_verifier(text)


def test_valid_numbers():
    assert key_verifier_check("7") == 7
    assert key_verifier_check(" 10 ") == 10


def test_rejects_everything_else():
    for text in ("", "  ", "a", "-1", "1.5", "123", "１", None, 5):
        assert key_verifier_check(text) is None


def test_valid():
    for name in ("abc", "tim_01", "a" * 20):
        assert io_mgr.is_valid_username(name)


def test_invalid():
    for name in ("ab", "a" * 21, "has space", "bad-name", "../x", "naïve", ""):
        assert not io_mgr.is_valid_username(name)


def test_numbers():
    assert io_mgr.finite_float("12.5") == 12.5


def test_nan_and_infinity_are_refused():
    for text in ("nan", "inf", "-inf", "x"):
        with raises(ValueError):
            io_mgr.finite_float(text)


RECORD_CONVERSION_NESTED = {
    "audit_id": 1,
    "company_profile": {
        "company_name": "Acme",
        "annual_revenue_sgd": 5.0,
        "group_employment_size": 3,
        "local_shareholding_pct": 80.0,
        "proposal_type": "ESG Reporting / Advisory",
        "reporting_advisory_fee_sgd": 1000.0,
    },
    "proposal": {"raw_narrative": "Our plan"},
}


def test_nested_record_becomes_the_display_layout():
    flat = io_mgr.flat_record(RECORD_CONVERSION_NESTED)
    assert flat["Company Name"] == "Acme"
    assert flat["Proposal Narrative"] == "Our plan"
    assert flat["Reporting Advisory Fee"] == 1000.0


def test_flat_record_is_left_alone():
    record = {"Company Name": "Beta"}
    assert io_mgr.flat_record(record) is record


def test_garbage_gives_an_empty_record():
    for value in (None, 5, "x", []):
        assert io_mgr.flat_record(value) == {}


def test_conversion_to_the_logic_profile():
    profile = io_mgr.convert_record_to_profile(
        {
            "Company Name": "Beta",
            "Company Total Revenue": 10.0,
            "Total Employees": 4,
            "Local Equity": 55.0,
            "Proposal Type": "Equipment / Energy Upgrade",
            "Baseline Energy Expenditure": 99.0,
        }
    )
    assert profile["annual_revenue_sgd"] == 10.0
    assert profile["baseline_annual_energy_expenditure_sgd"] == 99.0
    assert profile["estimated_retrofit_cost_sgd"] == 0.0


def test_missing_fields_do_not_crash():
    profile = io_mgr.convert_record_to_profile({})
    assert profile["annual_revenue_sgd"] == 0.0


def test_displaying_damaged_records_does_not_crash():
    with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(io_mgr.gui, "return_button"):
        io_mgr.display_applied_grants([{}, {"Company Name": None}, 5], 4)


RECORD_PICKER_RECORDS = [
    {"Company Name": "A", "Proposal Type": "Equipment / Energy Upgrade"},
    {"Company Name": "B", "Proposal Type": "ESG Reporting / Advisory"},
]


def record_picker_pick(function, answers, *args):
    with (
        contextlib.redirect_stdout(io.StringIO()),
        mock.patch("builtins.input", side_effect=answers),
    ):
        return function(*args)


def test_choosing_a_record():
    assert (
        record_picker_pick(io_mgr.select_record_index, ["2"], RECORD_PICKER_RECORDS, "update") == 1
    )


def test_zero_cancels():
    assert (
        record_picker_pick(io_mgr.select_record_index, ["0"], RECORD_PICKER_RECORDS, "delete")
        is None
    )


def test_bad_answers_are_asked_again():
    assert (
        record_picker_pick(
            io_mgr.select_record_index, ["x", "", "3", "-1", "1"], RECORD_PICKER_RECORDS, "update"
        )
        == 0
    )


def test_fields_depend_on_the_proposal_type():
    equipment = io_mgr.fields_for(RECORD_PICKER_RECORDS[0])
    reporting = io_mgr.fields_for(RECORD_PICKER_RECORDS[1])
    assert "Baseline Energy Expenditure" in equipment
    assert "Reporting Advisory Fee" not in equipment
    assert "Reporting Advisory Fee" in reporting
    assert "Estimated Retrofit Cost" not in reporting


def test_every_editable_field_has_a_prompt():
    import data_manager

    assert set(io_mgr.FIELD_PROMPTS) == set(data_manager.EDITABLE_RECORD_FIELDS)


def test_choosing_a_field():
    field = record_picker_pick(io_mgr.select_field_to_edit, ["1"], RECORD_PICKER_RECORDS[0])
    assert field == "Company Name"
    assert record_picker_pick(io_mgr.select_field_to_edit, ["0"], RECORD_PICKER_RECORDS[0]) is None


def test_existing_file_choices():
    for typed, expected in (("a", "add"), (" R ", "replace"), ("c", "cancel")):
        assert record_picker_pick(io_mgr.ask_existing_file_action, [typed], "f.json") == expected
    assert record_picker_pick(io_mgr.ask_existing_file_action, ["x", "", "a"], "f.json") == "add"


def test_delete_confirmation():
    assert record_picker_pick(io_mgr.confirm_delete_record, ["maybe", "y"], "A")
    assert not record_picker_pick(io_mgr.confirm_delete_record, ["n"], "A")
