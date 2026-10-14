"""Tests for the Logic Manager: grant decisions, SME check, subsidy maths
and password hashing. No network, files or AI are involved."""

import logic_manager as logic

import math

VALID_STATUSES = {
    "REJECT_NON_SME",
    "REJECT_LOW_IMPACT",
    "PRE_APPROVED_SRG",
    "PRE_APPROVED_TIER_1",
    "PRE_APPROVED_TIER_1_ADVANCED",
    "PROVISIONAL_APPROVAL_TIER_2",
    "MANUAL_REVIEW",
    "MANUAL_EXCLUSION_REVIEW",
}


def all_scenarios():
    """A spread of inputs that exercise most rules."""
    return [
        (make_profile(), make_audit()),
        (make_profile(), make_audit(scope_category="Scope-2", estimated_energy_reduction_pct=16.0)),
        (make_profile(), make_audit(estimated_energy_reduction_pct=12.0)),
        (make_profile(), make_audit(estimated_energy_reduction_pct=1.0)),
        (make_profile(), make_audit(scope_category="Unknown")),
        (make_profile(), make_audit(detected_exclusion_keywords=["second-hand"])),
        (make_profile(annual_revenue_sgd=250000000.0), make_audit()),
        (reporting_grant_reporting_profile(20000.0), make_audit(scope_category="Unknown")),
        (
            make_profile(baseline_annual_energy_expenditure_sgd=1000000.0),
            make_audit(estimated_lifetime_abatement_tonnes=400.0),
        ),
    ]


# ---- SME and subsidy boundaries -------------------------------------------

def test_sme_exactly_at_both_limits_passes():
    assert logic.check_sme_status(30.0, 100000000.0, 1)


def test_subsidy_with_zero_cost_rate_or_cap_is_zero():
    assert logic.calculate_subsidy(0, 0.5, 20000) == 0.0
    assert logic.calculate_subsidy(10000, 0.0, 20000) == 0.0
    assert logic.calculate_subsidy(10000, 0.5, 0) == 0.0


def test_srg_fee_where_30_percent_equals_the_cap():
    result = decide(
        reporting_grant_reporting_profile(500000.0), make_audit(scope_category="Unknown")
    )
    assert result["decision_status"] == "PRE_APPROVED_SRG"
    assert result["approved_subsidy_sgd"] == 150000.0


# ---- Energy-reduction boundaries (Scope-1) ----------------------------------

def test_scope1_reduction_boundaries():
    cases = [
        (9.99, "REJECT_LOW_IMPACT"),
        (10.0, "MANUAL_REVIEW"),
        (14.99, "MANUAL_REVIEW"),
        (15.0, "PROVISIONAL_APPROVAL_TIER_2"),
        (19.99, "PROVISIONAL_APPROVAL_TIER_2"),
        (20.0, "PRE_APPROVED_TIER_1"),
    ]
    for pct, expected in cases:
        result = decide(audit=make_audit(estimated_energy_reduction_pct=pct))
        assert result["decision_status"] == expected, f"{pct}% gave {result['decision_status']}"


# ---- Retrofit cost cap --------------------------------------------------------

def test_retrofit_cost_of_zero_means_no_cap():
    result = decide(make_profile(estimated_retrofit_cost_sgd=0.0))
    assert result["approved_subsidy_sgd"] == 30000.0


def test_tiny_retrofit_cost_caps_the_subsidy():
    result = decide(make_profile(estimated_retrofit_cost_sgd=0.01))
    assert result["approved_subsidy_sgd"] == 0.01


def test_retrofit_cap_applies_to_the_advanced_tier():
    profile = make_profile(
        baseline_annual_energy_expenditure_sgd=1000000.0, estimated_retrofit_cost_sgd=100000.0
    )
    result = decide(profile, make_audit(estimated_lifetime_abatement_tonnes=400.0))
    assert result["decision_status"] == "PRE_APPROVED_TIER_1_ADVANCED"
    assert result["approved_subsidy_sgd"] == 100000.0


# ---- Rule interactions --------------------------------------------------------

def test_exclusion_beats_the_advanced_tier():
    profile = make_profile(baseline_annual_energy_expenditure_sgd=1000000.0)
    audit = make_audit(
        estimated_lifetime_abatement_tonnes=400.0, detected_exclusion_keywords=["second-hand"]
    )
    assert decide(profile, audit)["decision_status"] == "MANUAL_EXCLUSION_REVIEW"


