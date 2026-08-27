"""Unit tests for PPDService.comps() residential-default filtering.

Covers the data-parity defaults:
- transaction_category="A" by default (only standard residential sales)
- property_type=None means residential set (F/D/S/T); "ALL" disables type filter;
  specific codes filter to that one type
- filter_outliers=False by default; opt-in for 1.5*IQR trimming applied to BOTH
  stats and the returned transactions list
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest

from property_core.models.ppd import PPDTransaction
from property_core.ppd_service import PPDService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _txn(
    *,
    tid: str,
    price: int,
    property_type: Optional[str] = "F",
    transaction_category: Optional[str] = "A",
    date: str = "2024-01-15",
    postcode: str = "NG1 2NS",
) -> PPDTransaction:
    return PPDTransaction(
        transaction_id=tid,
        price=price,
        date=date,
        postcode=postcode,
        property_type=property_type,
        transaction_category=transaction_category,
        paon=str(int(tid[-2:], 36) if tid[-2:].isalnum() else 1),
        street="HIGH STREET",
    )


def _page(rows: list[PPDTransaction]) -> "SearchPage":
    """A page whose upstream window was NOT saturated, so evidence is 'exhausted'.

    These tests are about filter push-down, not completeness; an exhausted page
    keeps them free of completeness warnings.
    """
    from property_core.ppd_client import SearchPage
    from property_core.provenance import TransportEvidence

    rows = list(rows)
    return SearchPage(
        transactions=rows,
        evidence=TransportEvidence(raw_bindings_returned=len(rows), fetch_limit=1000),
    )


def _service_with(mock_results: list[PPDTransaction]) -> tuple[PPDService, MagicMock]:
    """Build a PPDService whose client returns the provided transactions.

    comps() calls `search_with_evidence` (the evidence-returning seam); the
    subject-property lookup still uses `sparql_search`. Both are mocked, and the
    same MagicMock is exposed as `client.sparql_search` so existing assertions
    about pushed-down kwargs keep reading naturally.
    """
    client = MagicMock()
    seam = MagicMock(return_value=_page(mock_results))
    client.search_with_evidence = seam
    client.sparql_search = seam
    return PPDService(client=client), client


# ---------------------------------------------------------------------------
# transaction_category filtering
# ---------------------------------------------------------------------------


def test_default_transaction_category_is_A_pushed_to_sparql():
    """By default, comps() pushes transaction_category='A' down to the SPARQL client."""
    txns = [_txn(tid="01", price=200_000)]
    service, client = _service_with(txns)

    service.comps(postcode="NG1 2NS", search_level="sector", auto_escalate=False)

    assert client.sparql_search.call_args.kwargs["transaction_category"] == "A"


def test_transaction_category_none_disables_filter():
    """Passing transaction_category=None tells the client to fetch all categories."""
    txns = [_txn(tid="01", price=200_000)]
    service, client = _service_with(txns)

    service.comps(
        postcode="NG1 2NS",
        search_level="sector",
        transaction_category=None,
        auto_escalate=False,
    )

    assert client.sparql_search.call_args.kwargs["transaction_category"] is None


# ---------------------------------------------------------------------------
# property_type semantics
# ---------------------------------------------------------------------------


def test_default_property_type_filters_to_residential_set():
    """property_type=None fetches all types, then post-filters to F/D/S/T."""
    txns = [
        _txn(tid="01", price=200_000, property_type="F"),
        _txn(tid="02", price=250_000, property_type="D"),
        _txn(tid="03", price=180_000, property_type="S"),
        _txn(tid="04", price=220_000, property_type="T"),
        _txn(tid="05", price=900_000, property_type="O"),  # commercial — should drop
    ]
    service, client = _service_with(txns)

    response = service.comps(postcode="NG1 2NS", search_level="sector", auto_escalate=False)

    # No property_type pushed to SPARQL when default (we post-filter instead).
    assert client.sparql_search.call_args.kwargs["property_type"] is None
    types = {t.property_type for t in response.transactions}
    assert types == {"F", "D", "S", "T"}
    assert response.count == 4


def test_property_type_ALL_returns_everything_including_commercial():
    """property_type='ALL' disables both SPARQL filtering and post-filtering."""
    txns = [
        _txn(tid="01", price=200_000, property_type="F"),
        _txn(tid="05", price=900_000, property_type="O"),
    ]
    service, client = _service_with(txns)

    response = service.comps(
        postcode="NG1 2NS",
        search_level="sector",
        property_type="ALL",
        auto_escalate=False,
    )

    # Sentinel must not leak into SPARQL — it should be translated to None.
    assert client.sparql_search.call_args.kwargs["property_type"] is None
    assert response.count == 2
    assert {t.property_type for t in response.transactions} == {"F", "O"}


def test_property_type_single_code_pushed_to_sparql():
    """property_type='O' is pushed to SPARQL with no post-filter."""
    txns = [_txn(tid="01", price=900_000, property_type="O")]
    service, client = _service_with(txns)

    response = service.comps(
        postcode="NG1 2NS",
        search_level="sector",
        property_type="O",
        auto_escalate=False,
    )

    assert client.sparql_search.call_args.kwargs["property_type"] == "O"
    assert response.count == 1
    assert response.transactions[0].property_type == "O"


# ---------------------------------------------------------------------------
# filter_outliers
# ---------------------------------------------------------------------------


def test_filter_outliers_default_off_keeps_outlier():
    """By default, an extreme outlier is NOT dropped — stats reflect it."""
    # Need >=8 points so the outlier doesn't drag Q3 high enough to keep itself.
    txns = [
        _txn(tid=f"{i:02d}", price=p)
        for i, p in enumerate(
            [100_000, 105_000, 110_000, 115_000, 120_000, 125_000, 130_000, 1_600_000]
        )
    ]
    service, _ = _service_with(txns)

    response = service.comps(postcode="NG1 2NS", search_level="sector", auto_escalate=False)

    assert response.count == 8
    assert response.max == 1_600_000


def test_filter_outliers_on_drops_outlier_from_stats_and_list():
    """filter_outliers=True drops the 1.6M outlier from BOTH stats and txns."""
    txns = [
        _txn(tid=f"{i:02d}", price=p)
        for i, p in enumerate(
            [100_000, 105_000, 110_000, 115_000, 120_000, 125_000, 130_000, 1_600_000]
        )
    ]
    service, _ = _service_with(txns)

    response = service.comps(
        postcode="NG1 2NS",
        search_level="sector",
        filter_outliers=True,
        auto_escalate=False,
    )

    assert response.count == 7
    assert response.max == 130_000
    prices = {t.price for t in response.transactions}
    assert 1_600_000 not in prices


def test_filter_outliers_noop_with_fewer_than_four_prices():
    """IQR filter is skipped when there are fewer than 4 prices."""
    txns = [
        _txn(tid="01", price=100_000),
        _txn(tid="02", price=110_000),
        _txn(tid="03", price=1_600_000),
    ]
    service, _ = _service_with(txns)

    response = service.comps(
        postcode="NG1 2NS",
        search_level="sector",
        filter_outliers=True,
        auto_escalate=False,
        thin_market_threshold=0,  # don't escalate just because count is low
    )

    assert response.count == 3
    assert response.max == 1_600_000


# ---------------------------------------------------------------------------
# Auto-escalate threads new params through
# ---------------------------------------------------------------------------


def test_auto_escalate_no_longer_widens_and_still_threads_params():
    """PR 2: live auto-escalation is disabled, so the chain is a single call.

    Previously this asserted three calls (postcode -> sector -> district).
    Widening needs proof the narrower search was exhausted, and the only
    available evidence derives from the caller's presentation limit -- so the
    geography would still move with page size. The caller now gets the requested
    area plus a warning. Parameter threading is still asserted on the one call.
    """
    client = MagicMock()
    seam = MagicMock(return_value=_page([]))
    client.search_with_evidence = seam
    client.sparql_search = seam
    service = PPDService(client=client)

    resp = service.comps(
        postcode="NG1 2NS",
        search_level="postcode",
        property_type="ALL",
        transaction_category=None,
        filter_outliers=True,
        auto_escalate=True,
    )

    assert seam.call_count == 1, "escalation issued extra upstream requests"
    assert resp.query.search_level == "postcode"
    assert resp.escalated_from is None and resp.escalated_to is None
    assert any("escalat" in w.lower() for w in resp.warnings), resp.warnings
    # property_type="ALL" must NOT leak into SPARQL as the literal string.
    assert seam.call_args.kwargs["property_type"] is None
    assert seam.call_args.kwargs["transaction_category"] is None
