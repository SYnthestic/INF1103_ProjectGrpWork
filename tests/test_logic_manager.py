"""Tests for the Logic Manager: grant decisions, SME check, subsidy maths
and password hashing. No network, files or AI are involved."""

import unittest

import logic_manager as logic


def make_profile(**changes):
    """A valid SME equipment proposal; override fields per test."""
    profile = {
        "annual_revenue_sgd": 5_000_000.0,
        "group_employment_size": 50,
        "local_shareholding_pct": 100.0,
        "proposal_type": "Equipment / Energy Upgrade",
        "sustainability_grant": "1. Energy Efficiency Grant (EEG) - Base Tier",
        "baseline_annual_energy_expenditure_sgd": 100_000.0,
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


class SmeStatusTests(unittest.TestCase):
    def test_meets_both_requirements(self):
        self.assertTrue(logic.check_sme_status(30.0, 100_000_000.0, 5000))

    def test_local_shareholding_below_30_fails(self):
        self.assertFalse(logic.check_sme_status(29.9, 1_000_000.0, 10))

    def test_revenue_over_cap_fails(self):
        self.assertFalse(logic.check_sme_status(100.0, 100_000_001.0, 10))

    def test_headcount_is_ignored(self):
        # The agreed rule set only uses shareholding and revenue.
        self.assertTrue(logic.check_sme_status(100.0, 1_000_000.0, 100_000))

    def test_fail_reasons_name_each_failed_requirement(self):
        reasons = logic.get_sme_fail_reasons(10.0, 200_000_000.0, 10)
        self.assertEqual(len(reasons), 2)
        self.assertIn("shareholding", reasons[0])
        self.assertIn("revenue", reasons[1])

    def test_no_fail_reasons_for_an_sme(self):
        self.assertEqual(logic.get_sme_fail_reasons(100.0, 1.0, 1), [])


class SubsidyTests(unittest.TestCase):
    def test_rate_applied(self):
        self.assertEqual(logic.calculate_subsidy(10_000, 0.5, 20_000), 5_000.0)

    def test_cap_applied(self):
        self.assertEqual(logic.calculate_subsidy(1_000_000, 0.7, 30_000), 30_000.0)

    def test_rounded_to_cents(self):
        self.assertEqual(logic.calculate_subsidy(333.333, 0.5, 1_000), 166.67)


class DecisionRuleTests(unittest.TestCase):
    def test_scope1_fast_track_is_base_tier(self):
        result = decide()
        self.assertEqual(result["decision_status"], "PRE_APPROVED_TIER_1")
        self.assertEqual(result["approved_subsidy_sgd"], 30_000.0)
        self.assertTrue(result["audit_passed"])
        self.assertTrue(result["is_sme"])

    def test_scope1_exactly_20_percent_is_fast_track(self):
        result = decide(audit=make_audit(estimated_energy_reduction_pct=20.0))
        self.assertEqual(result["decision_status"], "PRE_APPROVED_TIER_1")

    def test_scope1_between_15_and_20_is_provisional(self):
        result = decide(audit=make_audit(estimated_energy_reduction_pct=17.0))
        self.assertEqual(result["decision_status"], "PROVISIONAL_APPROVAL_TIER_2")
        self.assertEqual(result["approved_subsidy_sgd"], 20_000.0)

    def test_scope2_at_15_percent_is_provisional(self):
        result = decide(audit=make_audit(scope_category="Scope-2", estimated_energy_reduction_pct=15.0))
        self.assertEqual(result["decision_status"], "PROVISIONAL_APPROVAL_TIER_2")

    def test_scope2_at_30_percent_is_not_fast_tracked(self):
        result = decide(audit=make_audit(scope_category="Scope-2", estimated_energy_reduction_pct=30.0))
        self.assertEqual(result["decision_status"], "PROVISIONAL_APPROVAL_TIER_2")

    def test_ten_to_fifteen_percent_goes_to_manual_review(self):
        result = decide(audit=make_audit(estimated_energy_reduction_pct=12.0))
        self.assertEqual(result["decision_status"], "MANUAL_REVIEW")
        self.assertFalse(result["audit_passed"])

    def test_below_ten_percent_is_rejected(self):
        result = decide(audit=make_audit(estimated_energy_reduction_pct=9.9))
        self.assertEqual(result["decision_status"], "REJECT_LOW_IMPACT")
        self.assertEqual(result["approved_subsidy_sgd"], 0.0)

    def test_advanced_tier_needs_over_350_tonnes(self):
        profile = make_profile(baseline_annual_energy_expenditure_sgd=1_000_000.0)
        result = decide(profile, make_audit(estimated_lifetime_abatement_tonnes=400.0,
                                            estimated_energy_reduction_pct=12.0))
        self.assertEqual(result["decision_status"], "PRE_APPROVED_TIER_1_ADVANCED")
        self.assertEqual(result["approved_subsidy_sgd"], 350_000.0)

    def test_350_tonnes_exactly_is_not_advanced(self):
        result = decide(audit=make_audit(estimated_lifetime_abatement_tonnes=350.0))
        self.assertEqual(result["decision_status"], "PRE_APPROVED_TIER_1")

    def test_claimed_tonnes_without_energy_reduction_is_not_advanced(self):
        result = decide(audit=make_audit(estimated_lifetime_abatement_tonnes=900.0,
                                         estimated_energy_reduction_pct=0.0))
        self.assertEqual(result["decision_status"], "REJECT_LOW_IMPACT")

    def test_unknown_scope_goes_to_manual_review(self):
        result = decide(audit=make_audit(scope_category="Unknown"))
        self.assertEqual(result["decision_status"], "MANUAL_REVIEW")

    def test_exclusion_keyword_forces_exclusion_review(self):
        result = decide(audit=make_audit(detected_exclusion_keywords=["second-hand"]))
        self.assertEqual(result["decision_status"], "MANUAL_EXCLUSION_REVIEW")
        self.assertFalse(result["audit_passed"])
        self.assertTrue(any("second-hand" in reason for reason in result["reasons"]))

    def test_none_placeholder_is_not_an_exclusion(self):
        result = decide(audit=make_audit(detected_exclusion_keywords=["None", "N/A"]))
        self.assertEqual(result["decision_status"], "PRE_APPROVED_TIER_1")

    def test_fossil_fuel_modification_goes_to_exclusion_review(self):
        result = decide(audit=make_audit(primary_intervention_type="Fossil Fuel Modification"))
        self.assertEqual(result["decision_status"], "MANUAL_EXCLUSION_REVIEW")

    def test_non_sme_is_rejected_before_any_approval(self):
        result = decide(make_profile(annual_revenue_sgd=250_000_000.0))
        self.assertEqual(result["decision_status"], "REJECT_NON_SME")
        self.assertFalse(result["is_sme"])
        self.assertEqual(result["approved_subsidy_sgd"], 0.0)

    def test_low_local_shareholding_is_rejected(self):
        result = decide(make_profile(local_shareholding_pct=10.0))
        self.assertEqual(result["decision_status"], "REJECT_NON_SME")

    def test_exclusions_outrank_the_sme_check(self):
        result = decide(make_profile(annual_revenue_sgd=250_000_000.0),
                        make_audit(detected_exclusion_keywords=["refurbished"]))
        self.assertEqual(result["decision_status"], "MANUAL_EXCLUSION_REVIEW")

    def test_subsidy_never_exceeds_retrofit_cost(self):
        result = decide(make_profile(estimated_retrofit_cost_sgd=10_000.0))
        self.assertEqual(result["approved_subsidy_sgd"], 10_000.0)
        self.assertTrue(any("retrofit cost" in reason for reason in result["reasons"]))

    def test_zero_baseline_spend_goes_to_manual_review(self):
        result = decide(make_profile(baseline_annual_energy_expenditure_sgd=0.0))
        self.assertEqual(result["decision_status"], "MANUAL_REVIEW")
        self.assertEqual(result["approved_subsidy_sgd"], 0.0)


class ReportingGrantTests(unittest.TestCase):
    def reporting_profile(self, fee):
        return make_profile(proposal_type="ESG Reporting / Advisory",
                            reporting_advisory_fee_sgd=fee,
                            baseline_annual_energy_expenditure_sgd=0.0,
                            sustainability_grant="3. Sustainability Reporting Grant")

    def test_srg_pays_30_percent_of_the_fee(self):
        result = decide(self.reporting_profile(20_000.0), make_audit(scope_category="Unknown"))
        self.assertEqual(result["decision_status"], "PRE_APPROVED_SRG")
        self.assertEqual(result["approved_subsidy_sgd"], 6_000.0)

    def test_srg_is_capped(self):
        result = decide(self.reporting_profile(10_000_000.0), make_audit(scope_category="Unknown"))
        self.assertEqual(result["approved_subsidy_sgd"], 150_000.0)

    def test_srg_without_a_fee_needs_manual_review(self):
        result = decide(self.reporting_profile(0.0), make_audit(scope_category="Unknown"))
        self.assertEqual(result["decision_status"], "MANUAL_REVIEW")

    def test_non_sme_cannot_use_srg(self):
        profile = self.reporting_profile(20_000.0)
        profile["annual_revenue_sgd"] = 500_000_000.0
        self.assertEqual(decide(profile)["decision_status"], "REJECT_NON_SME")


class SchemeNoteTests(unittest.TestCase):
    def test_note_when_chosen_scheme_differs_from_match(self):
        profile = make_profile(sustainability_grant="3. Sustainability Reporting Grant")
        result = decide(profile)
        self.assertTrue(any("You selected" in text for text in result["recommendations"]))

    def test_no_note_when_scheme_matches(self):
        result = decide()
        self.assertFalse(any("You selected" in text for text in result["recommendations"]))

    def test_unrelated_choice_is_never_flagged(self):
        self.assertIsNone(logic.scheme_mismatch_note("5. Others", ["Anything"]))

    def test_note_ignores_a_non_string_choice(self):
        self.assertIsNone(logic.scheme_mismatch_note(0, ["Anything"]))


class RobustnessTests(unittest.TestCase):
    def test_bad_numbers_do_not_crash(self):
        profile = make_profile(annual_revenue_sgd=float("nan"),
                               group_employment_size=None,
                               local_shareholding_pct="lots")
        result = decide(profile)
        self.assertEqual(result["decision_status"], "REJECT_NON_SME")

    def test_missing_ai_fields_do_not_crash(self):
        result = decide(audit={})
        self.assertIn(result["decision_status"], {"MANUAL_REVIEW", "REJECT_LOW_IMPACT"})

    def test_result_always_has_the_same_keys(self):
        keys = {"is_sme", "decision_status", "reasons", "recommendations",
                "matched_schemes", "approved_subsidy_sgd", "audit_passed"}
        for audit in (make_audit(), make_audit(scope_category="Unknown"), make_audit(estimated_energy_reduction_pct=1.0)):
            self.assertEqual(set(decide(audit=audit)), keys)


class RuleEngineTests(unittest.TestCase):
    """The decision engine is a list of small rules; these test them one by one."""

    def case(self, profile=None, audit=None):
        return logic.build_case(profile or make_profile(), audit or make_audit())

    def test_rules_run_in_priority_order(self):
        names = [rule.__name__ for rule in logic.DECISION_RULES]
        self.assertEqual(names[0], "rule_exclusion_keywords")
        self.assertLess(names.index("rule_fossil_fuel_modification"), names.index("rule_not_an_sme"))
        self.assertLess(names.index("rule_not_an_sme"), names.index("rule_reporting_grant"))
        self.assertLess(names.index("rule_reporting_grant"), names.index("rule_unclassified_scope"))
        self.assertLess(names.index("rule_eeg_advanced_tier"), names.index("rule_eeg_base_tier"))
        self.assertLess(names.index("rule_eeg_base_tier"), names.index("rule_esp_provisional"))
        self.assertEqual(names[-1], "rule_low_impact")

    def test_last_rule_always_gives_a_decision(self):
        self.assertIsNotNone(logic.rule_low_impact(self.case()))

    def test_a_rule_that_does_not_apply_returns_none(self):
        clean = self.case()
        self.assertIsNone(logic.rule_exclusion_keywords(clean))
        self.assertIsNone(logic.rule_fossil_fuel_modification(clean))
        self.assertIsNone(logic.rule_not_an_sme(clean))
        self.assertIsNone(logic.rule_reporting_grant(clean))
        self.assertIsNone(logic.rule_unclassified_scope(clean))
        self.assertIsNone(logic.rule_borderline_impact(clean))

    def test_each_rule_returns_a_complete_decision(self):
        keys = {"decision_status", "reasons", "recommendations", "matched_schemes", "approved_subsidy_sgd"}
        decision = logic.rule_eeg_base_tier(self.case())
        self.assertEqual(set(decision), keys)

    def test_build_case_cleans_bad_values(self):
        case = logic.build_case({"annual_revenue_sgd": "lots", "group_employment_size": 12.7},
                                {"detected_exclusion_keywords": "None"})
        self.assertEqual(case["annual_revenue"], 0.0)
        self.assertEqual(case["headcount"], 12)
        self.assertEqual(case["exclusions"], [])

    def test_retrofit_cap_ignores_non_subsidy_decisions(self):
        decision = logic._decision("MANUAL_REVIEW", subsidy=500.0)
        logic.cap_subsidy_at_retrofit_cost(decision, {"retrofit_cost": 10.0})
        self.assertEqual(decision["approved_subsidy_sgd"], 500.0)


class PasswordTests(unittest.TestCase):
    def test_correct_password_verifies(self):
        record = logic.build_new_user_record("alice", "correct horse")
        self.assertTrue(logic.verify_password("correct horse", record))

    def test_wrong_password_fails(self):
        record = logic.build_new_user_record("alice", "correct horse")
        self.assertFalse(logic.verify_password("wrong horse", record))

    def test_plain_password_is_never_stored(self):
        record = logic.build_new_user_record("alice", "correct horse")
        self.assertNotIn("correct horse", str(record))

    def test_same_password_gets_different_salts(self):
        first = logic.build_new_user_record("a", "samepassword")
        second = logic.build_new_user_record("b", "samepassword")
        self.assertNotEqual(first["salt"], second["salt"])
        self.assertNotEqual(first["password_hash"], second["password_hash"])

    def test_unknown_user_fails(self):
        self.assertFalse(logic.verify_password("whatever", None))

    def test_damaged_record_fails_instead_of_crashing(self):
        self.assertFalse(logic.verify_password("x", {"salt": "zz", "password_hash": "1", "iterations": 5}))
        self.assertFalse(logic.verify_password("x", {"salt": 5, "password_hash": None}))

    def test_absurd_iteration_count_is_refused(self):
        record = logic.build_new_user_record("alice", "correct horse")
        record["iterations"] = 10**12
        self.assertFalse(logic.verify_password("correct horse", record))


if __name__ == "__main__":
    unittest.main()
