"""Tests that exercise the object-oriented design itself: polymorphism,
substitution, extension without modification, and how the parts are wired
(association, aggregation, composition)."""

import pytest

from managers.ai.ai_manager import AIClient, AIManager
from managers.data_manager import DataManager
from managers.io_manager import IOManager
from managers.logic_manager import (
    Case,
    DecisionAdjuster,
    DecisionEngine,
    EegAdvancedScheme,
    EegBaseScheme,
    EligibilityRule,
    EspScheme,
    GrantScheme,
    LogicManager,
    LowImpactRule,
    SrgScheme,
)
from main import Application, Session
from models import (
    EQUIPMENT_PROPOSAL,
    REPORTING_PROPOSAL,
    ApplicationRecord,
    EquipmentProposal,
    PlaceholderKeywords,
    Proposal,
    RecordSections,
    ReportingProposal,
)
from report_exporter import ReportExporter
from tests.helpers import temp_data_dir


def make_case(**changes):
    values = dict(
        annual_revenue=1_000_000.0,
        headcount=10,
        local_equity=60.0,
        is_sme=True,
        scope="Scope-1",
        energy_reduction_pct=5.0,
        baseline_spend=50_000.0,
    )
    values.update(changes)
    return Case(**values)


# ----- Open/Closed + Polymorphism: a new rule needs no engine change -----------
class AlwaysApprove(EligibilityRule):
    def evaluate(self, case):
        return self.make_decision("PRE_APPROVED_TIER_1", subsidy=1.0)


class NeverApplies(EligibilityRule):
    def evaluate(self, case):
        return None


def test_a_new_rule_plugs_into_the_engine_without_editing_it():
    engine = DecisionEngine([NeverApplies(), AlwaysApprove(), LowImpactRule()])
    assert engine.decide(make_case())["decision_status"] == "PRE_APPROVED_TIER_1"


def test_the_first_matching_rule_wins():
    engine = DecisionEngine([AlwaysApprove(), LowImpactRule()])
    assert engine.decide(make_case())["approved_subsidy_sgd"] == 1.0


def test_an_engine_without_a_catch_all_says_so():
    with pytest.raises(LookupError):
        DecisionEngine([NeverApplies()]).decide(make_case())


def test_a_custom_engine_can_be_given_to_the_logic_manager():
    manager = LogicManager(engine=DecisionEngine([AlwaysApprove()]))
    result = manager.evaluate_grant_application({}, {})
    assert result["decision_status"] == "PRE_APPROVED_TIER_1"
    assert result["audit_passed"] is True


class AppendNote(DecisionAdjuster):
    def adjust(self, decision, case):
        decision["recommendations"].append("checked")


def test_adjusters_run_after_the_rule_is_chosen():
    engine = DecisionEngine([LowImpactRule()], adjusters=[AppendNote()])
    assert engine.decide(make_case())["recommendations"][-1] == "checked"


# ----- Liskov: every rule can stand in for the base type ----------------------
def test_every_default_rule_honours_the_rule_contract():
    case = make_case()
    for rule in DecisionEngine.with_default_rules().rules:
        result = rule.evaluate(case)
        assert result is None or {
            "decision_status",
            "reasons",
            "recommendations",
            "matched_schemes",
            "approved_subsidy_sgd",
        } == set(result), type(rule).__name__


def test_every_scheme_can_be_used_through_the_base_type():
    for scheme in (EegAdvancedScheme(), EegBaseScheme(), EspScheme(), SrgScheme()):
        assert isinstance(scheme, GrantScheme)
        assert 0 < scheme.rate <= 1
        assert 0 <= scheme.calculate_subsidy(10**9) <= scheme.cap
        assert scheme.calculate_subsidy(0) == 0.0


def test_scheme_numbers_match_the_funding_table():
    assert (EegAdvancedScheme.rate, EegAdvancedScheme.cap) == (0.70, 350_000.0)
    assert (EegBaseScheme.rate, EegBaseScheme.cap) == (0.70, 30_000.0)
    assert (EspScheme.rate, EspScheme.cap) == (0.50, 20_000.0)
    assert (SrgScheme.rate, SrgScheme.cap) == (0.30, 150_000.0)


# ----- Proposal hierarchy: polymorphism instead of type-name branching --------
class FakePrompts:
    def __init__(self):
        self.asked = []

    def retrieve_baseline_energy_expenditure(self):
        self.asked.append("baseline")
        return 100.0

    def retrieve_estimated_retrofit_cost(self):
        self.asked.append("retrofit")
        return 200.0

    def retrieve_reporting_advisory_fee(self):
        self.asked.append("fee")
        return 300.0


def test_each_proposal_kind_asks_only_for_its_own_details():
    prompts = FakePrompts()
    equipment = EquipmentProposal().collect_details(prompts)
    assert prompts.asked == ["baseline", "retrofit"]
    assert equipment == {
        "Baseline Energy Expenditure": 100.0,
        "Estimated Retrofit Cost": 200.0,
        "Reporting Advisory Fee": 0.0,
    }
    prompts = FakePrompts()
    reporting = ReportingProposal().collect_details(prompts)
    assert prompts.asked == ["fee"]
    assert reporting["Reporting Advisory Fee"] == 300.0
    assert reporting["Baseline Energy Expenditure"] == 0.0


def test_proposal_factory_picks_the_right_kind():
    assert isinstance(Proposal.for_type(REPORTING_PROPOSAL), ReportingProposal)
    assert isinstance(Proposal.for_type(EQUIPMENT_PROPOSAL), EquipmentProposal)
    assert isinstance(Proposal.for_type(None), EquipmentProposal)
    assert Proposal.for_type(REPORTING_PROPOSAL).type_name == REPORTING_PROPOSAL