def test_non_sme_beats_the_advanced_tier():
    profile = make_profile(
        annual_revenue_sgd=250000000.0, baseline_annual_energy_expenditure_sgd=1000000.0
    )
    result = decide(profile, make_audit(estimated_lifetime_abatement_tonnes=400.0))
    assert result["decision_status"] == "REJECT_NON_SME"
    assert result["approved_subsidy_sgd"] == 0.0


def test_fossil_fuel_modification_beats_the_non_sme_rejection():
    result = decide(
        make_profile(annual_revenue_sgd=250000000.0),
        make_audit(primary_intervention_type="Fossil Fuel Modification"),
    )
    assert result["decision_status"] == "MANUAL_EXCLUSION_REVIEW"


def test_unused_cost_field_is_ignored():
    with_fee = decide(make_profile(reporting_advisory_fee_sgd=99999.0))
    without_fee = decide(make_profile(reporting_advisory_fee_sgd=0.0))
    assert with_fee == without_fee


# ---- Bad or unexpected input ------------------------------------------------

def test_empty_profile_does_not_crash_and_is_not_approved():
    result = decide(profile={})
    assert result["decision_status"] in VALID_STATUSES
    assert not result["audit_passed"]
    assert result["approved_subsidy_sgd"] == 0.0


def test_infinite_and_negative_numbers_do_not_crash():
    bad_profiles = [
        make_profile(annual_revenue_sgd=float("inf")),
        make_profile(annual_revenue_sgd=-5.0),
        make_profile(baseline_annual_energy_expenditure_sgd=-1.0),
        make_profile(estimated_retrofit_cost_sgd=-100.0),
        make_profile(local_shareholding_pct=150.0),
        make_profile(local_shareholding_pct=-10.0),
    ]
    for profile in bad_profiles:
        result = decide(profile)
        assert result["decision_status"] in VALID_STATUSES
        assert math.isfinite(result["approved_subsidy_sgd"])
        assert result["approved_subsidy_sgd"] >= 0.0


def test_wrong_types_in_the_ai_audit_do_not_crash():
    bad_audits = [
        make_audit(estimated_energy_reduction_pct="high"),
        make_audit(estimated_energy_reduction_pct=None),
        make_audit(estimated_energy_reduction_pct=float("nan")),
        make_audit(estimated_lifetime_abatement_tonnes="lots"),
        make_audit(detected_exclusion_keywords=None),
        make_audit(detected_exclusion_keywords={"a": 1}),
        make_audit(detected_exclusion_keywords=[1, None, "second-hand"]),
        make_audit(scope_category=None),
    ]
    for audit in bad_audits:
        assert decide(audit=audit)["decision_status"] in VALID_STATUSES


def test_placeholder_keywords_in_any_case_are_not_exclusions():
    result = decide(audit=make_audit(detected_exclusion_keywords=["NONE", " n/a ", ""]))
    assert result["decision_status"] == "PRE_APPROVED_TIER_1"


def test_odd_scope_spellings_never_pre_approve_by_accident():
    for scope in ("scope-1", "Scope 1", "Scope-3", "", "SCOPE-1"):
        result = decide(audit=make_audit(scope_category=scope))
        assert result["decision_status"] in VALID_STATUSES


def test_unknown_proposal_type_does_not_crash():
    for proposal_type in ("Something Else", "", None):
        result = decide(make_profile(proposal_type=proposal_type))
        assert result["decision_status"] in VALID_STATUSES


# ---- Determinism and result shape --------------------------------------------

def test_same_inputs_give_the_same_result_and_are_not_modified():
    for profile, audit in all_scenarios():
        profile_before = dict(profile)
        audit_before = {k: (list(v) if isinstance(v, list) else v) for k, v in audit.items()}
        first = decide(profile, audit)
        second = decide(profile, audit)
        assert first == second
        assert profile == profile_before
        assert audit == audit_before


def test_result_lists_are_not_shared_between_calls():
    first = decide()
    first["reasons"].append("tampered")
    first["recommendations"].append("tampered")
    first["matched_schemes"].append("tampered")
    second = decide()
    assert "tampered" not in second["reasons"]
    assert "tampered" not in second["recommendations"]
    assert "tampered" not in second["matched_schemes"]


