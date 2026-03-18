"""Live tests for Companies House client — requires API key."""

import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

import pytest

from property_core.companies_house_client import CompaniesHouseClient
from property_core.models.companies_house import CompanyRecord, CompanySearchResult


@pytest.fixture(autouse=True)
def _skip_unless_live():
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("RUN_LIVE_TESTS not set")


@pytest.fixture()
def client():
    c = CompaniesHouseClient()
    if not c.is_configured():
        pytest.skip("COMPANIES_HOUSE_API_KEY not set")
    # Verify the key is actually valid (401 = invalid key)
    probe = c.search("test", items_per_page=1)
    if probe.total_results == 0 and len(probe.companies) == 0:
        pytest.skip("COMPANIES_HOUSE_API_KEY appears invalid (got empty probe result)")
    return c


def test_search(client):
    result = client.search("Tesco")
    assert isinstance(result, CompanySearchResult)
    assert result.total_results > 0
    assert len(result.companies) > 0
    assert result.companies[0].company_name is not None


def test_get_company(client):
    """Tesco PLC = 00445790."""
    record = client.get_company("00445790")
    assert record is not None
    assert isinstance(record, CompanyRecord)
    assert record.company_name is not None
    assert record.company_status == "active"
    assert record.raw is not None


def test_get_company_not_found(client):
    result = client.get_company("99999999")
    assert result is None


def test_lookup_by_number(client):
    result = client.lookup("00445790")
    assert isinstance(result, CompanyRecord)
    assert result.company_number == "00445790"


def test_lookup_by_name(client):
    result = client.lookup("Tesco")
    assert isinstance(result, CompanySearchResult)
    assert result.total_results > 0
