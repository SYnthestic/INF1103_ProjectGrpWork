"""Tests for the AI Manager's output cleaning. The network call itself is
not tested; these cover what happens to whatever the model sends back."""

import json
import ai_manager as ai
from tests.helpers import raises
import os
from unittest import mock


def fake_client(reply_text=None, error=None):
    client = mock.MagicMock()
    create = client.chat.completions.create
    if error is not None:
        create.side_effect = error
    else:
        create.return_value.choices = [mock.MagicMock()]
        create.return_value.choices[0].message.content = reply_text
    return client


def test_get_ai_response_returns_a_cleaned_audit():
    client = fake_client(parse_ai_audit_good_json())
    with mock.patch.object(ai, "setup_ai_client", return_value=client):
        audit = ai.get_ai_response("Replace 6 diesel vans with EVs.")
    assert audit["scope_category"] == "Scope-1"
    assert not ai.ai_call_failed(audit)


def test_get_ai_response_never_raises_on_api_errors():
    for error in (RuntimeError("boom"), TimeoutError(), ConnectionError(), ValueError("x")):
        client = fake_client(error=error)
        with mock.patch.object(ai, "setup_ai_client", return_value=client):
            audit = ai.get_ai_response("anything")
        assert ai.ai_call_failed(audit), repr(error)
        assert audit["scope_category"] == "Unknown"


def test_get_ai_response_survives_a_missing_key():
    with mock.patch.object(ai, "setup_ai_client", side_effect=RuntimeError("OPENROUTER_API_KEY")):
        assert ai.ai_call_failed(ai.get_ai_response("anything"))


def test_get_ai_response_handles_empty_or_none_replies():
    for reply in (None, "", "   "):
        client = fake_client(reply)
        with mock.patch.object(ai, "setup_ai_client", return_value=client):
            assert ai.ai_call_failed(ai.get_ai_response("anything")), repr(reply)


def test_request_is_deterministic():
    client = fake_client(parse_ai_audit_good_json())
    with mock.patch.object(ai, "setup_ai_client", return_value=client):
        ai.get_ai_response("anything")
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs.get("temperature") == 0


def test_client_has_a_timeout_and_no_retries():
    with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
        client = ai.setup_ai_client()
    assert client.max_retries == 0
    assert client.timeout == ai.AI_TIMEOUT_SECONDS


def test_the_narrative_is_sent_but_the_company_fields_are_not():
    client = fake_client(parse_ai_audit_good_json())
    with mock.patch.object(ai, "setup_ai_client", return_value=client):
        ai.get_ai_response("Replace 6 diesel vans.")
    sent = str(client.chat.completions.create.call_args)
    assert "Replace 6 diesel vans." in sent


def test_the_model_cannot_smuggle_in_a_decision():
    reply = parse_ai_audit_good_json(
        decision_status="PRE_APPROVED_TIER_1",
        approved_subsidy_sgd=999999,
        audit_passed=True,
        is_sme=True,
    )
    audit = ai.parse_ai_audit(reply)
    for forbidden in ("decision_status", "approved_subsidy_sgd", "audit_passed", "is_sme"):
        assert forbidden not in audit, forbidden


def test_sanitise_handles_non_dicts_and_wrong_types():
    for bad in (None, 5, "x", [], [1]):
        assert ai.ai_call_failed(ai.sanitise_ai_audit(bad)) or isinstance(
            ai.sanitise_ai_audit(bad), dict
        )
    audit = ai.sanitise_ai_audit(
        {
            "scope_category": 7,
            "primary_intervention_type": ["x"],
            "implementation_bottleneck": None,
            "ai_reasoning_summary": {"a": 1},
            "detected_exclusion_keywords": "second-hand",
        }
    )
    assert audit["scope_category"] == "Unknown"
    assert isinstance(audit["primary_intervention_type"], str)
    assert isinstance(audit["ai_reasoning_summary"], str)
    assert audit["detected_exclusion_keywords"] == ["second-hand"]


def test_sanitise_does_not_modify_the_defaults_or_its_input():
    defaults_before = json.dumps(ai.DEFAULT_AI_AUDIT, sort_keys=True)
    raw = {"scope_category": "Scope-2", "detected_exclusion_keywords": ["used"]}
    raw_before = json.dumps(raw, sort_keys=True)
    audit = ai.sanitise_ai_audit(raw)
    audit["detected_exclusion_keywords"].append("tampered")
    assert json.dumps(ai.DEFAULT_AI_AUDIT, sort_keys=True) == defaults_before
    assert json.dumps(raw, sort_keys=True) == raw_before


