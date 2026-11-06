"""Tests for the adjustable grant rule thresholds (RuleConfig): checking new
values, decisions following the thresholds, and saving/loading them."""

import json
import os

from managers.logic_manager import (
    EEG_ADVANCED_MIN_TONNES,
    FAST_TRACK_MIN_PCT,
    MINIMUM_IMPACT_PCT,
    PROVISIONAL_MIN_PCT,
    DecisionEngine,
    LogicManager,
    LowImpactRule,
    RuleConfig,
)
from tests.helpers import raises, temp_data_dir


def profile():
    """A valid SME equipment proposal."""
    return {
        "annual_revenue_sgd": 5_000_000.0,
        "group_employment_size": 50,
        "local_shareholding_pct": 100.0,
        "proposal_type": "Equipment / Energy Upgrade",
        "sustainability_grant": "1. Energy Efficiency Grant (EEG) - Base Tier",
        "baseline_annual_energy_expenditure_sgd": 100_000.0,
        "estimated_retrofit_cost_sgd": 0.0,
        "reporting_advisory_fee_sgd": 0.0,
    }


def audit(scope="Scope-2", pct=12.0, tonnes=0.0):
    return {
        "scope_category": scope,
        "primary_intervention_type": "Smart HVAC / Chiller Optimization",
        "estimated_energy_reduction_pct": pct,
        "estimated_lifetime_abatement_tonnes": tonnes,
        "detected_exclusion_keywords": [],
        "ai_status": "ok",
    }


def status_with(config, **audit_fields):
    logic = LogicManager(rule_config=config, admin_username="")
    return logic.evaluate_grant_application(profile(), audit(**audit_fields))


def valid_values(**changes):
    values = RuleConfig().to_dict()
    values.update(changes)
    return values


# ---- Checking proposed thresholds -------------------------------------------


def test_the_defaults_are_the_original_rule_set():
    assert RuleConfig().to_dict() == {
        "minimum_impact_pct": MINIMUM_IMPACT_PCT,
        "provisional_min_pct": PROVISIONAL_MIN_PCT,
        "fast_track_min_pct": FAST_TRACK_MIN_PCT,
        "eeg_advanced_min_tonnes": EEG_ADVANCED_MIN_TONNES,
    }
    assert RuleConfig.problems(RuleConfig().to_dict()) == []


def test_valid_values_make_a_config():
    config = RuleConfig.from_dict(valid_values(provisional_min_pct=12))
    assert config.provisional_min_pct == 12.0
    assert isinstance(config.provisional_min_pct, float)


def test_non_numbers_are_refused():
    for bad in ("15", None, True, float("nan"), float("inf"), [15]):
        found = RuleConfig.problems(valid_values(provisional_min_pct=bad))
        assert any("must be a number" in text for text in found), bad


def test_out_of_range_values_are_refused():
    for name, bad in (
        ("minimum_impact_pct", 0),
        ("minimum_impact_pct", -5),
        ("fast_track_min_pct", 100.5),
        ("eeg_advanced_min_tonnes", 0),
        ("eeg_advanced_min_tonnes", RuleConfig.MAX_TONNES + 1),
    ):
        assert RuleConfig.problems(valid_values(**{name: bad})), (name, bad)


def test_percentages_must_not_decrease():
    found = RuleConfig.problems(valid_values(minimum_impact_pct=16))
    assert any("must not decrease" in text for text in found)
    found = RuleConfig.problems(valid_values(fast_track_min_pct=14))
    assert any("must not decrease" in text for text in found)
    # Equal thresholds are allowed (that band simply becomes empty).
    assert RuleConfig.problems(valid_values(provisional_min_pct=20)) == []


def test_missing_unknown_or_wrong_shaped_settings_are_refused():
    values = valid_values()
    del values["fast_track_min_pct"]
    assert RuleConfig.problems(values)
    assert any("Unknown" in text for text in RuleConfig.problems(valid_values(bonus=1)))
    for bad in (None, [], "x", 5):
        assert RuleConfig.problems(bad)


def test_from_dict_and_with_value_raise_for_bad_values():
    with raises(ValueError):
        RuleConfig.from_dict(valid_values(minimum_impact_pct=-1))
    with raises(ValueError):
        RuleConfig().with_value("fast_track_min_pct", 5)
    with raises(ValueError):
        RuleConfig().with_value("no_such_setting", 5)
    assert RuleConfig().with_value("fast_track_min_pct", 25).fast_track_min_pct == 25


def test_a_config_cannot_be_changed_in_place():
    config = RuleConfig()
    with raises(AttributeError):
        config.minimum_impact_pct = 1  # frozen dataclass


# ---- Decisions follow the thresholds ----------------------------------------


def test_lowering_the_provisional_line_turns_a_review_into_an_approval():
    assert status_with(RuleConfig(), pct=12)["decision_status"] == "MANUAL_REVIEW"
    lower = RuleConfig().with_value("provisional_min_pct", 12)
    result = status_with(lower, pct=12)
    assert result["decision_status"] == "PROVISIONAL_APPROVAL_TIER_2"
    assert any("12% threshold" in text for text in result["reasons"])