def test_editable_fields_follow_the_proposal_kind():
    assert "Reporting Advisory Fee" in ReportingProposal().editable_fields
    assert "Reporting Advisory Fee" not in EquipmentProposal().editable_fields
    assert "Company Name" in EquipmentProposal().editable_fields


# ----- ApplicationRecord adapter and shared helpers ---------------------------
def test_application_record_reads_both_layouts_without_changing_them():
    nested = {"company_profile": {"company_name": "N"}, "proposal": {}}
    before = repr(nested)
    assert ApplicationRecord(nested).company_name == "N"
    assert repr(nested) == before
    assert ApplicationRecord({}).company_name == "N/A"
    assert ApplicationRecord(None).flat == {}
    assert ApplicationRecord({"Proposal Narrative": "x"}).narrative == "x"


def test_application_record_knows_its_proposal_kind():
    record = ApplicationRecord({"Proposal Type": REPORTING_PROPOSAL})
    assert isinstance(record.proposal, ReportingProposal)


def test_placeholder_keywords_are_shared_by_both_managers():
    for word in ("none", " N/A ", "None detected.", "none found"):
        assert PlaceholderKeywords.matches(word)
    assert not PlaceholderKeywords.matches("second-hand")


def test_record_sections_are_always_dicts():
    assert RecordSections.get(None, "x") == {}
    assert RecordSections.get({"x": 5}, "x") == {}
    assert RecordSections.get({"x": {"a": 1}}, "x") == {"a": 1}


# ----- Aggregation / composition / association --------------------------------
def test_application_uses_the_managers_it_is_given():
    io, ai, logic, data = IOManager(), AIManager(), LogicManager(), DataManager()
    app = Application(io=io, ai=ai, logic=logic, data=data)
    assert (app.io, app.ai, app.logic, app.data) == (io, ai, logic, data)


def test_application_builds_defaults_when_none_are_given():
    app = Application()
    assert isinstance(app.io, IOManager)
    assert isinstance(app.ai, AIManager)
    assert isinstance(app.logic, LogicManager)
    assert isinstance(app.data, DataManager)


def test_a_session_owns_its_own_records():
    first, second = Session("a"), Session("b")
    first.records.append({"Company Name": "A"})
    assert second.records == []
    assert first.jsonfile_name == "" and first.ai_audit == {}


def test_each_logic_manager_owns_its_own_helpers():
    assert LogicManager()._hasher is not LogicManager()._hasher


class ScriptedAI(AIClient):
    def complete(self, system_prompt, user_message):
        return (
            '{"scope_category": "Scope-1", "estimated_energy_reduction_pct": 25,'
            ' "detected_exclusion_keywords": []}'
        )


def test_the_whole_pipeline_runs_with_a_fake_ai_and_no_network():
    """AI Manager -> Logic Manager through the controller's own run_audit."""
    app = Application(
        io=IOManager(), ai=AIManager(ScriptedAI()), logic=LogicManager(), data=DataManager()
    )
    record = {
        "Company Name": "Apex",
        "Company Total Revenue": 1_000_000.0,
        "Total Employees": 10,
        "Local Equity": 80.0,
        "Proposal Type": EQUIPMENT_PROPOSAL,
        "Proposal Narrative": "Swap diesel vans for EVs.",
        "Baseline Energy Expenditure": 40_000.0,
        "Estimated Retrofit Cost": 500_000.0,
    }
    from unittest import mock

    with (
        mock.patch.object(app.io, "display_ai_audit"),
        mock.patch.object(app.io, "display_grant_decision"),
        mock.patch.object(app.io, "run_ai_analysis_bar"),
    ):
        ai_audit, result = app.run_audit(record)
    assert ai_audit["ai_status"] == "ok"
    assert result["decision_status"] == "PRE_APPROVED_TIER_1"
    assert result["approved_subsidy_sgd"] == 28_000.0


# ----- Interface: the Data Manager works with any ReportExporter --------------
class RecordingExporter(ReportExporter):
    def __init__(self, available=True):
        self.available = available
        self.exported = []

    def is_available(self):
        return self.available

    def export(self, records, output_path):
        self.exported.append((records, output_path))
        with open(output_path, "w") as file:
            file.write("fake pdf")


def test_data_manager_exports_through_any_report_exporter():
    with temp_data_dir() as (_, folder):
        exporter = RecordingExporter()
        manager = DataManager(data_dir=folder, exporter=exporter)
        name, status = manager.export_records_to_pdf([{"a": 1}], "mine.json")
        assert (name, status) == ("mine.pdf", "exported")
        assert exporter.exported[0][0] == [{"a": 1}]


def test_missing_exporter_dependency_is_reported_not_raised():
    with temp_data_dir() as (_, folder):
        manager = DataManager(data_dir=folder, exporter=RecordingExporter(False))
        assert manager.export_records_to_pdf([], "x.json") == (
            None,
            "missing_dependency",
        )


class BrokenExporter(RecordingExporter):
    def export(self, records, output_path):
        raise OSError("disk full")


def test_a_failing_exporter_gives_pdf_error():
    with temp_data_dir() as (_, folder):
        manager = DataManager(data_dir=folder, exporter=BrokenExporter())
        assert manager.export_records_to_pdf([], "x.json") == (None, "pdf_error")


# ----- Encapsulation: the active user is a validated property ------------------
def test_active_user_is_validated_by_its_setter():
    manager = DataManager(data_dir="unused")
    manager.active_user = "alice"
    assert manager.active_user == "alice"
    for bad in ("../x", "A b", "", 5):
        with pytest.raises(ValueError):
            manager.active_user = bad
    assert manager.active_user == "alice"
    manager.active_user = None
    assert manager.active_user is None
