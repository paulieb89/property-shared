"""PR 2 — escalation requires transport-layer proof of exhaustion.

`ppd_service.py` sets `thin_market = count < threshold` where `count` is the
length of the list AFTER the upstream window was bounded and after client-side
filtering. A short list is therefore equally consistent with "the window was full
and we discarded most of it". Escalating on that widens sector -> district on no
evidence, and a small `limit` alone can trigger it.

Evidence must come from the transport: `raw_bindings_returned` vs `fetch_limit`.

**PR 2 decision: live SPARQL never auto-widens geography.** `fetch_limit` is
derived from the presentation limit, so evidence discovery still varies with
limit -- it cannot authorise escalation. When `auto_escalate=True` the requested
(narrower) geography is returned with an explicit warning. Snapshot routing may
re-enable escalation in PR 4 using limit-independent deterministic evidence.

Spec: docs/design/ppd-source-routing.md sections 2.7.3 and 2.7.4.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from property_core.models.ppd import PPDTransaction
from property_core.ppd_client import PricePaidDataClient, SearchPage
from property_core.provenance import TransportEvidence
from property_core.ppd_service import PPDService


def _rows(n: int, postcode: str = "M3 7AA", ptype: str = "F") -> list[PPDTransaction]:
    return [
        PPDTransaction(
            transaction_id=f"{{T-{i:04d}}}", price=200000 + i, date="2025-06-01",
            postcode=postcode, property_type=ptype, estate_type="L",
            transaction_category="A", new_build=False, paon=str(i),
            street="EXAMPLE STREET", town="MANCHESTER", county="GREATER MANCHESTER",
            district="MANCHESTER",
        )
        for i in range(n)
    ]


def _page(rows, raw_bindings_returned, fetch_limit):
    return SearchPage(
        transactions=rows,
        evidence=TransportEvidence(
            raw_bindings_returned=raw_bindings_returned, fetch_limit=fetch_limit
        ),
    )


# --------------------------------------------------------------------------
# Evidence must reach the decision point at all
# --------------------------------------------------------------------------

def test_client_exposes_transport_evidence():
    client = PricePaidDataClient()
    payload = {"results": {"bindings": []}}
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=payload):
        page = client.search_with_evidence(postcode_prefix="M3 7", limit=10)
    assert isinstance(page.evidence, TransportEvidence)
    assert page.evidence.fetch_limit is not None
    assert page.evidence.raw_bindings_returned == 0


def test_evidence_reports_the_raw_binding_count_not_the_filtered_count():
    """Client-side filters discard rows; evidence must predate that."""
    client = PricePaidDataClient()

    def binding(txid, ptype_uri):
        lit = lambda v: {"type": "literal", "value": str(v)}  # noqa: E731
        return {"transactionId": lit(txid), "pricePaid": lit(1),
                "transactionDate": lit("2025-01-01"), "postcode": lit("M3 7AA"),
                "propertyType": {"type": "uri", "value": ptype_uri},
                "estateType": {"type": "uri",
                               "value": "http://landregistry.data.gov.uk/def/common/leasehold"},
                "transactionCategory": {
                    "type": "uri",
                    "value": "http://landregistry.data.gov.uk/def/ppi/standardPricePaidTransaction"},
                "newBuild": lit("false"), "paon": lit("1"), "saon": lit(""),
                "street": lit("S"), "town": lit("M"), "county": lit("C"),
                "locality": lit(""), "district": lit("D")}

    flat = "http://landregistry.data.gov.uk/def/common/flat-maisonette"
    det = "http://landregistry.data.gov.uk/def/common/detached"
    payload = {"results": {"bindings": [binding("{A}", flat), binding("{B}", det),
                                        binding("{C}", det)]}}
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=payload):
        page = client.search_with_evidence(postcode_prefix="M3 7", property_type="F", limit=10)
    assert page.evidence.raw_bindings_returned == 3, "evidence must count raw bindings"
    assert len(page.transactions) == 1, "client-side filter should have dropped two"


# --------------------------------------------------------------------------
# Escalation rules
# --------------------------------------------------------------------------

def test_full_window_with_few_eligible_rows_does_not_escalate():
    """THE regression case: window full, post-filter short. Must not widen."""
    svc = PPDService()
    page = _page(_rows(2), raw_bindings_returned=150, fetch_limit=150)
    with patch.object(PricePaidDataClient, "search_with_evidence", return_value=page):
        resp = svc.comps(postcode="M3 7AA", search_level="sector",
                         limit=50, thin_market_threshold=5)
    assert resp.escalated_from is None and resp.escalated_to is None
    assert resp.query.search_level == "sector", "geography changed without evidence"
    assert any("exhaust" in w.lower() or "incomplete" in w.lower() for w in resp.warnings), (
        f"expected a completeness warning, got {resp.warnings}"
    )


def test_unknown_exhaustion_does_not_escalate():
    svc = PPDService()
    page = SearchPage(transactions=_rows(2), evidence=TransportEvidence())
    with patch.object(PricePaidDataClient, "search_with_evidence", return_value=page):
        resp = svc.comps(postcode="M3 7AA", search_level="sector",
                         limit=50, thin_market_threshold=5)
    assert resp.escalated_to is None
    assert resp.query.search_level == "sector"
    assert resp.warnings


def test_live_never_escalates_even_with_proven_exhaustion():
    """PR 2: fetch_limit derives from the presentation limit, so exhaustion
    evidence is itself limit-dependent and cannot authorise widening."""
    svc = PPDService()
    page = _page(_rows(2), raw_bindings_returned=2, fetch_limit=150)
    with patch.object(PricePaidDataClient, "search_with_evidence",
                      return_value=page) as call:
        resp = svc.comps(postcode="M3 7AA", search_level="sector",
                         limit=50, thin_market_threshold=5, auto_escalate=True)
    assert resp.escalated_from is None and resp.escalated_to is None
    assert resp.query.search_level == "sector"
    assert call.call_count == 1, "escalation issued a second upstream request"
    assert any("escalat" in w.lower() for w in resp.warnings), resp.warnings


def test_proven_exhaustion_above_threshold_does_not_escalate():
    svc = PPDService()
    page = _page(_rows(40), raw_bindings_returned=40, fetch_limit=150)
    with patch.object(PricePaidDataClient, "search_with_evidence", return_value=page):
        resp = svc.comps(postcode="M3 7AA", search_level="sector",
                         limit=50, thin_market_threshold=5)
    assert resp.escalated_to is None


def test_limit_4_and_limit_5_agree_exactly():
    """The decisive regression: same fixture, same window, different page size.

    Identical geography, no escalation either way, the warning present exactly
    once, and no extra upstream request.
    """
    svc = PPDService()
    seen = {}
    for limit in (4, 5):
        page = _page(_rows(3), raw_bindings_returned=limit * 3, fetch_limit=limit * 3)
        with patch.object(PricePaidDataClient, "search_with_evidence",
                          return_value=page) as call:
            resp = svc.comps(postcode="M3 7AA", search_level="sector",
                             limit=limit, thin_market_threshold=5,
                             auto_escalate=True)
        seen[limit] = {
            "level": resp.query.search_level,
            "escalated": (resp.escalated_from, resp.escalated_to),
            "escalation_warnings": [w for w in resp.warnings if "escalat" in w.lower()],
            "upstream_calls": call.call_count,
        }
    assert seen[4]["level"] == seen[5]["level"] == "sector"
    assert seen[4]["escalated"] == seen[5]["escalated"] == (None, None)
    for limit in (4, 5):
        assert len(seen[limit]["escalation_warnings"]) == 1, seen[limit]
        assert seen[limit]["upstream_calls"] == 1, seen[limit]


def test_thin_market_is_documented_as_a_bounded_sample_indicator():
    """Kept for compatibility, but it must not read as a whole-market fact."""
    from property_core.models.ppd import PPDCompsResponse

    doc = (PPDCompsResponse.model_fields["thin_market"].description or "").lower()
    assert "sample" in doc or "returned" in doc, doc
    assert "bounded" in doc or "not a whole-market" in doc or "incomplete" in doc, doc


# --------------------------------------------------------------------------
# Presentation limit must never determine geography
# --------------------------------------------------------------------------

@pytest.mark.parametrize("limit", [1, 2, 3, 4])
def test_small_limit_does_not_widen_the_search_area(limit):
    """A page size is not a market judgement."""
    svc = PPDService()
    page = _page(_rows(limit), raw_bindings_returned=limit * 3, fetch_limit=limit * 3)
    with patch.object(PricePaidDataClient, "search_with_evidence", return_value=page):
        resp = svc.comps(postcode="M3 7AA", search_level="sector",
                         limit=limit, thin_market_threshold=5)
    assert resp.query.search_level == "sector", (
        f"limit={limit} changed the geography"
    )
    assert resp.escalated_to is None


def test_identical_data_yields_identical_geography_regardless_of_limit():
    svc = PPDService()
    levels = []
    for limit in (3, 100):
        page = _page(_rows(3), raw_bindings_returned=300, fetch_limit=300)
        with patch.object(PricePaidDataClient, "search_with_evidence", return_value=page):
            levels.append(
                svc.comps(postcode="M3 7AA", search_level="sector",
                          limit=limit, thin_market_threshold=5).query.search_level
            )
    assert levels[0] == levels[1] == "sector"
