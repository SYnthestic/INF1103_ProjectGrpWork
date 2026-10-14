"""Tests for the I/O Manager's pure helpers (validation and record
conversion). Screens and prompts are covered by the end-to-end check in
the README, since they need a real terminal."""

import contextlib
import io
from unittest import mock
import io_manager as io_mgr
from tests.helpers import raises
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

COST_PROMPTS = (
    io_mgr.retrieve_baseline_energy_expenditure,
    io_mgr.retrieve_estimated_retrofit_cost,
    io_mgr.retrieve_reporting_advisory_fee,
)


def test_only_the_io_manager_prints_or_asks_for_input():
    files = list(ROOT.glob("*.py")) + list((ROOT / "sme_interface_stores").glob("*.py"))
    offenders = []
    for path in files:
        if path.name == "io_manager.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("print", "input")
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


def test_revenue_rejects_bad_values_until_valid():
    answers = ["", "abc", "-5", "0", "nan", "inf", "1500.50"]
    assert run_with_answers(io_mgr.retrieve_total_revenue, answers) == 1500.5


def test_employees_must_be_a_positive_whole_number():
    answers = ["", "x", "1.5", "-3", "0", "12"]
    assert run_with_answers(io_mgr.retrieve_total_employees, answers) == 12


def test_equity_must_be_above_0_and_at_most_100():
    answers = ["", "x", "0", "-1", "100.5", "100"]
    assert run_with_answers(io_mgr.retrieve_local_equity, answers) == 100.0


def test_cost_fields_reject_bad_values_until_valid():
    for function in COST_PROMPTS:
        result = run_with_answers(function, ["", "x", "-1", "nan", "inf", "250.5"])
        assert result == 250.5, function.__name__


def test_baseline_energy_expenditure_rejects_zero():
    assert (
        run_with_answers(io_mgr.retrieve_baseline_energy_expenditure, ["0", "7"]) == 7.0
    )


def test_retrofit_cost_rejects_zero():
    assert run_with_answers(io_mgr.retrieve_estimated_retrofit_cost, ["0", "7"]) == 7.0


def test_reporting_fee_accepts_zero():
    assert run_with_answers(io_mgr.retrieve_reporting_advisory_fee, ["0", "7"]) == 0.0


def test_proposal_type_choices():
    answers = ["", "3", "x", "2"]
    assert (
        run_with_answers(io_mgr.retrieve_proposal_type, answers)
        == "ESG Reporting / Advisory"
    )


def test_industry_is_case_insensitive_and_rejects_unknown():
    assert (
        run_with_answers(io_mgr.retrieve_company_industry, ["", "nonsense", "retail"])
        == "Retail"
    )
    assert (
        run_with_answers(io_mgr.retrieve_company_industry, ["others", "mining"])
        == "Mining"
    )


def test_grant_menu_rejects_out_of_range_choices():
    answers = ["", "0", "6", "x", "1"]
    result = run_with_answers(io_mgr.retrieve_sustainability_grant, answers)
    assert isinstance(result, str) and result


def test_displays_do_not_crash_on_minimal_data():
    with contextlib.redirect_stdout(io.StringIO()):
        io_mgr.display_ai_audit({})
        io_mgr.display_save_result("something_new", "x.json")
        io_mgr.display_load_result("something_new", "x.json")
        io_mgr.display_grant_decision(
            {
                "is_sme": False,
                "decision_status": "REJECT_NON_SME",
                "audit_passed": False,
                "approved_subsidy_sgd": 0.0,
                "matched_schemes": [],
                "reasons": [],
                "recommendations": [],
            }
        )


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
    with (
        contextlib.redirect_stdout(io.StringIO()),
        mock.patch.object(io_mgr.gui, "return_button"),
    ):
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
        record_picker_pick(
            io_mgr.select_record_index, ["2"], RECORD_PICKER_RECORDS, "update"
        )
        == 1
    )


def test_zero_cancels():
    assert (
        record_picker_pick(
            io_mgr.select_record_index, ["0"], RECORD_PICKER_RECORDS, "delete"
        )
        is None
    )


