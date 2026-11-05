import pytest

USER = {"username": "tester", "password": "Test1234!"}
OTHER = {"username": "other", "password": "Test1234!"}
FORM = {
    "Company Name": "DBS Coy", "Company Industry": "Finance",
    "Company Total Revenue": "23900", "Total Employees": "11", "Local Equity": "77",
    "Proposal Type": "ESG Reporting / Advisory",
    "Sustainability Grant": "1. Energy Efficiency Grant (EEG) -Base Tier",
    "Proposal Narrative": "We want to cut energy use.",
    "Baseline Energy Expenditure": "", "Estimated Retrofit Cost": "",
    "Reporting Advisory Fee": "1",
}


class FakeExporter:
    available = True

    def is_available(self):
        return self.available

    def export(self, records, path):
        with open(path, "wb") as file:
            file.write(b"%PDF-fake")


@pytest.fixture
def pdf_client(app):
    app.extensions["exporter"] = FakeExporter()
    client = app.test_client()
    client.post("/register", data=USER)
    client.post("/login", data=USER)
    client.post("/new", data=FORM)
    return client


def test_pdf_download(pdf_client):
    response = pdf_client.get("/history/1/pdf")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert "attachment" in response.headers["Content-Disposition"]


def test_pdf_unknown_audit_is_404(pdf_client):
    assert pdf_client.get("/history/99/pdf").status_code == 404


def test_pdf_requires_login(client):
    assert client.get("/history/1/pdf").status_code == 302


def test_pdf_missing_dependency_shows_message(app, pdf_client):
    app.extensions["exporter"].available = False
    page = pdf_client.get("/history/1/pdf", follow_redirects=True)
    assert b"needs ReportLab" in page.data


def test_pdf_of_another_users_audit_is_404(app, pdf_client):
    other = app.test_client()
    other.post("/register", data=OTHER)
    other.post("/login", data=OTHER)
    assert other.get("/history/1/pdf").status_code == 404