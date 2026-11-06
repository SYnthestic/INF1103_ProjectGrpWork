import os

import pytest

FORM = {
    "Company Name": "DBS Coy", "Company Industry": "Finance",
    "Company Total Revenue": "23900", "Total Employees": "11", "Local Equity": "77",
    "Proposal Type": "ESG Reporting / Advisory",
    "Sustainability Grant": "1. Energy Efficiency Grant (EEG) -Base Tier",
    "Proposal Narrative": "We want to cut energy use.",
    "Baseline Energy Expenditure": "", "Estimated Retrofit Cost": "",
    "Reporting Advisory Fee": "1",
}
EDIT = {
    "Company Name": "New Name Ltd", "Company Industry": "Finance",
    "Sustainability Grant": "1. Energy Efficiency Grant (EEG) -Base Tier",
    "Proposal Narrative": "We want to cut energy use.",
    "Company Total Revenue": "23900", "Total Employees": "11", "Local Equity": "77",
    "Baseline Energy Expenditure": "0", "Estimated Retrofit Cost": "0",
    "Reporting Advisory Fee": "1",
}
USER = {"username": "tester", "password": "Test1234!"}


@pytest.fixture
def pc(client):
    """Logged-in client that already has one record in memory."""
    client.post("/register", data=USER)
    client.post("/login", data=USER)
    client.post("/new", data=FORM)
    return client


def test_records_require_login(client):
    assert client.get("/records").status_code == 302


def test_new_audit_adds_record_to_memory(pc):
    page = pc.get("/records")
    assert b"DBS Coy" in page.data and b"unsaved changes" in page.data


def test_update_record(pc):
    page = pc.post("/records/0/edit", data=EDIT, follow_redirects=True)
    assert b"Record updated" in page.data and b"New Name Ltd" in page.data


def test_update_rejects_bad_number(pc):
    page = pc.post("/records/0/edit", data={**EDIT, "Local Equity": "150"})
    assert b"Local Equity must be between 0 and 100" in page.data


def test_update_unknown_record_is_404(pc):
    assert pc.get("/records/9/edit").status_code == 404


def test_delete_record(pc):
    page = pc.post("/records/0/delete", follow_redirects=True)
    assert b"Record deleted" in page.data
    assert b"No records in memory" in page.data


def test_save_creates_file_and_clears_unsaved(app, pc):
    page = pc.post("/records/save", data={"filename": "mine"}, follow_redirects=True)
    assert b"Records saved to mine.json" in page.data
    assert b"unsaved changes" not in page.data
    folder = os.path.join(app.config["DATA_DIR"], "records", "tester")
    assert os.path.isfile(os.path.join(folder, "mine.json"))


def test_save_blank_cancels(app, pc):
    page = pc.post("/records/save", data={"filename": ""}, follow_redirects=True)
    assert b"Save cancelled" in page.data
    assert b"DBS Coy" in page.data                       # still in memory
    assert not os.path.exists(os.path.join(app.config["DATA_DIR"], "records"))


def test_save_rejects_illegal_name(pc):
    page = pc.post("/records/save", data={"filename": "a/b"})
    assert b"illegal characters" in page.data


def test_save_existing_file_asks(pc):
    pc.post("/records/save", data={"filename": "a"})
    pc.post("/records/save", data={"filename": "b"})     # current file is now b
    page = pc.post("/records/save", data={"filename": "a"})
    assert b"already exists" in page.data


def test_load_needs_confirmation_then_loads(pc):
    pc.post("/records/save", data={"filename": "mine"})
    pc.post("/records/0/delete")
    page = pc.post("/records/load", data={"filename": "mine.json"})
    assert b"Tick the box" in page.data
    page = pc.post("/records/load", data={"filename": "mine.json", "confirm": "1"},
                   follow_redirects=True)
    assert b"loaded successfully" in page.data and b"DBS Coy" in page.data


def test_load_blank_cancels(pc):
    page = pc.post("/records/load", data={"filename": ""}, follow_redirects=True)
    assert b"Load cancelled" in page.data


def test_run_ai_and_logic(pc):
    assert b"AI audit" in pc.post("/records/ai").data
    assert b"Approved" in pc.post("/records/logic").data


def test_logic_needs_ai_audit_first(pc):
    pc.post("/records/save", data={"filename": "mine"})
    pc.post("/records/load", data={"filename": "mine.json", "confirm": "1"})
    page = pc.post("/records/logic", follow_redirects=True)
    assert b"Run the AI Manager first" in page.data


def test_logout_warns_about_unsaved_records(pc):
    assert b"unsaved records" in pc.post("/logout").data
    assert pc.get("/history").status_code == 200         # still logged in
    assert pc.post("/logout", data={"force": "1"}).status_code == 302
    assert pc.get("/history").status_code == 302