"""Unit tests for property_app.dashboards.yield_view -- yield tool + dashboard."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _fetch_yield (raw async helper)
# ---------------------------------------------------------------------------


def test_fetch_yield_returns_dict():
    """_fetch_yield returns dict with gross_yield_pct and assessment keys."""
    from property_app.dashboards.yield_view import _fetch_yield

    mock_result = MagicMock()
    mock_result.gross_yield_pct = 5.2
    mock_result.sale_count = 10
    mock_result.rental_count = 8
    mock_result.model_dump.return_value = {
        "postcode": "NG1 1AA",
        "median_sale_price": 180000,
        "sale_count": 10,
        "median_monthly_rent": 780,
        "rental_count": 8,
        "gross_yield_pct": 5.2,
        "thin_market": False,
    }

    with (
        patch("property_core.calculate_yield", new_callable=AsyncMock, return_value=mock_result) as mock_calc,
        patch("property_core.interpret.classify_yield", return_value="average") as mock_cy,
        patch("property_core.interpret.classify_data_quality", return_value="good") as mock_dq,
    ):
        result = asyncio.run(_fetch_yield(postcode="NG1 1AA"))

    assert isinstance(result, dict)
    assert result["gross_yield_pct"] == 5.2
    assert result["yield_assessment"] == "average"
    assert result["data_quality"] == "good"
    mock_calc.assert_awaited_once_with(
        postcode="NG1 1AA",
        months=24,
        search_level="sector",
        property_type=None,
        radius=0.5,
    )
    mock_cy.assert_called_once_with(5.2)
    mock_dq.assert_called_once_with(10, 8)


def test_fetch_yield_none_gross_yield():
    """_fetch_yield handles None gross_yield_pct gracefully."""
    from property_app.dashboards.yield_view import _fetch_yield

    mock_result = MagicMock()
    mock_result.gross_yield_pct = None
    mock_result.sale_count = 0
    mock_result.rental_count = 0
    mock_result.model_dump.return_value = {
        "postcode": "ZZ1 1ZZ",
        "median_sale_price": None,
        "sale_count": 0,
        "median_monthly_rent": None,
        "rental_count": 0,
        "gross_yield_pct": None,
        "thin_market": True,
    }

    with (
        patch("property_core.calculate_yield", new_callable=AsyncMock, return_value=mock_result),
        patch("property_core.interpret.classify_data_quality", return_value="insufficient"),
    ):
        result = asyncio.run(_fetch_yield(postcode="ZZ1 1ZZ"))

    assert result["yield_assessment"] is None
    assert result["data_quality"] == "insufficient"


def test_fetch_yield_passes_all_params():
    """_fetch_yield forwards all parameters to calculate_yield."""
    from property_app.dashboards.yield_view import _fetch_yield

    mock_result = MagicMock()
    mock_result.gross_yield_pct = 7.0
    mock_result.sale_count = 15
    mock_result.rental_count = 12
    mock_result.model_dump.return_value = {
        "gross_yield_pct": 7.0,
        "sale_count": 15,
        "rental_count": 12,
    }

    with (
        patch("property_core.calculate_yield", new_callable=AsyncMock, return_value=mock_result) as mock_calc,
        patch("property_core.interpret.classify_yield", return_value="strong"),
        patch("property_core.interpret.classify_data_quality", return_value="good"),
    ):
        asyncio.run(
            _fetch_yield(
                postcode="B1 1AA",
                months=12,
                search_level="district",
                property_type="F",
                radius=1.0,
            )
        )

    mock_calc.assert_awaited_once_with(
        postcode="B1 1AA",
        months=12,
        search_level="district",
        property_type="F",
        radius=1.0,
    )


# ---------------------------------------------------------------------------
# yield_dashboard (Prefab UI)
# ---------------------------------------------------------------------------


def test_yield_dashboard_returns_prefab_app():
    """yield_dashboard returns a PrefabApp instance."""
    from prefab_ui.app import PrefabApp

    from property_app.dashboards.yield_view import yield_dashboard

    result = yield_dashboard(postcode="NG1 1AA")
    assert isinstance(result, PrefabApp)


def test_yield_dashboard_has_state():
    """yield_dashboard sets initial state with data=None."""
    from property_app.dashboards.yield_view import yield_dashboard

    result = yield_dashboard(postcode="E1 6AN")
    assert result.state is not None
    assert result.state["data"] is None
    assert result.state["postcode"] == "E1 6AN"


def test_yield_dashboard_title():
    """yield_dashboard sets the correct title."""
    from property_app.dashboards.yield_view import yield_dashboard

    result = yield_dashboard()
    assert result.title == "Yield Dashboard"


# ---------------------------------------------------------------------------
# Import test
# ---------------------------------------------------------------------------


def test_yield_importable():
    """get_yield and yield_dashboard are importable."""
    from property_app.dashboards.yield_view import get_yield, yield_dashboard

    assert get_yield is not None
    assert yield_dashboard is not None
