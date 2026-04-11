"""Unit tests for property_app.tools — plain MCP tool wrappers."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# stamp_duty
# ---------------------------------------------------------------------------


def test_calc_stamp_duty_basic():
    """calc_stamp_duty returns dict with total_sdlt and effective_rate."""
    from property_app.tools import calc_stamp_duty

    result = calc_stamp_duty(price=300000)
    assert isinstance(result, dict)
    assert "total_sdlt" in result
    assert "effective_rate" in result
    assert result["price"] == 300000
    assert result["total_sdlt"] > 0
    assert result["effective_rate"] > 0


def test_calc_stamp_duty_zero_price():
    """calc_stamp_duty with 0 price returns zero SDLT."""
    from property_app.tools import calc_stamp_duty

    result = calc_stamp_duty(price=0)
    assert result["total_sdlt"] == 0
    assert result["effective_rate"] == 0


def test_calc_stamp_duty_additional_property():
    """Additional property surcharge increases SDLT."""
    from property_app.tools import calc_stamp_duty

    with_surcharge = calc_stamp_duty(price=300000, additional_property=True)
    without_surcharge = calc_stamp_duty(price=300000, additional_property=False)
    assert with_surcharge["total_sdlt"] > without_surcharge["total_sdlt"]


def test_calc_stamp_duty_has_breakdown():
    """calc_stamp_duty returns breakdown bands."""
    from property_app.tools import calc_stamp_duty

    result = calc_stamp_duty(price=300000)
    assert "breakdown" in result
    assert len(result["breakdown"]) > 0
    band = result["breakdown"][0]
    assert "band" in band
    assert "rate" in band
    assert "tax" in band


# ---------------------------------------------------------------------------
# planning_search
# ---------------------------------------------------------------------------


def test_search_planning_returns_council_found():
    """search_planning returns dict with council_found key."""
    from property_app.tools import search_planning

    with patch("property_core.planning_service.PostcodeClient") as mock_pc:
        mock_pc.return_value.get_local_authority.return_value = {
            "name": "Westminster",
            "code": "E09000033",
            "region": "London",
            "country": "England",
            "postcode": "SW1A 1AA",
        }

        result = search_planning(postcode="SW1A 1AA")
        assert isinstance(result, dict)
        assert "council_found" in result


def test_search_planning_postcode_not_found():
    """search_planning returns council_found=False when postcode unknown."""
    from property_app.tools import search_planning

    with patch("property_core.planning_service.PostcodeClient") as mock_pc:
        mock_pc.return_value.get_local_authority.return_value = None

        result = search_planning(postcode="ZZ99 9ZZ")
        assert result["council_found"] is False


# ---------------------------------------------------------------------------
# company_search
# ---------------------------------------------------------------------------


def test_search_company_by_name():
    """search_company with text query calls client.search()."""
    from property_app.tools import search_company

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "query": "Tesco",
        "total_results": 1,
        "companies": [],
    }

    with patch("property_core.CompaniesHouseClient") as mock_cls:
        mock_cls.return_value.search.return_value = mock_result
        result = search_company("Tesco")
        assert isinstance(result, dict)
        assert result["query"] == "Tesco"
        mock_cls.return_value.search.assert_called_once_with("Tesco")


def test_search_company_by_number():
    """search_company with numeric query calls client.lookup()."""
    from property_app.tools import search_company

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "company_number": "00445790",
        "company_name": "Tesco PLC",
    }

    with patch("property_core.CompaniesHouseClient") as mock_cls:
        mock_cls.return_value.lookup.return_value = mock_result
        result = search_company("00445790")
        assert isinstance(result, dict)
        assert result["company_number"] == "00445790"
        mock_cls.return_value.lookup.assert_called_once_with("00445790")


def test_search_company_not_found():
    """search_company returns error dict when lookup returns None."""
    from property_app.tools import search_company

    with patch("property_core.CompaniesHouseClient") as mock_cls:
        mock_cls.return_value.lookup.return_value = None
        result = search_company("99999999")
        assert result == {"error": "Not found"}


def test_search_company_not_configured():
    """search_company returns result even if API key missing (empty results)."""
    from property_app.tools import search_company

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {"query": "test", "total_results": 0, "companies": []}

    with patch("property_core.CompaniesHouseClient") as mock_cls:
        mock_cls.return_value.search.return_value = mock_result
        result = search_company("test company")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# epc_lookup
# ---------------------------------------------------------------------------


def test_lookup_epc_no_data():
    """lookup_epc returns error dict when no EPC data found."""
    from property_app.tools import lookup_epc

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_by_postcode = AsyncMock(return_value=None)
        result = asyncio.run(lookup_epc("ZZ99 9ZZ"))
        assert result == {"error": "No EPC data"}


def test_lookup_epc_with_result():
    """lookup_epc returns dict when EPC data found."""
    from property_app.tools import lookup_epc

    mock_epc = MagicMock()
    mock_epc.model_dump.return_value = {
        "address": "1 TEST STREET",
        "postcode": "SW1A 1AA",
        "current_rating": "C",
    }

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_by_postcode = AsyncMock(return_value=mock_epc)
        result = asyncio.run(lookup_epc("SW1A 1AA"))
        assert isinstance(result, dict)
        assert result["current_rating"] == "C"


# ---------------------------------------------------------------------------
# rightmove_search
# ---------------------------------------------------------------------------


def test_search_rightmove_returns_structure():
    """search_rightmove returns dict with search_url, count, listings, median_price."""
    from property_app.tools import search_rightmove

    mock_listing = MagicMock()
    mock_listing.price = 250000
    mock_listing.model_dump.return_value = {
        "id": "12345",
        "price": 250000,
        "address": "1 Test St",
    }

    with patch("property_core.RightmoveLocationAPI") as mock_loc, \
         patch("property_core.fetch_listings") as mock_fetch:
        mock_loc.return_value.build_search_url.return_value = (
            "https://rightmove.co.uk/search?test=1"
        )
        mock_fetch.return_value = [mock_listing]

        result = search_rightmove("SW1A 1AA")
        assert isinstance(result, dict)
        assert "search_url" in result
        assert "count" in result
        assert result["count"] == 1
        assert "listings" in result
        assert "median_price" in result
        assert result["median_price"] == 250000


def test_search_rightmove_empty_results():
    """search_rightmove with no results returns count=0 and median_price=None."""
    from property_app.tools import search_rightmove

    with patch("property_core.RightmoveLocationAPI") as mock_loc, \
         patch("property_core.fetch_listings") as mock_fetch:
        mock_loc.return_value.build_search_url.return_value = (
            "https://rightmove.co.uk/search?test=1"
        )
        mock_fetch.return_value = []

        result = search_rightmove("SW1A 1AA")
        assert result["count"] == 0
        assert result["median_price"] is None
        assert result["listings"] == []


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


def test_tools_importable():
    """All MCP tool functions are importable from property_app.tools."""
    from property_app.tools import (
        company_search,
        epc_lookup,
        planning_search,
        rightmove_search,
        stamp_duty,
    )

    # Verify they exist
    assert stamp_duty is not None
    assert planning_search is not None
    assert company_search is not None
    assert epc_lookup is not None
    assert rightmove_search is not None
