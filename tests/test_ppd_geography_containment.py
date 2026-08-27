"""PR 2 — district searches must not leak neighbouring outcodes.

`sparql_search` filters a prefix with `FILTER(STRSTARTS(?postcode, "B5"))`
(property_core/ppd_client.py:212). "B50 4AA" starts with "B5", so a district
search for B5 silently returns B50 rows. B5 is inner Birmingham; B50 is Alcester,
~20 miles away. Comparable sales drawn across that boundary are wrong, and
nothing in the response says so.

These tests drive the real client with the SPARQL transport mocked -- no network.

Spec: docs/design/ppd-source-routing.md section 2.7.1.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from property_core.ppd_client import PricePaidDataClient


def _binding(txid: str, postcode: str, price: int = 250000, date: str = "2025-06-01"):
    lit = lambda v: {"type": "literal", "value": str(v)}  # noqa: E731
    return {
        "transactionId": lit(txid), "pricePaid": lit(price),
        "transactionDate": lit(date), "postcode": lit(postcode),
        "propertyType": {"type": "uri",
                         "value": "http://landregistry.data.gov.uk/def/common/flat-maisonette"},
        "estateType": {"type": "uri",
                       "value": "http://landregistry.data.gov.uk/def/common/leasehold"},
        "transactionCategory": {
            "type": "uri",
            "value": "http://landregistry.data.gov.uk/def/ppi/standardPricePaidTransaction"},
        "newBuild": lit("false"), "paon": lit("1"), "saon": lit(""),
        "street": lit("EXAMPLE STREET"), "town": lit("BIRMINGHAM"),
        "county": lit("WEST MIDLANDS"), "locality": lit(""), "district": lit("BIRMINGHAM"),
    }


#: What a permissive upstream returns for STRSTARTS "B5": both districts.
MIXED = {"results": {"bindings": [
    _binding("{B5-0001}", "B5 4BX"),
    _binding("{B50-0001}", "B50 4AA"),
    _binding("{B5-0002}", "B5 7FN"),
    _binding("{B50-0002}", "B50 4JR"),
]}}


@pytest.fixture
def client():
    return PricePaidDataClient()


def test_district_search_for_b5_never_returns_b50(client):
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=MIXED):
        rows = client.sparql_search(postcode_prefix="B5", limit=50)
    leaked = [t.postcode for t in rows if (t.postcode or "").startswith("B50")]
    assert leaked == [], f"B50 rows leaked into a B5 district search: {leaked}"
    assert {t.postcode for t in rows} == {"B5 4BX", "B5 7FN"}


def test_district_search_for_b50_returns_only_b50(client):
    """The converse must hold too -- B50 must not be swallowed by B5."""
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=MIXED):
        rows = client.sparql_search(postcode_prefix="B50", limit=50)
    assert {t.postcode for t in rows} == {"B50 4AA", "B50 4JR"}


def test_outcode_prefix_is_delimited_in_the_generated_query(client):
    """Push the boundary upstream, not only into a client-side filter.

    An undelimited STRSTARTS makes the upstream return rows we must then discard,
    which also corrupts the exhaustion evidence in section 2.7.3.
    """
    captured = {}

    def _capture(encoded_query):
        captured["q"] = encoded_query.decode()
        return {"results": {"bindings": []}}

    with patch.object(PricePaidDataClient, "_fetch_sparql", side_effect=_capture):
        client.sparql_search(postcode_prefix="B5", limit=10)

    q = captured["q"]
    assert "STRSTARTS" in q
    assert 'B5+' in q or "B5%20" in q or "B5 " in q, (
        "outcode prefix is not space-delimited, so B50 matches B5: " + q[:400]
    )


def test_sector_prefix_still_works(client):
    """Containment must not break the sector case, which was already correct."""
    sector_rows = {"results": {"bindings": [
        _binding("{S-1}", "B5 7FN"), _binding("{S-2}", "B5 7AB"),
    ]}}
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=sector_rows):
        rows = client.sparql_search(postcode_prefix="B5 7", limit=50)
    assert {t.postcode for t in rows} == {"B5 7FN", "B5 7AB"}


@pytest.mark.parametrize(
    "prefix, keep, drop",
    [
        ("N1", "N1 9GU", "N10 3AB"),
        ("E1", "E1 6AN", "E17 4RT"),
        ("B1", "B1 1AA", "B15 2TT"),
    ],
)
def test_single_digit_outcodes_do_not_absorb_their_longer_neighbours(client, prefix, keep, drop):
    payload = {"results": {"bindings": [_binding("{K}", keep), _binding("{D}", drop)]}}
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=payload):
        rows = client.sparql_search(postcode_prefix=prefix, limit=50)
    got = {t.postcode for t in rows}
    assert keep in got and drop not in got, f"{prefix} absorbed {drop}: {got}"
