"""Logic Manager tests driven by hardcoded sample AI responses.

Each sample below is the raw JSON text an AI model would send back for one
kind of proposal. The tests parse it with json.loads and feed it to
logic_manager exactly as the real pipeline would, so the Logic Manager's
decisions can be checked without any API key, network or AI Manager.

Run from the project folder, any of:
    python tests/test_logic_sample_ai_responses.py
    python tests/run_tests.py
    docker run --rm sme-grant-auditor python tests/test_logic_sample_ai_responses.py

Plain functions and asserts only (no classes). Every evaluation runs inside
a guard that raises if anything tries to open a network connection.
"""

import json
import os
import socket
import subprocess
import sys
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import logic_manager as logic  # noqa: E402


# ========================================================
# Hardcoded sample AI responses (raw JSON text)
# ========================================================
SAMPLE_FLEET_ELECTRIFICATION = """{
  "scope_category": "Scope-1",
  "primary_intervention_type": "Commercial Fleet Electrification",
  "estimated_energy_reduction_pct": 25.0,
  "estimated_lifetime_abatement_tonnes": 0.0,
  "detected_exclusion_keywords": [],
  "implementation_bottleneck": "Charging infrastructure lead time",
  "ai_reasoning_summary": "Replaces diesel vans with electric vans.",
  "ai_status": "ok"
}"""

SAMPLE_MODERATE_SCOPE1 = """{
  "scope_category": "Scope-1",
  "primary_intervention_type": "Boiler Efficiency Upgrade",
  "estimated_energy_reduction_pct": 17.0,
  "estimated_lifetime_abatement_tonnes": 0.0,
  "detected_exclusion_keywords": ["None"],
  "implementation_bottleneck": "",
  "ai_reasoning_summary": "Modest efficiency gain.",
  "ai_status": "ok"
}"""

SAMPLE_SCOPE2_CHILLER = """{
  "scope_category": "Scope-2",
  "primary_intervention_type": "Smart HVAC / Chiller Optimization",
  "estimated_energy_reduction_pct": 20.0,
  "estimated_lifetime_abatement_tonnes": 0.0,
  "detected_exclusion_keywords": [],
  "implementation_bottleneck": "",
  "ai_reasoning_summary": "Optimises chiller plant controls.",
  "ai_status": "ok"
}"""

SAMPLE_BORDERLINE_IMPACT = """{
  "scope_category": "Scope-1",
  "primary_intervention_type": "LED Lighting Retrofit",
  "estimated_energy_reduction_pct": 12.0,
  "estimated_lifetime_abatement_tonnes": 0.0,
  "detected_exclusion_keywords": [],
  "implementation_bottleneck": "",
  "ai_reasoning_summary": "Small saving.",
  "ai_status": "ok"
}"""

SAMPLE_LOW_IMPACT = """{
  "scope_category": "Scope-2",
  "primary_intervention_type": "Office Lighting",
  "estimated_energy_reduction_pct": 4.5,
  "estimated_lifetime_abatement_tonnes": 0.0,
  "detected_exclusion_keywords": [],
  "implementation_bottleneck": "",
  "ai_reasoning_summary": "Negligible saving.",
  "ai_status": "ok"
}"""

SAMPLE_LARGE_ABATEMENT = """{
  "scope_category": "Scope-1",
  "primary_intervention_type": "Process Heat Electrification",
  "estimated_energy_reduction_pct": 12.0,
  "estimated_lifetime_abatement_tonnes": 400.0,
  "detected_exclusion_keywords": [],
  "implementation_bottleneck": "",
  "ai_reasoning_summary": "Narrative states 400 tonnes CO2e abated over lifetime.",
  "ai_status": "ok"
}"""

SAMPLE_EXCLUDED_ITEM = """{
  "scope_category": "Scope-1",
  "primary_intervention_type": "Equipment Purchase",
  "estimated_energy_reduction_pct": 30.0,
  "estimated_lifetime_abatement_tonnes": 0.0,
  "detected_exclusion_keywords": ["second-hand"],
  "implementation_bottleneck": "",
  "ai_reasoning_summary": "Proposal buys second-hand machinery.",
  "ai_status": "ok"
}"""

