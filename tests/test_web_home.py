"""The home page (linked from the logo) lists the grants the auditor checks,
with figures taken from the grant classes and the thresholds in use."""

from managers.logic_manager import (
    EegAdvancedScheme,
    EegBaseScheme,
    EspScheme,
    RuleConfig,
    SrgScheme,
)
from web import display

USER = {"username": "tester", "password": "Test1234!"}


def test_the_logo_links_to_the_home_page(client):
    page = client.get("/login").data
    assert b'class="brand" href="/"' in page


def test_the_home_page_lists_every_grant_with_its_rate_and_cap(client):
    page = client.get("/").data.decode()
    for scheme, rate, cap in (
        (EegAdvancedScheme(), "70%", "SGD 350,000.00"),
        (EegBaseScheme(), "70%", "SGD 30,000.00"),
        (EspScheme(), "50%", "SGD 20,000.00"),
        (SrgScheme(), "30%", "SGD 150,000.00"),
    ):
        assert scheme.name in page
        assert rate in page and cap in page


def test_the_home_page_shows_who_can_apply(client):
    page = client.get("/").data
    assert b"Who can apply" in page
    assert b"at least 30% local shareholding" in page
    assert b"SGD 100,000,000.00" in page


def test_the_conditions_follow_the_saved_thresholds(app, client):
    page = client.get("/").data
    assert b"Energy reduction of at least 15%" in page
    app.extensions["data"].save_rule_config(
        dict(RuleConfig().to_dict(), provisional_min_pct=12.0), changed_by="boss"
    )
    page = client.get("/").data
    assert b"Energy reduction of at least 12%" in page
    assert b"Energy reduction of at least 15%" not in page


def test_visitors_are_invited_to_log_in_and_users_to_start_an_audit(client):
    assert b"Log in to start an audit" in client.get("/").data
    client.post("/register", data=USER)
    client.post("/login", data=USER)
    page = client.get("/").data
    assert b"Start a new audit" in page and b"Log in to start an audit" not in page


def test_grant_cards_are_built_from_the_scheme_classes():
    cards = display.grant_cards(RuleConfig().with_value("eeg_advanced_min_tonnes", 500))
    assert [c["name"] for c in cards] == [
        EegAdvancedScheme.name,
        EegBaseScheme.name,
        EspScheme.name,
        SrgScheme.name,
    ]
    assert "above 500 tonnes" in cards[0]["conditions"][0]
