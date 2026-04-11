"""Unit tests for property_app.dashboards.comps — comps tool + dashboard."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _search_comps (raw helper)
# ---------------------------------------------------------------------------


def test_search_comps_returns_dict():
    """_search_comps returns dict with count and median keys."""
    from property_app.dashboards.comps import _search_comps

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "count": 5,
        "median": 350000,
        "percentile_25": 300000,
        "percentile_75": 400000,
        "transactions": [],
    }

    with patch("property_core.PPDService") as mock_cls:
        mock_cls.return_value.comps.return_value = mock_result
        result = _search_comps(postcode="SW1A 1AA")

    assert isinstance(result, dict)
    assert "count" in result
    assert "median" in result
    assert result["count"] == 5
    assert result["median"] == 350000


def test_search_comps_passes_all_params():
    """_search_comps forwards all parameters to PPDService.comps()."""
    from property_app.dashboards.comps import _search_comps

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {"count": 0, "median": None, "transactions": []}

    with patch("property_core.PPDService") as mock_cls:
        mock_cls.return_value.comps.return_value = mock_result
        _search_comps(
            postcode="NG1 1AA",
            months=12,
            limit=50,
            search_level="district",
            address="1 Test Street",
            property_type="F",
        )

    mock_cls.return_value.comps.assert_called_once_with(
        postcode="NG1 1AA",
        months=12,
        limit=50,
        search_level="district",
        address="1 Test Street",
        property_type="F",
    )


# ---------------------------------------------------------------------------
# comps_dashboard (pre-populated Prefab view)
# ---------------------------------------------------------------------------

MOCK_COMPS_DATA = {
    "count": 3,
    "median": 250000,
    "mean": 260000,
    "percentile_25": 200000,
    "percentile_75": 300000,
    "min": 180000,
    "max": 350000,
    "thin_market": False,
    "escalated_from": None,
    "escalated_to": None,
    "transactions": [
        {"price": 250000, "date": "2025-01-15", "postcode": "NG1 1AA",
         "property_type": "F", "paon": "Flat 1", "saon": None, "street": "High St"},
        {"price": 200000, "date": "2025-02-20", "postcode": "NG1 1AB",
         "property_type": "T", "paon": "2", "saon": None, "street": "Low Rd"},
        {"price": 300000, "date": "2025-03-10", "postcode": "NG1 1AC",
         "property_type": "D", "paon": "3", "saon": None, "street": "Park Ave"},
    ],
}


def test_comps_dashboard_returns_tool_result():
    """comps_dashboard returns a ToolResult with content and structured_content."""
    from fastmcp.tools import ToolResult

    from property_app.dashboards.comps import comps_dashboard

    with patch("property_app.dashboards.comps._search_comps", return_value=MOCK_COMPS_DATA):
        result = comps_dashboard(postcode="NG1 1AA")

    assert isinstance(result, ToolResult)
    text = result.content[0].text
    assert "NG1 1AA" in text
    assert "250,000" in text


def test_comps_dashboard_text_has_stats():
    """Text fallback includes key stats for LLM reasoning."""
    from property_app.dashboards.comps import comps_dashboard

    with patch("property_app.dashboards.comps._search_comps", return_value=MOCK_COMPS_DATA):
        result = comps_dashboard(postcode="NG1 1AA")

    text = result.content[0].text
    assert "3 transactions" in text
    assert "median" in text.lower()


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


def test_build_price_buckets():
    """_build_price_buckets groups transactions correctly."""
    from property_app.dashboards.comps import _build_price_buckets

    txns = [
        {"price": 80000},
        {"price": 120000},
        {"price": 130000},
        {"price": 250000},
    ]
    buckets = _build_price_buckets(txns)
    labels = [b["range"] for b in buckets]
    assert "50-100k" in labels
    assert "100-150k" in labels
    assert "250-300k" in labels


def test_build_address():
    """_build_address constructs readable address."""
    from property_app.dashboards.comps import _build_address

    assert _build_address({"paon": "42", "street": "High St"}) == "42, High St"
    assert _build_address({"saon": "Flat 1", "paon": "10", "street": "Park Rd"}) == "Flat 1, 10, Park Rd"
    assert _build_address({}) == "—"


# ---------------------------------------------------------------------------
# Import test
# ---------------------------------------------------------------------------


def test_comps_importable():
    """search_comps and comps_dashboard are importable."""
    from property_app.dashboards.comps import comps_dashboard, search_comps

    assert search_comps is not None
    assert comps_dashboard is not None
