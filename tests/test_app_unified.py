"""Unit tests for property_app.dashboards.unified — unified property dashboard."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


def _mock_comps():
    m = MagicMock()
    m.model_dump.return_value = {
        "count": 15,
        "median": 200000,
        "mean": 210000,
        "percentile_25": 180000,
        "percentile_75": 240000,
        "min": 150000,
        "max": 280000,
        "thin_market": False,
        "escalated_from": None,
        "escalated_to": None,
        "transactions": [
            {
                "price": 200000,
                "date": "2025-06-15",
                "property_type": "F",
                "estate_type": "Leasehold",
                "paon": "12",
                "saon": None,
                "street": "HIGH STREET",
            },
            {
                "price": 220000,
                "date": "2025-07-01",
                "property_type": "T",
                "estate_type": "Freehold",
                "paon": "5",
                "saon": None,
                "street": "PARK ROAD",
            },
        ],
    }
    return m


def _mock_yield():
    m = MagicMock()
    m.gross_yield_pct = 5.2
    m.sale_count = 15
    m.rental_count = 8
    m.model_dump.return_value = {
        "gross_yield_pct": 5.2,
        "median_sale_price": 200000,
        "median_rent_monthly": 867,
        "sale_count": 15,
        "rental_count": 8,
    }
    return m


def _mock_rental():
    m = MagicMock()
    m.model_dump.return_value = {
        "rental_listings_count": 8,
        "median_rent_monthly": 867,
        "average_rent_monthly": 920,
        "min_rent": 650,
        "max_rent": 1200,
        "thin_market": False,
        "escalated_from": None,
        "escalated_to": None,
    }
    return m


def _patches():
    """Return context managers for all three data sources."""
    comps_mock = _mock_comps()
    yield_mock = _mock_yield()
    rental_mock = _mock_rental()

    async def fake_yield(**kw):
        return yield_mock

    async def fake_rental(*a, **kw):
        return rental_mock

    return (
        patch("property_core.PPDService.comps", return_value=comps_mock),
        patch("property_core.calculate_yield", side_effect=fake_yield),
        patch("property_core.rental_service.analyze_rentals", side_effect=fake_rental),
        patch("property_core.interpret.classify_yield", return_value="average"),
        patch("property_core.interpret.classify_data_quality", return_value="good"),
    )


# ---------------------------------------------------------------------------
# _fetch_unified
# ---------------------------------------------------------------------------


def test_fetch_unified_returns_combined_dict():
    """_fetch_unified returns dict with comps, yield_data, and rental sections."""
    from property_app.dashboards.unified import _fetch_unified

    p1, p2, p3, p4, p5 = _patches()
    with p1, p2, p3, p4, p5:
        result = asyncio.run(_fetch_unified(postcode="NG1 1AA"))

    assert "comps" in result
    assert "yield_data" in result
    assert "rental" in result
    assert result["comps"]["count"] == 15
    assert result["yield_data"]["gross_yield_pct"] == 5.2
    assert result["rental"]["rental_listings_count"] == 8


def test_fetch_unified_adds_assessment_labels():
    """_fetch_unified adds yield_assessment and data_quality."""
    from property_app.dashboards.unified import _fetch_unified

    p1, p2, p3, p4, p5 = _patches()
    with p1, p2, p3, p4, p5:
        result = asyncio.run(_fetch_unified(postcode="NG1 1AA"))

    assert result["yield_data"]["yield_assessment"] == "average"
    assert result["yield_data"]["data_quality"] == "good"


# ---------------------------------------------------------------------------
# property_dashboard
# ---------------------------------------------------------------------------


def test_property_dashboard_returns_tool_result():
    """property_dashboard returns a ToolResult with text + PrefabApp."""
    from fastmcp.tools import ToolResult

    from property_app.dashboards.unified import property_dashboard

    with patch("property_app.dashboards.unified._fetch_unified") as mock_fetch:
        mock_fetch.return_value = {
            "comps": _mock_comps().model_dump.return_value,
            "yield_data": {
                **_mock_yield().model_dump.return_value,
                "yield_assessment": "average",
                "data_quality": "good",
            },
            "rental": _mock_rental().model_dump.return_value,
        }
        result = asyncio.run(property_dashboard(postcode="NG1 1AA"))

    assert isinstance(result, ToolResult)


def test_property_dashboard_text_has_key_stats():
    """Text fallback includes postcode, median, yield."""
    from property_app.dashboards.unified import property_dashboard

    with patch("property_app.dashboards.unified._fetch_unified") as mock_fetch:
        mock_fetch.return_value = {
            "comps": _mock_comps().model_dump.return_value,
            "yield_data": {
                **_mock_yield().model_dump.return_value,
                "yield_assessment": "average",
                "data_quality": "good",
            },
            "rental": _mock_rental().model_dump.return_value,
        }
        result = asyncio.run(property_dashboard(postcode="NG1 1AA"))

    text = result.content[0].text
    assert "NG1 1AA" in text
    assert "200,000" in text or "£200,000" in text
    assert "5.2%" in text


# ---------------------------------------------------------------------------
# Import test
# ---------------------------------------------------------------------------


def test_unified_importable():
    """get_property_data and property_dashboard are importable."""
    from property_app.dashboards.unified import get_property_data, property_dashboard

    assert get_property_data is not None
    assert property_dashboard is not None
