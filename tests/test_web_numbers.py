"""The web form, the edit page and the JSON API refuse the same numbers the
terminal refuses: not-a-number, infinity, values too large to be real, and
anything outside the terminal's ranges. None of them may crash the app."""

import pytest

USER = {"username": "tester", "password": "Test1234!"}
FORM = {
    "Company Name": "Apex Ltd",
    "Company Industry": "Logistics",
    "Company Total Revenue": "8450000",
    "Total Employees": "38",
    "Local Equity": "85",
    "Proposal Type": "Equipment / Energy Upgrade",
    "Sustainability Grant": "1. Energy Efficiency Grant (EEG) -Base Tier",
    "Proposal Narrative": "Electric vans",
    "Baseline Energy Expenditure": "120000",
    "Estimated Retrofit Cost": "150000",
    "Reporting Advisory Fee": "",
}
API_RECORD = {
    "Company Name": "Apex Ltd",
    "Company Industry": "Logistics",
    "Company Total Revenue": 8450000.0,
    "Total Employees": 38,
    "Local Equity": 85.0,
    "Proposal Narrative": "Electric vans",
}

BAD_FORM_VALUES = [
    ("Company Total Revenue", "nan"),
    ("Company Total Revenue", "inf"),
    ("Company Total Revenue", "1e309"),
    ("Company Total Revenue", "-1"),
    ("Company Total Revenue", "0"),
    ("Company Total Revenue", "e"),
    ("Total Employees", "1e309"),
    ("Total Employees", "1.5"),
    ("Total Employees", "0"),
    ("Total Employees", "nan"),
    ("Local Equity", "nan"),
    ("Local Equity", "0"),
    ("Local Equity", "100.5"),
    ("Baseline Energy Expenditure", "inf"),
    ("Baseline Energy Expenditure", "0"),
    ("Baseline Energy Expenditure", ""),
    ("Estimated Retrofit Cost", "-5"),
]


@pytest.fixture
def user(client):
    client.post("/register", data=USER)
    client.post("/login", data=USER)
    return client


def saved_audits(app):
    return app.extensions["data"].get_user_audits("tester")


@pytest.mark.parametrize("field, value", BAD_FORM_VALUES)
def test_the_new_audit_form_refuses_bad_numbers(app, user, field, value):
    page = user.post("/new", data={**FORM, field: value})
    assert page.status_code == 200  # the form again, with a message; no crash
    assert b'<div class="flash">' in page.data
    assert saved_audits(app) == []


def test_ordinary_number_forms_are_still_accepted(app, user):
    page = user.post(
        "/new", data={**FORM, "Company Total Revenue": "8.45e6", "Local Equity": "100"}
    )
    assert page.status_code == 302
    application = saved_audits(app)[0]["application"]
    assert application["Company Total Revenue"] == 8450000.0
    assert application["Total Employees"] == 38


def test_a_reporting_proposal_needs_no_equipment_costs(app, user):
    reporting = {
        **FORM,
        "Proposal Type": "ESG Reporting / Advisory",
        "Baseline Energy Expenditure": "",
        "Estimated Retrofit Cost": "",
        "Reporting Advisory Fee": "5000",
    }
    assert user.post("/new", data=reporting).status_code == 302
    application = saved_audits(app)[0]["application"]
    assert application["Baseline Energy Expenditure"] == 0.0
    assert application["Reporting Advisory Fee"] == 5000.0


def test_costs_a_proposal_does_not_use_are_stored_as_zero(app, user):
    user.post("/new", data={**FORM, "Reporting Advisory Fee": "999"})
    assert saved_audits(app)[0]["application"]["Reporting Advisory Fee"] == 0.0


@pytest.mark.parametrize(
    "field, value",
    [("Total Employees", "1e309"), ("Local Equity", "nan"), ("Company Total Revenue", "0")],
)
def test_the_edit_page_refuses_bad_numbers(user, field, value):
    user.post("/new", data=FORM)
    edit = {key: FORM[key] for key in FORM if key != "Proposal Type"}
    page = user.post("/records/0/edit", data={**edit, field: value})
    assert page.status_code == 200
    assert b'<div class="flash">' in page.data
    records = user.get("/records").data
    assert b"Apex Ltd" in records and b"Record updated" not in records


@pytest.mark.parametrize(
    "change",
    [
        {"Company Total Revenue": float("nan")},
        {"Company Total Revenue": float("inf")},
        {"Company Total Revenue": 0},
        {"Company Total Revenue": "8450000"},  # the API wants JSON numbers
        {"Total Employees": 1.5},
        {"Total Employees": True},
        {"Local Equity": float("nan")},
        {"Local Equity": 0},
        {"Baseline Energy Expenditure": float("inf")},
        {"Reporting Advisory Fee": -1},
        {"Company Name": "x" * 101},
    ],
)
def test_the_api_refuses_bad_numbers(app, client, change):
    client.post("/api/register", json=USER)
    client.post("/api/login", json=USER)
    response = client.post("/api/audits", json={**API_RECORD, **change})
    assert response.status_code == 400, response.json
    assert saved_audits(app) == []


def test_the_api_still_accepts_a_record_without_costs(app, client):
    client.post("/api/register", json=USER)
    client.post("/api/login", json=USER)
    assert client.post("/api/audits", json=API_RECORD).status_code == 201