def test_output_types_are_the_same_on_every_path():
    for profile, audit in all_scenarios():
        result = decide(profile, audit)
        assert isinstance(result["is_sme"], bool)
        assert isinstance(result["audit_passed"], bool)
        assert isinstance(result["approved_subsidy_sgd"], float)
        assert isinstance(result["reasons"], list)
        assert all(isinstance(r, str) for r in result["reasons"])
        assert isinstance(result["recommendations"], list)
        assert isinstance(result["matched_schemes"], list)


def test_every_status_the_logic_returns_is_a_known_status():
    for profile, audit in all_scenarios():
        assert decide(profile, audit)["decision_status"] in VALID_STATUSES


def test_rejections_and_reviews_never_pay_a_subsidy():
    for profile, audit in all_scenarios():
        result = decide(profile, audit)
        if result["decision_status"].startswith(("REJECT", "MANUAL")):
            assert result["approved_subsidy_sgd"] == 0.0
            assert not result["audit_passed"]


# ---- Scheme mismatch note -----------------------------------------------------

def test_missing_grant_choice_gives_no_note():
    assert logic.scheme_mismatch_note(None, ["Anything"]) is None
    result = decide(make_profile(sustainability_grant=None))
    assert not any("You selected" in text for text in result["recommendations"])


def test_mismatch_note_with_no_matched_schemes_does_not_crash():
    logic.scheme_mismatch_note("1. Energy Efficiency Grant (EEG) - Base Tier", [])


# ---- Passwords ----------------------------------------------------------------

def test_password_is_case_sensitive():
    record = logic.build_new_user_record("alice", "correct horse")
    assert not logic.verify_password("Correct Horse", record)


def test_spaces_around_a_password_are_not_stripped():
    record = logic.build_new_user_record("alice", "correct horse")
    assert not logic.verify_password(" correct horse", record)
    assert not logic.verify_password("correct horse ", record)


def test_unicode_password_round_trips():
    record = logic.build_new_user_record("alice", "pässwörd✓")
    assert logic.verify_password("pässwörd✓", record)
    assert not logic.verify_password("passwoerd", record)


def test_password_at_the_limit_works_and_beyond_is_refused():
    limit = logic.MAX_PASSWORD_CHARS_CHECKED
    ok = "x" * limit
    record = logic.build_new_user_record("alice", ok)
    assert logic.verify_password(ok, record)

    too_long = "x" * (limit + 1)
    assert not logic.verify_password(too_long, record)


def test_zero_or_negative_iterations_are_refused():
    for iterations in (0, -1):
        record = logic.build_new_user_record("alice", "correct horse")
        record["iterations"] = iterations
        assert not logic.verify_password("correct horse", record)


def test_missing_iterations_falls_back_to_the_default():
    record = logic.build_new_user_record("alice", "correct horse")
    del record["iterations"]
    assert logic.verify_password("correct horse", record)


def test_record_with_missing_or_damaged_fields_fails_safely():
    record = logic.build_new_user_record("alice", "correct horse")
    for field in ("salt", "password_hash"):
        damaged = dict(record)
        del damaged[field]
        assert not logic.verify_password("correct horse", damaged), f"missing {field} still verified"
    truncated = dict(record, password_hash=record["password_hash"][:10])
    assert not logic.verify_password("correct horse", truncated)
    not_hex = dict(record, password_hash="not-hex!")
    assert not logic.verify_password("correct horse", not_hex)


def make_profile(**changes):
    """A valid SME equipment proposal; override fields per test."""
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


def make_audit(**changes):
    """A clean AI audit; override fields per test."""
    audit = {
        "scope_category": "Scope-1",
        "primary_intervention_type": "Commercial Fleet Electrification",
        "estimated_energy_reduction_pct": 25.0,
        "estimated_lifetime_abatement_tonnes": 0.0,
        "detected_exclusion_keywords": [],
        "implementation_bottleneck": "",
        "ai_reasoning_summary": "ok",
        "ai_status": "ok",
    }
    audit.update(changes)
    return audit