SAMPLE_FOSSIL_FUEL_MODIFICATION = """{
  "scope_category": "Scope-1",
  "primary_intervention_type": "Fossil Fuel Modification",
  "estimated_energy_reduction_pct": 30.0,
  "estimated_lifetime_abatement_tonnes": 0.0,
  "detected_exclusion_keywords": [],
  "implementation_bottleneck": "",
  "ai_reasoning_summary": "Converts a gas burner to a different fossil fuel.",
  "ai_status": "ok"
}"""

SAMPLE_UNKNOWN_SCOPE = """{
  "scope_category": "Unknown",
  "primary_intervention_type": "Unclear",
  "estimated_energy_reduction_pct": 0.0,
  "estimated_lifetime_abatement_tonnes": 0.0,
  "detected_exclusion_keywords": [],
  "implementation_bottleneck": "Narrative too vague to classify",
  "ai_reasoning_summary": "Could not classify.",
  "ai_status": "ok"
}"""

SAMPLE_REPORTING_ONLY = """{
  "scope_category": "Unknown",
  "primary_intervention_type": "ESG Reporting",
  "estimated_energy_reduction_pct": 0.0,
  "estimated_lifetime_abatement_tonnes": 0.0,
  "detected_exclusion_keywords": [],
  "implementation_bottleneck": "",
  "ai_reasoning_summary": "Consultancy for sustainability reporting.",
  "ai_status": "ok"
}"""

# What the AI Manager hands over when the API call fails or the answer is junk.
SAMPLE_FAILED_CALL = """{
  "scope_category": "Unknown",
  "primary_intervention_type": "Unknown",
  "estimated_energy_reduction_pct": 0.0,
  "estimated_lifetime_abatement_tonnes": 0.0,
  "detected_exclusion_keywords": [],
  "implementation_bottleneck": "",
  "ai_reasoning_summary": "",
  "ai_status": "failed"
}"""

# A model that sends the wrong types and drops fields.
SAMPLE_SLOPPY_TYPES = """{
  "scope_category": 1,
  "estimated_energy_reduction_pct": "twenty",
  "estimated_lifetime_abatement_tonnes": null,
  "detected_exclusion_keywords": "second-hand"
}"""

COMPLETE_RESULT_KEYS = {
    "is_sme", "decision_status", "reasons", "recommendations",
    "matched_schemes", "approved_subsidy_sgd", "audit_passed",
}


# ========================================================
# Helpers
# ========================================================
def sme_profile(**changes):
    """A valid SME equipment proposal with SGD 100,000 baseline energy spend."""
    profile = {
        "annual_revenue_sgd": 5000000.0,
        "group_employment_size": 50,
        "local_shareholding_pct": 100.0,
        "proposal_type": "Equipment / Energy Upgrade",
        "sustainability_grant": "1. Energy Efficiency Grant (EEG) - Base Tier",
        "baseline_annual_energy_expenditure_sgd": 100000.0,
        "estimated_retrofit_cost_sgd": 0.0,
        "reporting_advisory_fee_sgd": 0.0,
    }
    profile.update(changes)
    return profile


def reporting_profile(fee):
    return sme_profile(
        proposal_type="ESG Reporting / Advisory",
        sustainability_grant="3. Sustainability Reporting Grant",
        baseline_annual_energy_expenditure_sgd=0.0,
        reporting_advisory_fee_sgd=fee,
    )


@contextmanager
def network_blocked():
    """Any attempt to open a socket inside this block fails the test."""
    def refuse(*args, **kwargs):
        raise AssertionError("the Logic Manager tried to use the network")

    saved = (socket.socket.connect, socket.create_connection)
    socket.socket.connect = refuse
    socket.create_connection = refuse
    try:
        yield
    finally:
        socket.socket.connect, socket.create_connection = saved


def evaluate(raw_ai_json, profile=None):
    """Parse a sample AI response and run the Logic Manager on it, offline."""
    ai_audit = json.loads(raw_ai_json)
    with network_blocked():
        return logic.evaluate_grant_application(
            profile if profile is not None else sme_profile(), ai_audit
        )


# ========================================================
# Tests
# ========================================================
def test_every_sample_is_valid_json():
    samples = [value for name, value in globals().items() if name.startswith("SAMPLE_")]
    assert len(samples) >= 12
    for sample in samples:
        assert isinstance(json.loads(sample), dict)


