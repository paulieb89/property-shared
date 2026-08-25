"""Unit tests for property_app.tools — plain MCP tool wrappers."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# stamp_duty
# ---------------------------------------------------------------------------


def test_calc_stamp_duty_basic():
    """calc_stamp_duty returns correct SDLT for a standard £300k purchase (April 2025 bands)."""
    from property_app.tools import calc_stamp_duty

    result = calc_stamp_duty(price=300000)
    assert isinstance(result, dict)
    assert "total_sdlt" in result
    assert "effective_rate" in result
    assert result["price"] == 300000
    # 0% on £0–£125k + 2% on £125k–£250k + 5% on £250k–£300k = £5,000
    assert result["total_sdlt"] == 5000
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
    """search_company always calls client.search() — direct lookup by number uses the resource."""
    from property_app.tools import search_company

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "query": "00445790",
        "total_results": 1,
        "companies": [{"company_number": "00445790", "company_name": "Tesco PLC"}],
    }

    with patch("property_core.CompaniesHouseClient") as mock_cls:
        mock_cls.return_value.search.return_value = mock_result
        result = search_company("00445790")
        assert isinstance(result, dict)
        mock_cls.return_value.search.assert_called_once_with("00445790")
        mock_cls.return_value.lookup.assert_not_called()


def test_search_company_not_found():
    """search_company returns error dict when search returns None."""
    from property_app.tools import search_company

    with patch("property_core.CompaniesHouseClient") as mock_cls:
        mock_cls.return_value.search.return_value = None
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


def test_lookup_epc_with_address_no_data():
    """lookup_epc (with address) returns error dict when no EPC match."""
    from property_app.tools import lookup_epc

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_by_postcode = AsyncMock(return_value=None)
        result = asyncio.run(lookup_epc("ZZ99 9ZZ", address="1 Fake St"))
        assert result == {"error": "No EPC data"}


def test_lookup_epc_with_address_and_result():
    """lookup_epc (with address) returns single cert dict when matched."""
    from property_app.tools import lookup_epc

    mock_epc = MagicMock()
    mock_epc.model_dump.return_value = {
        "address": "1 TEST STREET",
        "postcode": "SW1A 1AA",
        "current_rating": "C",
    }

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_by_postcode = AsyncMock(return_value=mock_epc)
        result = asyncio.run(lookup_epc("SW1A 1AA", address="1 Test Street"))
        assert isinstance(result, dict)
        assert result["current_rating"] == "C"


def test_lookup_epc_no_address_empty():
    """No certificates lodged -> error dict, unchanged from v1."""
    from property_app.tools import lookup_epc

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.area_summary = AsyncMock(
            return_value={"total_records": 0, "complete": True, "warnings": [],
                          "rating_distribution": {}, "rating_distribution_sample": None,
                          "rating_distribution_sample_size": None})
        result = asyncio.run(lookup_epc("ZZ99 9ZZ"))
        assert result == {"error": "No EPC data"}


def test_lookup_epc_area_summary_reports_unavailable_stats_as_none():
    """Floor-area and property-type stats live only on full certificates.

    They must be None (unavailable), never {} or 0, which would assert that the
    area genuinely has none.
    """
    from property_app.tools import lookup_epc

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.area_summary = AsyncMock(return_value={
            "total_records": 4,
            "complete": True,
            "rating_distribution": {"B": 1, "C": 2, "D": 1},
            "rating_distribution_sample": None,
            "rating_distribution_sample_size": None,
            "warnings": ["property_type_breakdown and floor-area statistics are unavailable"],
        })
        result = asyncio.run(lookup_epc("NG11 9HD"))

    assert result["postcode"] == "NG11 9HD"
    assert result["summary"]["count"] == 4
    assert result["summary"]["rating_distribution"] == {"B": 1, "C": 2, "D": 1}
    assert result["summary"]["property_type_breakdown"] is None
    assert result["summary"]["floor_area_min"] is None
    assert result["summary"]["floor_area_avg"] is None
    assert result["summary"]["complete"] is True
    assert result["summary"]["warnings"]
    assert "certificates" not in result
    assert "note" in result


def test_lookup_epc_incomplete_area_does_not_present_a_sample_as_the_distribution():
    """A bounded page is a sample, explicitly labelled, not an area distribution."""
    from property_app.tools import lookup_epc

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.area_summary = AsyncMock(return_value={
            "total_records": 500,
            "complete": False,
            "rating_distribution": None,
            "rating_distribution_sample": {"C": 25},
            "rating_distribution_sample_size": 25,
            "warnings": ["bounded page"],
        })
        result = asyncio.run(lookup_epc("NG11 9HD"))

    assert result["summary"]["rating_distribution"] is None
    assert result["summary"]["rating_distribution_sample"] == {"C": 25}
    assert result["summary"]["rating_distribution_sample_size"] == 25
    assert result["summary"]["complete"] is False


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
# epc_search / epc_certificate
# ---------------------------------------------------------------------------


def test_browse_epc_certs_empty():
    """No certificates lodged -> an empty results list, never an error."""
    from types import SimpleNamespace

    from property_app.tools import browse_epc_certs

    page = SimpleNamespace(results=[], pagination=SimpleNamespace(total_records=0),
                           returned_distinct_count=0, duplicates_removed=0,
                           unusable_rows=0, complete=True, warnings=[])
    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_summaries = AsyncMock(return_value=page)
        result = asyncio.run(browse_epc_certs("ZZ99 9ZZ"))
    assert result["results"] == [] and result["total_records"] == 0


def test_browse_epc_certs_returns_summary_fields_only():
    """Summary browse exposes only what the EPC search provides.

    score, floor_area and property_type used to appear here. They exist solely
    on a full certificate now, so returning them would require one upstream
    request per row.
    """
    from types import SimpleNamespace

    from property_app.tools import browse_epc_certs

    def row(cert_no, address, band):
        return SimpleNamespace(
            certificate_number=cert_no, address=address, uprn=None,
            current_energy_efficiency_band=band,
            registration_date="2023-01-01", schema_type="RdSAP-Schema-20.0.0",
        )

    page = SimpleNamespace(
        results=[row("abc123", "FLAT 1, 10 TEST STREET", "C"),
                 row("def456", "FLAT 2, 10 TEST STREET", "B")],
        pagination=SimpleNamespace(total_records=2),
        returned_distinct_count=2, duplicates_removed=0,
        unusable_rows=0, complete=True, warnings=[],
    )
    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.search_summaries = AsyncMock(return_value=page)
        result = asyncio.run(browse_epc_certs("SW1A 1AA"))

    assert result["total_records"] == 2 and result["complete"] is True
    first = result["results"][0]
    assert first["certificate_number"] == "abc123"
    assert set(first) == {"certificate_number", "address", "uprn",
                          "energy_band", "registration_date", "schema_type"}
    for absent in ("score", "floor_area", "property_type", "raw"):
        assert absent not in first


def test_fetch_epc_certificate_not_found():
    """fetch_epc_certificate returns None when lmk_key not found."""
    from property_app.tools import fetch_epc_certificate

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.get_certificate = AsyncMock(return_value=None)
        result = asyncio.run(fetch_epc_certificate("nonexistent"))
        assert result is None


def test_fetch_epc_certificate_returns_full_cert():
    """fetch_epc_certificate returns slimmed full cert dict."""
    from property_app.tools import fetch_epc_certificate

    mock_epc = MagicMock()
    mock_epc.model_dump.return_value = {
        "address": "FLAT 1, 10 TEST STREET",
        "rating": "C",
        "lmk_key": "abc123",
        "raw": {"should": "be stripped"},
    }

    with patch("property_core.EPCClient") as mock_cls:
        mock_cls.return_value.get_certificate = AsyncMock(return_value=mock_epc)
        result = asyncio.run(fetch_epc_certificate("abc123"))

    assert isinstance(result, dict)
    assert result["lmk_key"] == "abc123"
    assert "raw" not in result


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


def test_tools_importable():
    """All MCP tool functions are importable from property_app.tools."""
    from property_app.tools import (
        browse_epc_certs,
        company_search,
        epc_certificate,
        epc_lookup,
        epc_search,
        fetch_epc_certificate,
        planning_search,
        rightmove_search,
        stamp_duty,
    )

    assert stamp_duty is not None
    assert planning_search is not None
    assert company_search is not None
    assert epc_lookup is not None
    assert epc_search is not None
    assert epc_certificate is not None
    assert browse_epc_certs is not None
    assert fetch_epc_certificate is not None
    assert rightmove_search is not None
