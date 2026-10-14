import pytest


@pytest.fixture
def mock_company_data():
    # This fixture is now instantly available to all test files
    return {"local_shareholding": 35.0, "annual_revenue": 50_000_000, "headcount": 150}
