"""Unit tests for property_app.dashboards.rental -- rental tool + dashboard."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _fetch_rental (raw async helper)
# ---------------------------------------------------------------------------


def test_fetch_rental_returns_dict():
    """_fetch_rental returns dict with rental_listings_count and median_rent_monthly."""
    from property_app.dashboards.rental import _fetch_rental

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "search_radius_miles": 0.5,
        "rental_listings_count": 15,
        "average_rent_monthly": 820,
        "median_rent_monthly": 795,
        "rent_range_low": 650,
        "rent_range_high": 1100,
        "estimated_annual_rent": None,
        "gross_yield_pct": None,
        "yield_assessment": None,
        "thin_market": False,
        "escalated_from": None,
        "escalated_to": None,
        "search_postcode": "NG1 1AA",
    }

    with patch(
        "property_core.analyze_rentals",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_analyze:
        result = asyncio.run(_fetch_rental(postcode="NG1 1AA"))

    assert isinstance(result, dict)
    assert result["rental_listings_count"] == 15
    assert result["median_rent_monthly"] == 795
    assert result["average_rent_monthly"] == 820
    assert result["thin_market"] is False
    mock_analyze.assert_awaited_once_with(
        postcode="NG1 1AA",
        radius=0.5,
        purchase_price=None,
        auto_escalate=True,
        building_type=None,
    )


def test_fetch_rental_with_purchase_price():
    """_fetch_rental passes purchase_price through to analyze_rentals."""
    from property_app.dashboards.rental import _fetch_rental

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "rental_listings_count": 10,
        "median_rent_monthly": 750,
        "gross_yield_pct": 5.0,
        "estimated_annual_rent": 9000,
        "thin_market": False,
    }

    with patch(
        "property_core.analyze_rentals",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_analyze:
        result = asyncio.run(
            _fetch_rental(postcode="NG1 1AA", purchase_price=180000)
        )

    assert result["gross_yield_pct"] == 5.0
    assert result["estimated_annual_rent"] == 9000
    mock_analyze.assert_awaited_once_with(
        postcode="NG1 1AA",
        radius=0.5,
        purchase_price=180000,
        auto_escalate=True,
        building_type=None,
    )


def test_fetch_rental_passes_all_params():
    """_fetch_rental forwards all parameters to analyze_rentals."""
    from property_app.dashboards.rental import _fetch_rental

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "rental_listings_count": 8,
        "median_rent_monthly": 650,
        "thin_market": False,
    }

    with patch(
        "property_core.analyze_rentals",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_analyze:
        asyncio.run(
            _fetch_rental(
                postcode="B1 1AA",
                radius=1.0,
                purchase_price=200000,
                auto_escalate=False,
                building_type="F",
            )
        )

    mock_analyze.assert_awaited_once_with(
        postcode="B1 1AA",
        radius=1.0,
        purchase_price=200000,
        auto_escalate=False,
        building_type="F",
    )


def test_fetch_rental_thin_market():
    """_fetch_rental returns thin_market=True when listing count is low."""
    from property_app.dashboards.rental import _fetch_rental

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "rental_listings_count": 1,
        "median_rent_monthly": 500,
        "average_rent_monthly": 500,
        "thin_market": True,
        "search_postcode": "ZZ1 1ZZ",
    }

    with patch(
        "property_core.analyze_rentals",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = asyncio.run(_fetch_rental(postcode="ZZ1 1ZZ"))

    assert result["thin_market"] is True
    assert result["rental_listings_count"] == 1


# ---------------------------------------------------------------------------
# rental_dashboard (Prefab UI)
# ---------------------------------------------------------------------------


def test_rental_dashboard_returns_prefab_app():
    """rental_dashboard returns a PrefabApp instance."""
    from prefab_ui.app import PrefabApp

    from property_app.dashboards.rental import rental_dashboard

    result = rental_dashboard(postcode="NG1 1AA")
    assert isinstance(result, PrefabApp)


def test_rental_dashboard_has_state():
    """rental_dashboard sets initial state with data=None."""
    from property_app.dashboards.rental import rental_dashboard

    result = rental_dashboard(postcode="E1 6AN")
    assert result.state is not None
    assert result.state["data"] is None
    assert result.state["postcode"] == "E1 6AN"


def test_rental_dashboard_title():
    """rental_dashboard sets the correct title."""
    from property_app.dashboards.rental import rental_dashboard

    result = rental_dashboard()
    assert result.title == "Rental Analysis"


# ---------------------------------------------------------------------------
# Import test
# ---------------------------------------------------------------------------


def test_rental_importable():
    """get_rental and rental_dashboard are importable."""
    from property_app.dashboards.rental import get_rental, rental_dashboard

    assert get_rental is not None
    assert rental_dashboard is not None