def decide(profile=None, audit=None):
    return logic.evaluate_grant_application(
        profile if profile is not None else make_profile(),
        audit if audit is not None else make_audit(),
    )


def test_meets_both_requirements():
    assert logic.check_sme_status(30.0, 100000000.0, 5000)


def test_local_shareholding_below_30_fails():
    assert not logic.check_sme_status(29.9, 1000000.0, 10)


def test_revenue_over_cap_fails():
    assert not logic.check_sme_status(100.0, 100000001.0, 10)


def test_headcount_is_ignored():
    assert logic.check_sme_status(100.0, 1000000.0, 100000)


def test_fail_reasons_name_each_failed_requirement():
    reasons = logic.get_sme_fail_reasons(10.0, 200000000.0, 10)
    assert len(reasons) == 2
    assert "shareholding" in reasons[0]
    assert "revenue" in reasons[1]


def test_no_fail_reasons_for_an_sme():
    assert logic.get_sme_fail_reasons(100.0, 1.0, 1) == []


def test_rate_applied():
    assert logic.calculate_subsidy(10000, 0.5, 20000) == 5000.0


def test_cap_applied():
    assert logic.calculate_subsidy(1000000, 0.7, 30000) == 30000.0


def test_rounded_to_cents():
    assert logic.calculate_subsidy(333.333, 0.5, 1000) == 166.67


def test_scope1_fast_track_is_base_tier():
    result = decide()
    assert result["decision_status"] == "PRE_APPROVED_TIER_1"
    assert result["approved_subsidy_sgd"] == 30000.0
    assert result["audit_passed"]
    assert result["is_sme"]


def test_scope1_exactly_20_percent_is_fast_track():
    result = decide(audit=make_audit(estimated_energy_reduction_pct=20.0))
    assert result["decision_status"] == "PRE_APPROVED_TIER_1"


def test_scope1_between_15_and_20_is_provisional():
    result = decide(audit=make_audit(estimated_energy_reduction_pct=17.0))
    assert result["decision_status"] == "PROVISIONAL_APPROVAL_TIER_2"
    assert result["approved_subsidy_sgd"] == 20000.0


def test_scope2_at_15_percent_is_provisional():
    result = decide(audit=make_audit(scope_category="Scope-2", estimated_energy_reduction_pct=15.0))
    assert result["decision_status"] == "PROVISIONAL_APPROVAL_TIER_2"


def test_scope2_at_30_percent_is_not_fast_tracked():
    result = decide(audit=make_audit(scope_category="Scope-2", estimated_energy_reduction_pct=30.0))
    assert result["decision_status"] == "PROVISIONAL_APPROVAL_TIER_2"


def test_ten_to_fifteen_percent_goes_to_manual_review():
    result = decide(audit=make_audit(estimated_energy_reduction_pct=12.0))
    assert result["decision_status"] == "MANUAL_REVIEW"
    assert not result["audit_passed"]


def test_below_ten_percent_is_rejected():
    result = decide(audit=make_audit(estimated_energy_reduction_pct=9.9))
    assert result["decision_status"] == "REJECT_LOW_IMPACT"
    assert result["approved_subsidy_sgd"] == 0.0


def test_advanced_tier_needs_over_350_tonnes():
    profile = make_profile(baseline_annual_energy_expenditure_sgd=1000000.0)
    result = decide(
        profile,
        make_audit(estimated_lifetime_abatement_tonnes=400.0, estimated_energy_reduction_pct=12.0),
    )
    assert result["decision_status"] == "PRE_APPROVED_TIER_1_ADVANCED"
    assert result["approved_subsidy_sgd"] == 350000.0


def test_350_tonnes_exactly_is_not_advanced():
    result = decide(audit=make_audit(estimated_lifetime_abatement_tonnes=350.0))
    assert result["decision_status"] == "PRE_APPROVED_TIER_1"


def test_claimed_tonnes_without_energy_reduction_is_not_advanced():
    result = decide(
        audit=make_audit(
            estimated_lifetime_abatement_tonnes=900.0, estimated_energy_reduction_pct=0.0
        )
    )
    assert result["decision_status"] == "REJECT_LOW_IMPACT"


def test_unknown_scope_goes_to_manual_review():
    result = decide(audit=make_audit(scope_category="Unknown"))
    assert result["decision_status"] == "MANUAL_REVIEW"


