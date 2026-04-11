"""Unit tests for property_app.dashboards.yield_view — yield tool + dashboard."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


MOCK_YIELD_DATA = {
    "gross_yield_pct": 5.2,
    "median_sale_price": 250000,
    "median_rent_monthly": 1083,
    "sale_count": 12,
    "rental_count": 8,
    "yield_assessment": "average",
    "data_quality": "good",
}


# ---------------------------------------------------------------------------
# _fetch_yield (raw async helper)
# ---------------------------------------------------------------------------


def test_fetch_yield_returns_dict():
    """_fetch_yield returns dict with yield and assessment fields."""
    from property_app.dashboards.yield_view import _fetch_yield

    mock_result = MagicMock()
    mock_result.gross_yield_pct = 5.2
    mock_result.sale_count = 12
    mock_result.rental_count = 8
    mock_result.model_dump.return_value = {
        "gross_yield_pct": 5.2,
        "median_sale_price": 250000,
        "median_rent_monthly": 1083,
        "sale_count": 12,
        "rental_count": 8,
    }

    with (
        patch("property_core.calculate_yield", return_value=mock_result),
        patch("property_core.interpret.classify_yield", return_value="average"),
        patch("property_core.interpret.classify_data_quality", return_value="good"),
    ):
        result = asyncio.run(_fetch_yield(postcode="NG1 1AA"))

    assert result["gross_yield_pct"] == 5.2
    assert result["yield_assessment"] == "average"
    assert result["data_quality"] == "good"


def test_fetch_yield_none_gross_yield():
    """_fetch_yield handles None gross_yield_pct gracefully."""
    from property_app.dashboards.yield_view import _fetch_yield

    mock_result = MagicMock()
    mock_result.gross_yield_pct = None
    mock_result.sale_count = 0
    mock_result.rental_count = 0
    mock_result.model_dump.return_value = {
        "gross_yield_pct": None,
        "median_sale_price": None,
        "median_rent_monthly": None,
        "sale_count": 0,
        "rental_count": 0,
    }

    with (
        patch("property_core.calculate_yield", return_value=mock_result),
        patch("property_core.interpret.classify_data_quality", return_value="insufficient"),
    ):
        result = asyncio.run(_fetch_yield(postcode="ZZ1 1ZZ"))

    assert result["yield_assessment"] is None
    assert result["data_quality"] == "insufficient"


# ---------------------------------------------------------------------------
# yield_dashboard (pre-populated Prefab view)
# ---------------------------------------------------------------------------


def test_yield_dashboard_returns_tool_result():
    """yield_dashboard returns a ToolResult with content and structured_content."""
    from fastmcp.tools import ToolResult

    from property_app.dashboards.yield_view import yield_dashboard

    with patch("property_app.dashboards.yield_view._fetch_yield", return_value=MOCK_YIELD_DATA):
        result = asyncio.run(yield_dashboard(postcode="NG1 1AA"))

    assert isinstance(result, ToolResult)
    text = result.content[0].text
    assert "NG1 1AA" in text
    assert "5.2%" in text


def test_yield_dashboard_text_has_assessment():
    """Text fallback includes assessment and quality labels."""
    from property_app.dashboards.yield_view import yield_dashboard

    with patch("property_app.dashboards.yield_view._fetch_yield", return_value=MOCK_YIELD_DATA):
        result = asyncio.run(yield_dashboard(postcode="NG1 1AA"))

    text = result.content[0].text
    assert "average" in text
    assert "good" in text


# ---------------------------------------------------------------------------
# Import test
# ---------------------------------------------------------------------------


def test_yield_importable():
    """get_yield and yield_dashboard are importable."""
    from property_app.dashboards.yield_view import get_yield, yield_dashboard

    assert get_yield is not None
    assert yield_dashboard is not None