def test_bad_answers_are_asked_again():
    assert (
        record_picker_pick(
            io_mgr.select_record_index,
            ["x", "", "3", "-1", "1"],
            RECORD_PICKER_RECORDS,
            "update",
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
    field = record_picker_pick(
        io_mgr.select_field_to_edit, ["1"], RECORD_PICKER_RECORDS[0]
    )
    assert field == "Company Name"
    assert (
        record_picker_pick(io_mgr.select_field_to_edit, ["0"], RECORD_PICKER_RECORDS[0])
        is None
    )


def test_existing_file_choices():
    for typed, expected in (("a", "add"), (" R ", "replace"), ("c", "cancel")):
        assert (
            record_picker_pick(io_mgr.ask_existing_file_action, [typed], "f.json")
            == expected
        )
    assert (
        record_picker_pick(io_mgr.ask_existing_file_action, ["x", "", "a"], "f.json")
        == "add"
    )


def test_delete_confirmation():
    assert record_picker_pick(io_mgr.confirm_delete_record, ["maybe", "y"], "A")
    assert not record_picker_pick(io_mgr.confirm_delete_record, ["n"], "A")


def run_with_answers(function, answers, *args):
    with (
        mock.patch("builtins.input", side_effect=answers),
        contextlib.redirect_stdout(io.StringIO()),
    ):
        return function(*args)


def test_history_action_choices():
    audits = [{"audit_id": 1}, {"audit_id": 5}]
    assert run_with_answers(io_mgr.choose_history_action, [""], audits) == (
        "back",
        None,
    )
    assert run_with_answers(io_mgr.choose_history_action, ["f"], audits) == (
        "filter",
        None,
    )
    assert run_with_answers(io_mgr.choose_history_action, ["#5"], audits) == ("open", 1)
    assert run_with_answers(io_mgr.choose_history_action, ["9", "x", "1"], audits) == (
        "open",
        0,
    )


def test_history_filter_choices():
    statuses = ["MANUAL_REVIEW", "REJECT_LOW_IMPACT"]
    assert run_with_answers(io_mgr.retrieve_history_filter, [""], statuses) is None
    assert run_with_answers(io_mgr.retrieve_history_filter, ["2"], statuses) == (
        "status",
        "REJECT_LOW_IMPACT",
    )
    assert run_with_answers(
        io_mgr.retrieve_history_filter, ["c", "apex"], statuses
    ) == (
        "company",
        "apex",
    )
    assert run_with_answers(io_mgr.retrieve_history_filter, ["9", "1"], statuses) == (
        "status",
        "MANUAL_REVIEW",
    )
    assert (
        run_with_answers(io_mgr.retrieve_history_filter, ["c", "", ""], statuses)
        is None
    )


def test_export_confirmation_only_accepts_y_or_n():
    assert run_with_answers(io_mgr.confirm_export_pdf, ["maybe", "Y"]) is True
    assert run_with_answers(io_mgr.confirm_export_pdf, ["n"]) is False


def test_pdf_result_messages_name_the_file_and_the_failures():
    def shown(status):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            io_mgr.show_pdf_result(status, "a.pdf", "/data/records/alice")
        return buffer.getvalue()

    assert "a.pdf" in shown("exported") and "/data/records/alice" in shown("exported")
    assert "reportlab" in shown("missing_dependency")
    assert "could not be created" in shown("pdf_error")
    assert "failed" in shown("something_new")


def test_company_name_and_narrative_have_length_limits():
    too_long_name = "x" * (io_mgr.COMPANY_NAME_MAX_LEN + 1)
    assert (
        run_with_answers(io_mgr.retrieve_company_name, [too_long_name, "  Apex  "])
        == "Apex"
    )
    too_long_text = "y" * (io_mgr.NARRATIVE_MAX_LEN + 1)
    assert run_with_answers(
        io_mgr.retrieve_proposal_narrative, [too_long_text, "EV vans"]
    ) == ("EV vans")


def test_other_industry_and_grant_have_length_limits():
    long_text = "a" * (io_mgr.OTHER_TEXT_MAX_LEN + 1)
    assert (
        run_with_answers(io_mgr.get_valid_other_industry, [long_text, "mining"])
        == "Mining"
    )
    assert run_with_answers(
        io_mgr.retrieve_sustainability_grant, ["5", long_text, "Green Fund"]
    ) == ("Green Fund")
