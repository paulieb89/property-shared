"""Unit tests for property_app.dashboards.rental — rental tool + dashboard."""
from __future__ import annotations

import asyncio
from unittest.mock import patch


MOCK_RENTAL_DATA = {
    "rental_listings_count": 15,
    "median_rent_monthly": 950,
    "average_rent_monthly": 980,
    "min_rent": 700,
    "max_rent": 1400,
    "gross_yield_pct": None,
    "thin_market": False,
    "escalated_from": None,
    "escalated_to": None,
}

MOCK_RENTAL_WITH_YIELD = {
    **MOCK_RENTAL_DATA,
    "gross_yield_pct": 4.8,
}


# ---------------------------------------------------------------------------
# _fetch_rental (raw async helper)
# ---------------------------------------------------------------------------


def test_fetch_rental_returns_dict():
    """_fetch_rental returns dict with rental stats."""
    from property_app.dashboards.rental import _fetch_rental

    from unittest.mock import MagicMock

    mock_result = MagicMock()
    mock_result.model_dump.return_value = MOCK_RENTAL_DATA

    with patch("property_core.analyze_rentals", return_value=mock_result):
        result = asyncio.run(_fetch_rental(postcode="NG1 1AA"))

    assert result["rental_listings_count"] == 15
    assert result["median_rent_monthly"] == 950


def test_fetch_rental_passes_params():
    """_fetch_rental forwards all parameters."""
    from property_app.dashboards.rental import _fetch_rental

    from unittest.mock import MagicMock

    mock_result = MagicMock()
    mock_result.model_dump.return_value = MOCK_RENTAL_DATA

    with patch("property_core.analyze_rentals", return_value=mock_result) as mock_fn:
        asyncio.run(_fetch_rental(
            postcode="NG1 1AA",
            radius=1.0,
            purchase_price=200000,
            auto_escalate=False,
            building_type="F",
        ))

    mock_fn.assert_called_once_with(
        postcode="NG1 1AA",
        radius=1.0,
        purchase_price=200000,
        auto_escalate=False,
        building_type="F",
    )


# ---------------------------------------------------------------------------
# rental_dashboard (pre-populated Prefab view)
# ---------------------------------------------------------------------------


def test_rental_dashboard_returns_tool_result():
    """rental_dashboard returns a ToolResult with content and structured_content."""
    from fastmcp.tools import ToolResult

    from property_app.dashboards.rental import rental_dashboard

    with patch("property_app.dashboards.rental._fetch_rental", return_value=MOCK_RENTAL_DATA):
        result = asyncio.run(rental_dashboard(postcode="NG1 1AA"))

    assert isinstance(result, ToolResult)
    text = result.content[0].text
    assert "NG1 1AA" in text
    assert "15 listings" in text


def test_rental_dashboard_text_includes_rent():
    """Text fallback includes median rent."""
    from property_app.dashboards.rental import rental_dashboard

    with patch("property_app.dashboards.rental._fetch_rental", return_value=MOCK_RENTAL_DATA):
        result = asyncio.run(rental_dashboard(postcode="NG1 1AA"))

    text = result.content[0].text
    assert "950" in text


def test_rental_dashboard_with_yield():
    """rental_dashboard includes yield when purchase_price given."""
    from property_app.dashboards.rental import rental_dashboard

    with patch("property_app.dashboards.rental._fetch_rental", return_value=MOCK_RENTAL_WITH_YIELD):
        result = asyncio.run(rental_dashboard(postcode="NG1 1AA", purchase_price=200000))

    text = result.content[0].text
    assert "4.8%" in text


# ---------------------------------------------------------------------------
# Import test
# ---------------------------------------------------------------------------


def test_rental_importable():
    """get_rental and rental_dashboard are importable."""
    from property_app.dashboards.rental import get_rental, rental_dashboard

    assert get_rental is not None
    assert rental_dashboard is not None