def test_clear_scope1_proposal_is_pre_approved():
    result = evaluate(SAMPLE_FLEET_ELECTRIFICATION)
    assert result["decision_status"] == "PRE_APPROVED_TIER_1"
    assert result["approved_subsidy_sgd"] == 30000.0
    assert result["audit_passed"] is True
    assert result["is_sme"] is True


def test_moderate_scope1_proposal_is_provisional():
    result = evaluate(SAMPLE_MODERATE_SCOPE1)
    assert result["decision_status"] == "PROVISIONAL_APPROVAL_TIER_2"
    assert result["approved_subsidy_sgd"] == 20000.0


def test_scope2_proposal_is_provisional_not_fast_tracked():
    result = evaluate(SAMPLE_SCOPE2_CHILLER)
    assert result["decision_status"] == "PROVISIONAL_APPROVAL_TIER_2"


def test_borderline_impact_goes_to_manual_review():
    result = evaluate(SAMPLE_BORDERLINE_IMPACT)
    assert result["decision_status"] == "MANUAL_REVIEW"
    assert result["audit_passed"] is False


def test_low_impact_is_rejected_with_no_subsidy():
    result = evaluate(SAMPLE_LOW_IMPACT)
    assert result["decision_status"] == "REJECT_LOW_IMPACT"
    assert result["approved_subsidy_sgd"] == 0.0
    assert result["reasons"] and result["recommendations"]


def test_large_abatement_reaches_the_advanced_tier():
    profile = sme_profile(baseline_annual_energy_expenditure_sgd=1000000.0)
    result = evaluate(SAMPLE_LARGE_ABATEMENT, profile)
    assert result["decision_status"] == "PRE_APPROVED_TIER_1_ADVANCED"
    assert result["approved_subsidy_sgd"] == 350000.0


def test_excluded_item_goes_to_exclusion_review():
    result = evaluate(SAMPLE_EXCLUDED_ITEM)
    assert result["decision_status"] == "MANUAL_EXCLUSION_REVIEW"
    assert result["audit_passed"] is False
    assert any("second-hand" in reason for reason in result["reasons"])


def test_fossil_fuel_modification_goes_to_exclusion_review():
    result = evaluate(SAMPLE_FOSSIL_FUEL_MODIFICATION)
    assert result["decision_status"] == "MANUAL_EXCLUSION_REVIEW"


def test_none_placeholder_keyword_is_not_an_exclusion():
    # SAMPLE_MODERATE_SCOPE1 lists "None" as its only keyword.
    assert evaluate(SAMPLE_MODERATE_SCOPE1)["decision_status"] != "MANUAL_EXCLUSION_REVIEW"


def test_unclassifiable_proposal_goes_to_manual_review():
    result = evaluate(SAMPLE_UNKNOWN_SCOPE)
    assert result["decision_status"] == "MANUAL_REVIEW"


def test_a_failed_ai_call_never_approves_anything():
    result = evaluate(SAMPLE_FAILED_CALL)
    assert result["decision_status"] in ("MANUAL_REVIEW", "REJECT_LOW_IMPACT")
    assert result["approved_subsidy_sgd"] == 0.0
    assert result["audit_passed"] is False


def test_non_sme_is_rejected_even_with_a_perfect_ai_answer():
    result = evaluate(SAMPLE_FLEET_ELECTRIFICATION, sme_profile(annual_revenue_sgd=250000000.0))
    assert result["decision_status"] == "REJECT_NON_SME"
    assert result["is_sme"] is False
    assert result["approved_subsidy_sgd"] == 0.0


def test_low_local_shareholding_is_rejected():
    result = evaluate(SAMPLE_FLEET_ELECTRIFICATION, sme_profile(local_shareholding_pct=20.0))
    assert result["decision_status"] == "REJECT_NON_SME"


def test_exclusions_outrank_the_sme_check():
    result = evaluate(SAMPLE_EXCLUDED_ITEM, sme_profile(annual_revenue_sgd=250000000.0))
    assert result["decision_status"] == "MANUAL_EXCLUSION_REVIEW"


def test_reporting_grant_pays_30_percent_of_the_fee():
    result = evaluate(SAMPLE_REPORTING_ONLY, reporting_profile(20000.0))
    assert result["decision_status"] == "PRE_APPROVED_SRG"
    assert result["approved_subsidy_sgd"] == 6000.0


