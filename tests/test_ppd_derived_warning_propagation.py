"""Review follow-up: a comps completeness caveat must survive into derived figures.

`calculate_yield` divides rent by `comps.median`. If that median came from an
incomplete comps window, the resulting yield is equally uncertain -- but
`YieldAnalysis` had no `warnings` field and every return path dropped
`comps.warnings`, so an uncaveated number reached the user.

These are end-to-end: real services, transport mocked, no network.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from property_core.models.ppd import PPDTransaction
from property_core.ppd_client import PricePaidDataClient, SearchPage
from property_core.provenance import TransportEvidence

def _rentals():
    """Real RightmoveListing objects -- yield_service reads `.price`."""
    from property_core.models.rightmove import RightmoveListing

    return [
        RightmoveListing(id=f"r{i}", url=f"https://example.invalid/r{i}",
                         price=1200 + i * 50, address="B5 4BX", bedrooms=2)
        for i in range(4)
    ]


def _saturated(n: int = 6) -> SearchPage:
    rows = [
        PPDTransaction(
            transaction_id=f"{{Y-{i}}}", price=250_000 + i * 1000, date="2025-06-01",
            postcode="B5 4BX", property_type="F", estate_type="L",
            transaction_category="A", new_build=False, paon=str(i),
            street="ESSEX STREET", town="BIRMINGHAM", county="WEST MIDLANDS",
            district="BIRMINGHAM",
        )
        for i in range(n)
    ]
    return SearchPage(
        transactions=rows,
        evidence=TransportEvidence(raw_bindings_returned=150, fetch_limit=150),
    )


def _incomplete(warnings) -> bool:
    joined = " ".join(warnings or []).lower()
    return "incomplete" in joined or "exhaust" in joined


@pytest.fixture
def saturated_market():
    with patch.object(PricePaidDataClient, "search_with_evidence",
                      return_value=_saturated()), \
         patch("property_core.yield_service.fetch_listings", return_value=_rentals()):
        yield


def test_yield_analysis_has_a_warnings_field():
    from property_core.models.report import YieldAnalysis

    assert "warnings" in YieldAnalysis.model_fields


def test_calculate_yield_carries_the_comps_warning(saturated_market):
    from property_core import calculate_yield

    result = asyncio.run(calculate_yield(postcode="B5 4BX", months=24))
    assert _incomplete(result.warnings), result.warnings


def test_a_yield_number_is_never_presented_without_its_caveat(saturated_market):
    """The point of the whole exercise: no uncaveated derived figure."""
    from property_core import calculate_yield

    result = asyncio.run(calculate_yield(postcode="B5 4BX", months=24))
    if result.gross_yield_pct is not None:
        assert result.warnings, "a yield figure was returned with no completeness caveat"


def test_market_analysis_has_a_warnings_field():
    from property_core.models.report import MarketAnalysis

    assert "warnings" in MarketAnalysis.model_fields


def test_mcp_property_yield_exposes_the_warning(saturated_market):
    from app.mcp.server import property_yield

    fn = getattr(property_yield, "fn", property_yield)
    result = asyncio.run(fn(postcode="B5 4BX", months=24))
    assert _incomplete(result.get("warnings")), result


def test_mcp_app_get_yield_exposes_the_warning(saturated_market):
    from property_app.dashboards.yield_view import get_yield

    fn = getattr(get_yield, "fn", get_yield)
    out = asyncio.run(fn(postcode="B5 4BX", months=24))
    result = out if isinstance(out, dict) else getattr(out, "structured_content", {})
    assert _incomplete(result.get("warnings")), result


def test_yield_dashboard_renders_the_warning(saturated_market):
    """A caveat the UI drops is a caveat the user never sees."""
    from property_app.dashboards import yield_view

    fn = getattr(yield_view.yield_dashboard, "fn", yield_view.yield_dashboard)
    rendered = str(asyncio.run(fn(postcode="B5 4BX", months=24)))
    assert "incomplete" in rendered.lower() or "exhaust" in rendered.lower(), (
        "the yield dashboard presents a figure without its completeness caveat"
    )