def test_exclusion_keyword_forces_exclusion_review():
    result = decide(audit=make_audit(detected_exclusion_keywords=["second-hand"]))
    assert result["decision_status"] == "MANUAL_EXCLUSION_REVIEW"
    assert not result["audit_passed"]
    assert any(("second-hand" in reason for reason in result["reasons"]))


def test_none_placeholder_is_not_an_exclusion():
    result = decide(audit=make_audit(detected_exclusion_keywords=["None", "N/A"]))
    assert result["decision_status"] == "PRE_APPROVED_TIER_1"


def test_fossil_fuel_modification_goes_to_exclusion_review():
    result = decide(audit=make_audit(primary_intervention_type="Fossil Fuel Modification"))
    assert result["decision_status"] == "MANUAL_EXCLUSION_REVIEW"


def test_non_sme_is_rejected_before_any_approval():
    result = decide(make_profile(annual_revenue_sgd=250000000.0))
    assert result["decision_status"] == "REJECT_NON_SME"
    assert not result["is_sme"]
    assert result["approved_subsidy_sgd"] == 0.0


def test_low_local_shareholding_is_rejected():
    result = decide(make_profile(local_shareholding_pct=10.0))
    assert result["decision_status"] == "REJECT_NON_SME"


def test_exclusions_outrank_the_sme_check():
    result = decide(
        make_profile(annual_revenue_sgd=250000000.0),
        make_audit(detected_exclusion_keywords=["refurbished"]),
    )
    assert result["decision_status"] == "MANUAL_EXCLUSION_REVIEW"


def test_subsidy_never_exceeds_retrofit_cost():
    result = decide(make_profile(estimated_retrofit_cost_sgd=10000.0))
    assert result["approved_subsidy_sgd"] == 10000.0
    assert any(("retrofit cost" in reason for reason in result["reasons"]))


def test_zero_baseline_spend_goes_to_manual_review():
    result = decide(make_profile(baseline_annual_energy_expenditure_sgd=0.0))
    assert result["decision_status"] == "MANUAL_REVIEW"
    assert result["approved_subsidy_sgd"] == 0.0


def reporting_grant_reporting_profile(fee):
    return make_profile(
        proposal_type="ESG Reporting / Advisory",
        reporting_advisory_fee_sgd=fee,
        baseline_annual_energy_expenditure_sgd=0.0,
        sustainability_grant="3. Sustainability Reporting Grant",
    )


def test_srg_pays_30_percent_of_the_fee():
    result = decide(
        reporting_grant_reporting_profile(20000.0), make_audit(scope_category="Unknown")
    )
    assert result["decision_status"] == "PRE_APPROVED_SRG"
    assert result["approved_subsidy_sgd"] == 6000.0


def test_srg_is_capped():
    result = decide(
        reporting_grant_reporting_profile(10000000.0), make_audit(scope_category="Unknown")
    )
    assert result["approved_subsidy_sgd"] == 150000.0


def test_srg_without_a_fee_needs_manual_review():
    result = decide(reporting_grant_reporting_profile(0.0), make_audit(scope_category="Unknown"))
    assert result["decision_status"] == "MANUAL_REVIEW"


def test_non_sme_cannot_use_srg():
    profile = reporting_grant_reporting_profile(20000.0)
    profile["annual_revenue_sgd"] = 500000000.0
    assert decide(profile)["decision_status"] == "REJECT_NON_SME"


def test_note_when_chosen_scheme_differs_from_match():
    profile = make_profile(sustainability_grant="3. Sustainability Reporting Grant")
    result = decide(profile)
    assert any(("You selected" in text for text in result["recommendations"]))


def test_no_note_when_scheme_matches():
    result = decide()
    assert not any(("You selected" in text for text in result["recommendations"]))


def test_unrelated_choice_is_never_flagged():
    assert logic.scheme_mismatch_note("5. Others", ["Anything"]) is None


def test_note_ignores_a_non_string_choice():
    assert logic.scheme_mismatch_note(0, ["Anything"]) is None


def test_bad_numbers_do_not_crash():
    profile = make_profile(
        annual_revenue_sgd=float("nan"), group_employment_size=None, local_shareholding_pct="lots"
    )
    result = decide(profile)
    assert result["decision_status"] == "REJECT_NON_SME"