def test_reporting_grant_is_capped():
    result = evaluate(SAMPLE_REPORTING_ONLY, reporting_profile(10000000.0))
    assert result["approved_subsidy_sgd"] == 150000.0


def test_reporting_grant_without_a_fee_needs_review():
    result = evaluate(SAMPLE_REPORTING_ONLY, reporting_profile(0.0))
    assert result["decision_status"] == "MANUAL_REVIEW"


def test_zero_baseline_spend_needs_review_instead_of_a_subsidy():
    profile = sme_profile(baseline_annual_energy_expenditure_sgd=0.0)
    result = evaluate(SAMPLE_FLEET_ELECTRIFICATION, profile)
    assert result["decision_status"] == "MANUAL_REVIEW"
    assert result["approved_subsidy_sgd"] == 0.0


def test_subsidy_never_exceeds_the_retrofit_cost():
    profile = sme_profile(estimated_retrofit_cost_sgd=12000.0)
    result = evaluate(SAMPLE_FLEET_ELECTRIFICATION, profile)
    assert result["approved_subsidy_sgd"] == 12000.0


def test_sloppy_ai_types_do_not_crash_the_logic():
    result = evaluate(SAMPLE_SLOPPY_TYPES)
    assert set(result) >= COMPLETE_RESULT_KEYS
    assert result["audit_passed"] is False
    assert result["approved_subsidy_sgd"] == 0.0


def test_empty_ai_answer_does_not_crash_the_logic():
    result = evaluate("{}")
    assert set(result) >= COMPLETE_RESULT_KEYS
    assert result["decision_status"] == "MANUAL_REVIEW"


def test_every_sample_gives_a_complete_result():
    for name, sample in sorted(globals().items()):
        if not name.startswith("SAMPLE_"):
            continue
        profile = reporting_profile(20000.0) if name == "SAMPLE_REPORTING_ONLY" else None
        result = evaluate(sample, profile)
        assert set(result) >= COMPLETE_RESULT_KEYS, name
        assert isinstance(result["reasons"], list), name
        assert isinstance(result["recommendations"], list), name
        assert result["approved_subsidy_sgd"] >= 0, name


def test_same_sample_gives_the_same_decision_every_time():
    first = evaluate(SAMPLE_MODERATE_SCOPE1)
    assert all(evaluate(SAMPLE_MODERATE_SCOPE1) == first for _ in range(5))


def test_the_evaluation_does_not_change_the_ai_answer_it_was_given():
    ai_audit = json.loads(SAMPLE_EXCLUDED_ITEM)
    before = json.dumps(ai_audit, sort_keys=True)
    with network_blocked():
        logic.evaluate_grant_application(sme_profile(), ai_audit)
    assert json.dumps(ai_audit, sort_keys=True) == before


def test_sme_check_and_subsidy_maths_on_sample_figures():
    assert logic.check_sme_status(100.0, 5000000.0, 50) is True
    assert logic.check_sme_status(29.9, 5000000.0, 50) is False
    assert logic.get_sme_fail_reasons(100.0, 5000000.0, 50) == []
    assert logic.calculate_subsidy(100000.0, 0.30, 350000.0) == 30000.0
    assert logic.calculate_subsidy(10000000.0, 0.30, 350000.0) == 350000.0


def test_passwords_hash_and_verify_without_any_network():
    with network_blocked():
        record = logic.build_new_user_record("sample_user", "Sample#Pass123")
        assert logic.verify_password("Sample#Pass123", record) is True
        assert logic.verify_password("wrong-password", record) is False


def test_logic_manager_loads_without_the_ai_library():
    """Importing logic_manager must not pull in openai or the AI Manager."""
    code = (
        "import sys, logic_manager; "
        "bad = [m for m in ('openai', 'ai_manager') if m in sys.modules]; "
        "sys.exit(1 if bad else 0)"
    )
    env = dict(os.environ)
    env.pop("OPENROUTER_API_KEY", None)
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env)
    assert done.returncode == 0


# ========================================================
# Run this file on its own
# ========================================================
def run_this_file():
    tests = [
        (name, function) for name, function in globals().items()
        if name.startswith("test_") and callable(function)
    ]  # dicts keep definition order
    failed = 0
    for name, function in tests:
        try:
            function()
            print(f"ok    {name}")
        except Exception as error:
            failed += 1
            print(f"FAIL  {name}: {error!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if run_this_file() else 0)
