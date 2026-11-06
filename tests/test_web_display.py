"""The web pages show grant decisions in a readable way: a plain-English
heading coloured by outcome, the subsidy, reasons and recommendations as
lists, and the AI audit and thresholds as labelled tables."""

import pytest

from web import display

USER = {"username": "tester", "password": "Test1234!"}
RECORD = {
    "Company Name": "Apex <Logistics>",
    "Company Industry": "Logistics",
    "Company Total Revenue": "8450000",
    "Total Employees": "38",
    "Local Equity": "85",
    "Proposal Type": "Equipment / Energy Upgrade",
    "Sustainability Grant": "1. Energy Efficiency Grant (EEG) -Base Tier",
    "Proposal Narrative": "Electric vans",
    "Baseline Energy Expenditure": "120000",
    "Estimated Retrofit Cost": "150000",
}
DECISION = {
    "is_sme": True,
    "decision_status": "PRE_APPROVED_TIER_1",
    "reasons": ["Proposal targets Scope-1 emissions.", "Meets <the> 20% threshold."],
    "recommendations": ["Keep receipts."],
    "matched_schemes": ["Energy Efficiency Grant (EEG) - Base Tier"],
    "approved_subsidy_sgd": 30000.0,
    "audit_passed": True,
}
AI_AUDIT = {
    "scope_category": "Scope-1",
    "primary_intervention_type": "Commercial Fleet Electrification",
    "estimated_energy_reduction_pct": 28.0,
    "estimated_lifetime_abatement_tonnes": 0.0,
    "detected_exclusion_keywords": [],
    "ai_reasoning_summary": "Diesel to electric.",
    "ai_status": "ok",
}


@pytest.fixture
def audited(app, client):
    """Logged in, with one audit whose decision is DECISION."""
    app.extensions["ai"].get_ai_response = lambda narrative, progress=None: dict(AI_AUDIT)
    app.extensions["logic"].evaluate_grant_application = lambda profile, ai: dict(DECISION)
    client.post("/register", data=USER)
    client.post("/login", data=USER)
    client.post("/new", data=RECORD)
    return client


# ---- Helpers in web/display.py ------------------------------------------------


@pytest.mark.parametrize(
    "status, label, tone",
    [
        ("PRE_APPROVED_TIER_1", "Pre-approved: EEG Base Tier", "approved"),
        ("PROVISIONAL_APPROVAL_TIER_2", "Provisionally approved: ESP", "approved"),
        ("MANUAL_REVIEW", "Needs manual review", "review"),
        ("MANUAL_EXCLUSION_REVIEW", "Exclusion review needed", "review"),
        ("REJECT_NON_SME", "Rejected: not an SME", "rejected"),
        ("REJECT_LOW_IMPACT", "Rejected: energy reduction too low", "rejected"),
        ("SOMETHING_NEW", "SOMETHING_NEW", "neutral"),
        (None, "No decision", "neutral"),
    ],
)
def test_every_decision_has_a_heading_and_a_tone(status, label, tone):
    assert display.decision_label(status) == label
    assert display.decision_tone(status) == tone


def test_money_and_numbers_are_formatted():
    assert display.money(30000) == "SGD 30,000.00"
    assert display.money(None) == "-" and display.money(True) == "-"
    assert display.number(28.0, "%") == "28%"
    assert display.number(12.5, "%") == "12.5%"
    assert display.number(350.0, "tonnes") == "350 tonnes"


def test_ai_rows_are_labelled_in_a_fixed_order_and_keep_extra_fields():
    rows = display.ai_rows(dict(AI_AUDIT, model_note="extra"))
    labels = [label for label, _ in rows]
    assert labels[:3] == ["GHG scope", "Intervention", "Estimated energy reduction"]
    assert ("Exclusion keywords", "None") in rows
    assert ("Model note", "extra") in rows
    assert "ai_status" not in str(rows)
    assert display.ai_rows(None) == [] and display.ai_rows("x") == []


def test_threshold_rows_use_the_admin_labels():
    rows = display.threshold_rows({"provisional_min_pct": 12.0, "eeg_advanced_min_tonnes": 350.0})
    assert ("Provisional approval (ESP) from", "12%") in rows
    assert ("EEG Advanced Tier: lifetime abatement above", "350 tonnes") in rows
    assert display.threshold_rows(None) == []


# ---- The pages ----------------------------------------------------------------


def test_the_audit_page_shows_a_readable_decision(audited):
    page = audited.get("/history/1").data
    assert b"Pre-approved: EEG Base Tier" in page
    assert b"tone-approved" in page
    assert b"SGD 30,000.00" in page
    assert b"<li>Proposal targets Scope-1 emissions.</li>" in page
    assert b"<li>Keep receipts.</li>" in page
    assert b"Commercial Fleet Electrification" in page and b"28%" in page
    assert b"SGD 8,450,000.00" in page


def test_the_audit_page_shows_the_thresholds_used(audited):
    page = audited.get("/history/1").data
    assert b"Thresholds used for this decision" in page
    assert b"Scope-1 fast track (EEG Base Tier) from" in page


def test_text_from_the_record_and_the_rules_is_escaped(audited):
    page = audited.get("/history/1").data
    assert b"Apex <Logistics>" not in page and b"Apex &lt;Logistics&gt;" in page
    assert b"Meets <the>" not in page


def test_the_history_list_shows_a_coloured_decision_and_the_subsidy(audited):
    page = audited.get("/history").data
    assert b'badge tone-approved' in page
    assert b"Pre-approved: EEG Base Tier" in page and b"SGD 30,000.00" in page


def test_run_logic_shows_the_decision_panel_and_run_ai_shows_a_table(audited):
    logic_page = audited.post("/records/logic").data
    assert b"Grant decision" in logic_page and b"tone-approved" in logic_page
    ai_page = audited.post("/records/ai").data
    assert b"AI audit" in ai_page and b"GHG scope" in ai_page


def test_the_register_page_explains_the_rules(client):
    page = client.get("/register").data
    assert b"3-20 letters, digits or _" in page
    assert b"8-64 characters" in page