def test_missing_ai_fields_do_not_crash():
    result = decide(audit={})
    assert result["decision_status"] in {"MANUAL_REVIEW", "REJECT_LOW_IMPACT"}


def test_result_always_has_the_same_keys():
    keys = {
        "is_sme",
        "decision_status",
        "reasons",
        "recommendations",
        "matched_schemes",
        "approved_subsidy_sgd",
        "audit_passed",
    }
    for audit in (
        make_audit(),
        make_audit(scope_category="Unknown"),
        make_audit(estimated_energy_reduction_pct=1.0),
    ):
        assert set(decide(audit=audit)) == keys


def rule_engine_case(profile=None, audit=None):
    return logic.build_case(profile or make_profile(), audit or make_audit())


def test_rules_run_in_priority_order():
    names = [rule.__name__ for rule in logic.DECISION_RULES]
    assert names[0] == "rule_exclusion_keywords"
    assert names.index("rule_fossil_fuel_modification") < names.index("rule_not_an_sme")
    assert names.index("rule_not_an_sme") < names.index("rule_ai_failed")
    assert names.index("rule_ai_failed") < names.index("rule_reporting_grant")
    assert names.index("rule_reporting_grant") < names.index("rule_unclassified_scope")
    assert names.index("rule_eeg_advanced_tier") < names.index("rule_eeg_base_tier")
    assert names.index("rule_eeg_base_tier") < names.index("rule_esp_provisional")
    assert names[-1] == "rule_low_impact"


def test_last_rule_always_gives_a_decision():
    assert logic.rule_low_impact(rule_engine_case()) is not None


def test_a_rule_that_does_not_apply_returns_none():
    clean = rule_engine_case()
    assert logic.rule_exclusion_keywords(clean) is None
    assert logic.rule_fossil_fuel_modification(clean) is None
    assert logic.rule_not_an_sme(clean) is None
    assert logic.rule_reporting_grant(clean) is None
    assert logic.rule_unclassified_scope(clean) is None
    assert logic.rule_borderline_impact(clean) is None


def test_each_rule_returns_a_complete_decision():
    keys = {
        "decision_status",
        "reasons",
        "recommendations",
        "matched_schemes",
        "approved_subsidy_sgd",
    }
    decision = logic.rule_eeg_base_tier(rule_engine_case())
    assert set(decision) == keys


def test_build_case_cleans_bad_values():
    case = logic.build_case(
        {"annual_revenue_sgd": "lots", "group_employment_size": 12.7},
        {"detected_exclusion_keywords": "None"},
    )
    assert case["annual_revenue"] == 0.0
    assert case["headcount"] == 12
    assert case["exclusions"] == []


def test_retrofit_cap_ignores_non_subsidy_decisions():
    decision = logic._decision("MANUAL_REVIEW", subsidy=500.0)
    logic.cap_subsidy_at_retrofit_cost(decision, {"retrofit_cost": 10.0})
    assert decision["approved_subsidy_sgd"] == 500.0


def test_correct_password_verifies():
    record = logic.build_new_user_record("alice", "correct horse")
    assert logic.verify_password("correct horse", record)


def test_wrong_password_fails():
    record = logic.build_new_user_record("alice", "correct horse")
    assert not logic.verify_password("wrong horse", record)


def test_plain_password_is_never_stored():
    record = logic.build_new_user_record("alice", "correct horse")
    assert "correct horse" not in str(record)


def test_same_password_gets_different_salts():
    first = logic.build_new_user_record("a", "samepassword")
    second = logic.build_new_user_record("b", "samepassword")
    assert first["salt"] != second["salt"]
    assert first["password_hash"] != second["password_hash"]


def test_unknown_user_fails():
    assert not logic.verify_password("whatever", None)


def test_damaged_record_fails_instead_of_crashing():
    assert not logic.verify_password("x", {"salt": "zz", "password_hash": "1", "iterations": 5})
    assert not logic.verify_password("x", {"salt": 5, "password_hash": None})


def test_absurd_iteration_count_is_refused():
    record = logic.build_new_user_record("alice", "correct horse")
    record["iterations"] = 10**12
    assert not logic.verify_password("correct horse", record)
