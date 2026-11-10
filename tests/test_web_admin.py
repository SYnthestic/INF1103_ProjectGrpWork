"""The web pages and API respect the admin feature: the ADMIN_USERNAME name
cannot be registered there, and web decisions use the thresholds an
administrator saved."""

import logging

from managers.logic_manager import LogicManager, RuleConfig
from web.service import AuditService

ADMIN = {"username": "boss", "password": "Test1234!"}


def use_admin_name(app):
    """Gives the web app a real Logic Manager whose ADMIN_USERNAME is 'boss'."""
    app.extensions["logic"] = LogicManager(admin_username="boss")


def test_the_api_refuses_to_register_the_admin_name(app, client):
    use_admin_name(app)
    assert client.post("/api/register", json=ADMIN).status_code == 409
    assert app.extensions["data"].get_user("boss") is None


def test_the_register_page_refuses_the_admin_name(app, client):
    use_admin_name(app)
    page = client.post("/register", data=ADMIN)
    assert b"That username is taken" in page.data
    assert app.extensions["data"].get_user("boss") is None


def test_web_decisions_use_the_saved_thresholds(app):
    data = app.extensions["data"]
    logic = LogicManager(admin_username="")
    data.save_rule_config(
        dict(RuleConfig().to_dict(), provisional_min_pct=12.0), changed_by="boss"
    )
    AuditService(None, logic, data, logging.getLogger()).use_saved_rules()
    assert logic.rule_config.provisional_min_pct == 12.0


def test_unusable_saved_thresholds_fall_back_to_the_defaults(app):
    data = app.extensions["data"]
    logic = LogicManager(rule_config=RuleConfig().with_value("provisional_min_pct", 12))
    data.save_rule_config({"minimum_impact_pct": "ten"}, changed_by="boss")
    AuditService(None, logic, data, logging.getLogger()).use_saved_rules()
    assert logic.rule_config == RuleConfig()


def test_web_audits_record_the_thresholds_used(app, client):
    app.extensions["data"].save_rule_config(
        dict(RuleConfig().to_dict(), provisional_min_pct=12.0), changed_by="boss"
    )
    client.post("/api/register", json={"username": "tester", "password": "Test1234!"})
    client.post("/api/login", json={"username": "tester", "password": "Test1234!"})
    record = {
        "Company Name": "Acme",
        "Company Industry": "Retail",
        "Company Total Revenue": 1000.0,
        "Total Employees": 5,
        "Local Equity": 80.0,
        "Proposal Narrative": "LED lighting upgrade.",
    }
    response = client.post("/api/audits", json=record)
    assert response.status_code == 201
    assert response.json["audit"]["rules_used"]["provisional_min_pct"] == 12.0
