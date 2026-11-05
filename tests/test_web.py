import pytest

CREDS = {"username": "tester", "password": "Test1234!"}
OTHER = {"username": "other", "password": "Test1234!"}

APPLICATION = {
    "Company Name": "DBS Coy",
    "Company Industry": "Finance",
    "Company Total Revenue": 23900.0,
    "Total Employees": 11,
    "Local Equity": 77.0,
    "Proposal Type": "ESG Reporting / Advisory",
    "Sustainability Grant": "1. Energy Efficiency Grant (EEG) -Base Tier",
    "Proposal Narrative": "We want to cut energy use.",
    "Baseline Energy Expenditure": 0.0,
    "Estimated Retrofit Cost": 0.0,
    "Reporting Advisory Fee": 1.0,
}


@pytest.fixture
def logged_in(client):
    client.post("/api/register", json=CREDS)
    client.post("/api/login", json=CREDS)
    return client


def test_create_audit_requires_login(client):
    assert client.post("/api/audits", json=APPLICATION).status_code == 401


def test_create_audit_success(logged_in):
    response = logged_in.post("/api/audits", json=APPLICATION)
    assert response.status_code == 201
    audit = response.json["audit"]
    assert audit["audit_id"] == 1
    assert audit["result"]["decision_status"] == "Approved"


def test_created_audit_appears_in_history(logged_in):
    logged_in.post("/api/audits", json=APPLICATION)
    history = logged_in.get("/api/audits").json
    assert len(history) == 1
    assert history[0]["application"]["Company Name"] == "DBS Coy"


def test_audit_ids_increment(logged_in):
    logged_in.post("/api/audits", json=APPLICATION)
    second = logged_in.post("/api/audits", json=APPLICATION)
    assert second.json["audit"]["audit_id"] == 2


@pytest.mark.parametrize(
    "change",
    [
        {"Company Name": ""},
        {"Proposal Narrative": None},
        {"Company Total Revenue": -1},
        {"Total Employees": "many"},
        {"Local Equity": 150},
    ],
)
def test_create_audit_rejects_bad_input(logged_in, change):
    response = logged_in.post("/api/audits", json={**APPLICATION, **change})
    assert response.status_code == 400


def test_create_audit_rejects_non_json(logged_in):
    assert logged_in.post("/api/audits", data="nope").status_code == 400


def test_ai_failure_returns_502(app, logged_in):
    app.extensions["ai"].ai_call_failed = lambda audit: True
    assert logged_in.post("/api/audits", json=APPLICATION).status_code == 502
    assert logged_in.get("/api/audits").json == []   # nothing saved


def test_get_single_audit(logged_in):
    logged_in.post("/api/audits", json=APPLICATION)
    assert logged_in.get("/api/audits/1").status_code == 200
    assert logged_in.get("/api/audits/99").status_code == 404


def test_users_cannot_see_each_others_audits(app):
    a, b = app.test_client(), app.test_client()
    a.post("/api/register", json=CREDS)
    a.post("/api/login", json=CREDS)
    a.post("/api/audits", json=APPLICATION)

    b.post("/api/register", json=OTHER)
    b.post("/api/login", json=OTHER)
    assert b.get("/api/audits").json == []
    assert b.get("/api/audits/1").status_code == 404

def test_index_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")