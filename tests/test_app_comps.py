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
    mock_cls.return_value.comps.assert_called_once_with(
        postcode="SW1A 1AA",
        months=24,
        limit=30,
        search_level="sector",
        address=None,
        property_type=None,
    )


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
# comps_dashboard (Prefab UI)
# ---------------------------------------------------------------------------


def test_comps_dashboard_returns_prefab_app():
    """comps_dashboard returns a PrefabApp instance."""
    from prefab_ui.app import PrefabApp

    from property_app.dashboards.comps import comps_dashboard

    result = comps_dashboard(postcode="SW1A 1AA")
    assert isinstance(result, PrefabApp)


def test_comps_dashboard_has_state():
    """comps_dashboard sets initial state with results=None."""
    from property_app.dashboards.comps import comps_dashboard

    result = comps_dashboard(postcode="E1 6AN")
    assert result.state is not None
    assert result.state["results"] is None
    assert result.state["postcode"] == "E1 6AN"


def test_comps_dashboard_title():
    """comps_dashboard sets the correct title."""
    from property_app.dashboards.comps import comps_dashboard

    result = comps_dashboard()
    assert result.title == "Comps Dashboard"


# ---------------------------------------------------------------------------
# Import test
# ---------------------------------------------------------------------------


def test_comps_importable():
    """search_comps and comps_dashboard are importable."""
    from property_app.dashboards.comps import comps_dashboard, search_comps

    assert search_comps is not None
    assert comps_dashboard is not None