def test_raising_the_minimum_turns_a_review_into_a_rejection():
    stricter = RuleConfig().with_value("minimum_impact_pct", 13)
    result = status_with(stricter, pct=12)
    assert result["decision_status"] == "REJECT_LOW_IMPACT"
    assert any("13.0%" in text for text in result["reasons"])


def test_raising_the_fast_track_line_moves_scope_1_to_the_esp():
    assert status_with(RuleConfig(), scope="Scope-1", pct=22)["decision_status"] == (
        "PRE_APPROVED_TIER_1"
    )
    stricter = RuleConfig().with_value("fast_track_min_pct", 25)
    assert status_with(stricter, scope="Scope-1", pct=22)["decision_status"] == (
        "PROVISIONAL_APPROVAL_TIER_2"
    )


def test_the_advanced_tier_follows_the_tonnes_threshold():
    assert status_with(RuleConfig(), pct=16, tonnes=400)["decision_status"] == (
        "PRE_APPROVED_TIER_1_ADVANCED"
    )
    stricter = RuleConfig().with_value("eeg_advanced_min_tonnes", 500)
    assert status_with(stricter, pct=16, tonnes=400)["decision_status"] == (
        "PROVISIONAL_APPROVAL_TIER_2"
    )
    result = status_with(stricter, pct=16, tonnes=600)
    assert any("500-tonne" in text for text in result["reasons"])


def test_the_default_messages_are_unchanged():
    result = status_with(RuleConfig(), scope="Scope-1", pct=22)
    assert any("meets the 20% threshold" in text for text in result["reasons"])
    result = status_with(RuleConfig(), pct=5)
    assert any("minimum threshold of 10.0%" in text for text in result["reasons"])


def test_use_rule_config_changes_later_decisions():
    logic = LogicManager(admin_username="")
    assert logic.evaluate_grant_application(profile(), audit(pct=12))[
        "decision_status"
    ] == "MANUAL_REVIEW"
    logic.use_rule_config(RuleConfig().with_value("provisional_min_pct", 11))
    assert logic.rule_config.provisional_min_pct == 11
    assert logic.evaluate_grant_application(profile(), audit(pct=12))[
        "decision_status"
    ] == "PROVISIONAL_APPROVAL_TIER_2"


def test_a_supplied_engine_is_kept_when_the_thresholds_change():
    engine = DecisionEngine([LowImpactRule()])
    logic = LogicManager(engine=engine, admin_username="")
    logic.use_rule_config(RuleConfig().with_value("provisional_min_pct", 11))
    assert logic.engine is engine


# ---- Saving and loading the thresholds (Data Manager) -----------------------


def test_no_saved_thresholds_means_defaults():
    with temp_data_dir() as (dm, _):
        assert dm.load_rule_config() == (None, "missing")


def test_thresholds_round_trip_with_who_changed_them():
    with temp_data_dir() as (dm, folder):
        values = valid_values(provisional_min_pct=12.0)
        assert dm.save_rule_config(values, changed_by="boss")
        loaded, status = dm.load_rule_config()
        assert status == "loaded"
        assert loaded == values
        with open(os.path.join(folder, dm.RULES_CONFIG_FILE), encoding="utf-8") as f:
            stored = json.load(f)
        assert stored["changed_by"] == "boss" and stored["changed_at"]


def test_a_corrupt_settings_file_is_set_aside():
    with temp_data_dir() as (dm, folder):
        path = os.path.join(folder, dm.RULES_CONFIG_FILE)
        with open(path, "w", encoding="utf-8") as file:
            file.write("{not json")
        assert dm.load_rule_config() == (None, "corrupt")
        assert os.path.exists(path + ".corrupt")


def test_a_settings_file_of_the_wrong_shape_is_set_aside():
    with temp_data_dir() as (dm, folder):
        path = os.path.join(folder, dm.RULES_CONFIG_FILE)
        with open(path, "w", encoding="utf-8") as file:
            json.dump([1, 2, 3], file)
        assert dm.load_rule_config() == (None, "corrupt")


def test_hand_edited_bad_values_are_caught_by_the_logic_manager():
    with temp_data_dir() as (dm, _):
        dm.save_rule_config(valid_values(minimum_impact_pct=50), changed_by="x")
        loaded, status = dm.load_rule_config()
        assert status == "loaded"
        assert LogicManager.rule_config_problems(loaded)


def test_a_record_file_cannot_replace_the_settings_file():
    with temp_data_dir() as (dm, _):
        assert dm.save_data_to_json([], "rules_config") == (None, "invalid_name")


def test_an_audit_records_the_thresholds_it_used():
    with temp_data_dir() as (dm, _):
        used = valid_values(provisional_min_pct=12.0)
        saved = dm.append_user_audit(
            "alice", {"Company Name": "A"}, {}, {}, rules_used=used
        )
        assert saved["rules_used"] == used
        assert dm.get_user_audits("alice")[0]["rules_used"] == used
