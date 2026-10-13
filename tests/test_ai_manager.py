"""Tests for the AI Manager's output cleaning. The network call itself is
not tested; these cover what happens to whatever the model sends back."""

import json
import ai_manager as ai
from tests.helpers import raises


def parse_ai_audit_good_json(**changes):
    data = {
        "scope_category": "Scope-1",
        "primary_intervention_type": "Fleet Electrification",
        "estimated_energy_reduction_pct": 30,
        "estimated_lifetime_abatement_tonnes": 120,
        "detected_exclusion_keywords": [],
        "implementation_bottleneck": "",
        "ai_reasoning_summary": "Looks fine.",
    }
    data.update(changes)
    return json.dumps(data)


def test_valid_json_is_accepted():
    audit = ai.parse_ai_audit(parse_ai_audit_good_json())
    assert audit["scope_category"] == "Scope-1"
    assert audit["estimated_energy_reduction_pct"] == 30.0
    assert audit["ai_status"] == "ok"
    assert not ai.ai_call_failed(audit)


def test_code_fences_are_removed():
    audit = ai.parse_ai_audit("```json\n" + parse_ai_audit_good_json() + "\n```")
    assert audit["ai_status"] == "ok"


def test_text_around_the_json_is_ignored():
    audit = ai.parse_ai_audit(
        "Sure! Here you go:\n" + parse_ai_audit_good_json() + "\nHope that helps."
    )
    assert audit["scope_category"] == "Scope-1"


def test_garbage_gives_failed_defaults():
    for raw in ("not json at all", "", None, 42, ["a"], "[1, 2]", "{broken"):
        audit = ai.parse_ai_audit(raw)
        assert ai.ai_call_failed(audit)
        assert audit["scope_category"] == "Unknown"


def test_defaults_are_not_shared_between_calls():
    first = ai.parse_ai_audit("garbage")
    first["detected_exclusion_keywords"].append("oops")
    assert ai.parse_ai_audit("garbage")["detected_exclusion_keywords"] == []


def test_scope_spellings_are_normalised():
    for text in ("scope-1", "Scope 1", "SCOPE1", " scope_1 "):
        assert ai._to_scope(text) == "Scope-1", text


def test_bad_scope_becomes_unknown():
    for value in ("Scope-4", "", None, 3, "scope"):
        assert ai._to_scope(value) == "Unknown", value


def test_numbers_are_extracted_and_clamped():
    assert ai._to_number("30%") == 30.0
    assert ai._to_number("1,200") == 1200.0
    assert ai._to_number(250, maximum=100.0) == 100.0
    assert ai._to_number(-5, minimum=0.0) == 0.0


def test_unusable_numbers_use_the_default():
    for value in (None, True, "n/a", float("nan"), float("inf"), [], {}):
        assert ai._to_number(value, 7.0) == 7.0, value


def test_keywords_from_a_string_are_split():
    assert ai._to_string_list("second-hand; refurbished, used") == [
        "second-hand",
        "refurbished",
        "used",
    ]


def test_placeholder_keywords_are_dropped():
    assert ai._to_string_list(["None", "N/A", " ", "second-hand", "none detected."]) == [
        "second-hand"
    ]


def test_non_list_keywords_give_empty_list():
    for value in (None, 5, {"a": 1}):
        assert ai._to_string_list(value) == []


def test_nested_values_in_keywords_are_skipped():
    assert ai._to_string_list([["x"], {"y": 1}, "ok"]) == ["ok"]


def test_energy_reduction_is_clamped_to_0_100():
    audit = ai.sanitise_ai_audit({"estimated_energy_reduction_pct": 900})
    assert audit["estimated_energy_reduction_pct"] == 100.0


def test_default_is_failed():
    assert ai.ai_call_failed(dict(ai.DEFAULT_AI_AUDIT))


def test_non_dict_is_failed():
    assert ai.ai_call_failed(None)


def test_missing_key_gives_a_clear_error():
    import os

    saved = os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        with raises(RuntimeError) as caught:
            ai.setup_ai_client()
        assert "OPENROUTER_API_KEY" in str(caught.exception)
    finally:
        if saved is not None:
            os.environ["OPENROUTER_API_KEY"] = saved
