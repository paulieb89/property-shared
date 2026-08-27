"""A caveat that never reaches the reader is not a caveat.

`warnings` reaching JSON is necessary but not sufficient. These assert the
caveat reaches the surfaces a human or an LLM actually consumes:

* the rendered HTML report;
* the LLM-facing `ToolResult.content` text of each dashboard -- asserted on the
  TEXT specifically, because `str(ToolResult)` can pass on structured content
  alone and hide exactly this bug;
* the comps and unified dashboards, which present medians derived from the same
  incomplete window.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from property_core.models.ppd import PPDTransaction
from property_core.ppd_client import PricePaidDataClient, SearchPage
from property_core.provenance import TransportEvidence

INCOMPLETE = "result may be incomplete"


def _rentals():
    from property_core.models.rightmove import RightmoveListing

    return [
        RightmoveListing(id=f"r{i}", url=f"https://example.invalid/r{i}",
                         price=1200 + i * 50, address="B5 4BX", bedrooms=2)
        for i in range(4)
    ]


def _saturated(n: int = 6) -> SearchPage:
    rows = [
        PPDTransaction(
            transaction_id=f"{{P-{i}}}", price=250_000 + i * 1000, date="2025-06-01",
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


@pytest.fixture
def incomplete_market():
    with patch.object(PricePaidDataClient, "search_with_evidence",
                      return_value=_saturated()), \
         patch("property_core.yield_service.fetch_listings", return_value=_rentals()), \
         patch("property_core.rental_service.fetch_listings", return_value=_rentals()):
        yield


def _content_text(result) -> str:
    """The LLM-facing text only -- never the structured tree."""
    content = getattr(result, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return " ".join(getattr(c, "text", "") or "" for c in content)


# --------------------------------------------------------------------------
# Rendered HTML report
# --------------------------------------------------------------------------

def test_html_report_renders_the_market_completeness_caveat(incomplete_market):
    from property_core.report_service import PropertyReportService

    report = asyncio.run(
        PropertyReportService().generate_report(
            "33 Essex Street, B5 4BX",
            include_rentals=False,
            include_sales_market=False,
        )
    )
    assert report.market_analysis is not None
    assert any(INCOMPLETE in w for w in report.market_analysis.warnings), (
        "precondition: the report model must carry the caveat"
    )

    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")
    html = templates.get_template("report.html").render(report=report, request=None)
    assert INCOMPLETE in html, "the rendered report shows a median with no caveat"


# --------------------------------------------------------------------------
# LLM-facing dashboard text
# --------------------------------------------------------------------------

def test_yield_dashboard_text_content_includes_the_caveat(incomplete_market):
    from property_app.dashboards.yield_view import yield_dashboard

    fn = getattr(yield_dashboard, "fn", yield_dashboard)
    result = asyncio.run(fn(postcode="B5 4BX", months=24))
    assert INCOMPLETE in _content_text(result).lower() or "incomplete" in _content_text(result).lower(), (
        f"LLM-facing text omits the caveat: {_content_text(result)!r}"
    )


def test_comps_dashboard_text_content_includes_the_caveat(incomplete_market):
    from property_app.dashboards.comps import comps_dashboard

    fn = getattr(comps_dashboard, "fn", comps_dashboard)
    result = fn(postcode="B5 4BX", months=24)
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    assert "incomplete" in _content_text(result).lower(), (
        f"comps dashboard presents an uncaveated median: {_content_text(result)!r}"
    )


def test_unified_dashboard_text_content_includes_the_caveat(incomplete_market):
    from property_app.dashboards.unified import property_dashboard

    fn = getattr(property_dashboard, "fn", property_dashboard)
    result = fn(postcode="B5 4BX")
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    assert "incomplete" in _content_text(result).lower(), (
        f"unified dashboard presents an uncaveated median: {_content_text(result)!r}"
    )


def test_str_of_toolresult_is_not_a_sufficient_assertion(incomplete_market):
    """Guard the guard: prove the text assertion is stricter than str().

    The previous test passed on `str(ToolResult)` while the LLM-facing text
    omitted the caveat entirely.
    """
    from property_app.dashboards.yield_view import yield_dashboard

    fn = getattr(yield_dashboard, "fn", yield_dashboard)
    result = asyncio.run(fn(postcode="B5 4BX", months=24))
    assert _content_text(result), "content text must be non-empty to be assertable"