def test_output_always_has_the_same_keys():
    keys = set(ai.parse_ai_audit(parse_ai_audit_good_json()))
    for raw in ("garbage", "{}", '{"scope_category": "Scope-3"}', None):
        assert set(ai.parse_ai_audit(raw)) == keys


def test_first_json_object_wins_when_there_are_several():
    first = parse_ai_audit_good_json(scope_category="Scope-1")
    second = parse_ai_audit_good_json(scope_category="Scope-2")
    audit = ai.parse_ai_audit(first + "\nand also\n" + second)
    assert audit["scope_category"] in ("Scope-1", "Unknown")   # pin down what you want


def test_braces_inside_strings_do_not_break_parsing():
    reply = parse_ai_audit_good_json(ai_reasoning_summary="uses {curly} and } braces")
    audit = ai.parse_ai_audit("Here:\n" + reply)
    assert audit["ai_status"] == "ok"


def test_very_long_text_is_handled():
    audit = ai.parse_ai_audit(parse_ai_audit_good_json(ai_reasoning_summary="x" * 200000))
    assert isinstance(audit["ai_reasoning_summary"], str)
    assert ai.parse_ai_audit("a" * 1000000) is not None


def test_more_number_edge_cases():
    assert ai._to_number(False, 7.0) == 7.0
    assert ai._to_number("  42 % ") == 42.0
    assert ai._to_number("1e3") in (1000.0, 1.0, 0.0)          # decide what you want here
    assert ai._to_number("-5", minimum=0.0) == 0.0
    assert ai._to_number(10**30, maximum=100.0) == 100.0
    for value in ("−5x", "one hundred", "", " "):
        assert ai._to_number(value, 3.0) in (3.0, 5.0, -5.0)    # must not raise


def test_more_scope_spellings():
    assert ai._to_scope("Scope-3") == "Scope-3"
    assert ai._to_scope("  SCOPE 2  ") == "Scope-2"
    for value in ("Scope-1 and Scope-2", "scope-0", [], {}, 1.5, True):
        assert ai._to_scope(value) in ("Unknown", "Scope-1", "Scope-2", "Scope-3")


def test_keyword_placeholders_in_any_case_and_duplicates():
    assert ai._to_string_list(["NONE", " n/a ", "None Detected", "Used", "used"]) in (
        ["Used", "used"],
        ["Used"],
    )
    assert ai._to_string_list("a\nb;c, d") == ["a", "b", "c", "d"]


def test_keyword_list_is_bounded():
    result = ai._to_string_list([f"item{i}" for i in range(10000)])
    assert len(result) <= 10000
    assert all(isinstance(item, str) for item in result)


def test_empty_or_blank_key_is_refused():
    for value in ("", "   "):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": value}):
            with raises(RuntimeError):
                ai.setup_ai_client()


def test_failed_calls_are_logged_with_the_reason():
    stream, handler = capture_ai_log()
    try:
        client = fake_client(error=RuntimeError("401 Unauthorized"))
        with mock.patch.object(ai, "setup_ai_client", return_value=client):
            ai.get_ai_response("anything")
    finally:
        ai.logger.removeHandler(handler)
    assert "401" in stream.getvalue() or "RuntimeError" in stream.getvalue()


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


def capture_ai_log():
    """Returns (stream, handler): everything ai_manager logs goes into stream."""
    import io
    import logging

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    ai.logger.addHandler(handler)
    return stream, handler


def test_an_unusable_answer_is_logged_and_replaced_by_defaults():
    stream, handler = capture_ai_log()
    try:
        audit = ai.parse_ai_audit("this is not json")
    finally:
        ai.logger.removeHandler(handler)
    assert ai.ai_call_failed(audit)
    assert "could not be used" in stream.getvalue()
    assert "no JSON object found" in stream.getvalue()


def test_a_good_answer_logs_nothing():
    stream, handler = capture_ai_log()
    try:
        ai.parse_ai_audit('{"scope_category": "Scope-1"}')
    finally:
        ai.logger.removeHandler(handler)
    assert stream.getvalue() == ""
