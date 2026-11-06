import pytest
import re

FORM = {
    "Company Name": "DBS Coy", "Company Industry": "Finance",
    "Company Total Revenue": "23900", "Total Employees": "11", "Local Equity": "77",
    "Proposal Type": "ESG Reporting / Advisory",
    "Sustainability Grant": "1. Energy Efficiency Grant (EEG) -Base Tier",
    "Proposal Narrative": "We want to cut energy use.",
    "Baseline Energy Expenditure": "", "Estimated Retrofit Cost": "",
    "Reporting Advisory Fee": "1",
}
USER = {"username": "tester", "password": "Test1234!"}


@pytest.fixture
def page_client(client):
    client.post("/register", data=USER)
    client.post("/login", data=USER)
    return client


def test_pages_require_login(client):
    for path in ("/new", "/history", "/history/1"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_register_then_login(client):
    page = client.post("/register", data=USER, follow_redirects=True)
    assert b"Account created" in page.data
    page = client.post("/login", data=USER, follow_redirects=True)
    assert b"Past audits" in page.data


def test_login_wrong_password(client):
    client.post("/register", data=USER)
    page = client.post("/login", data={**USER, "password": "bad"})
    assert b"Invalid username or password" in page.data


def test_register_rejects_unsafe_username(client):
    page = client.post("/register", data={"username": "../x", "password": "a"})
    assert b"Username must be" in page.data


def test_new_audit_via_form(page_client):
    page = page_client.post("/new", data=FORM, follow_redirects=True)
    flashes = re.findall(rb'<div class="flash">(.*?)</div>', page.data)
    assert b"Audit #1" in page.data, flashes


def test_new_audit_bad_number_keeps_values(page_client):
    page = page_client.post("/new", data={**FORM, "Total Employees": "many"})
    assert b"must be numbers" in page.data
    assert b"DBS Coy" in page.data


def test_narrative_is_escaped(page_client):
    evil = {**FORM, "Proposal Narrative": "<script>alert(1)</script>"}
    page = page_client.post("/new", data=evil, follow_redirects=True)
    assert b"<script>alert(1)</script>" not in page.data


def test_unknown_audit_is_404(page_client):
    assert page_client.get("/history/99").status_code == 404


def test_logout(page_client):
    page_client.post("/logout")
    assert page_client.get("/history").status_code == 302

def test_industry_others_uses_specified_text(page_client):
    form = {**FORM, "Company Industry": "Others", "Industry Other": "Maritime"}
    page = page_client.post("/new", data=form, follow_redirects=True)
    assert b"Maritime" in page.data


def test_industry_others_requires_text(page_client):
    form = {**FORM, "Company Industry": "Others", "Industry Other": ""}
    page = page_client.post("/new", data=form)
    assert b"Company Industry is required" in page.data

def test_grant_others_uses_specified_text(page_client):
    form = {**FORM, "Sustainability Grant": "5. Others", "Grant Other": "Green Fund"}
    page = page_client.post("/new", data=form, follow_redirects=True)
    assert b"Green Fund" in page.data


def test_grant_others_requires_text(page_client):
    form = {**FORM, "Sustainability Grant": "5. Others", "Grant Other": ""}
    page = page_client.post("/new", data=form)
    assert b"Please specify a valid grant name" in page.data


def test_grant_others_rejects_digits(page_client):
    form = {**FORM, "Sustainability Grant": "5. Others", "Grant Other": "Fund 123"}
    page = page_client.post("/new", data=form)
    assert b"Please specify a valid grant name" in page.data