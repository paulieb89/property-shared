"""PR 2 — malformed postcode input is rejected with a typed error, not passed upstream.

Today an arbitrary string reaches the SPARQL filter. The allowlisted grammar
turns caller error into a typed `invalid_postcode` (REST: 422) instead of an
empty 200 that reads as "no sales here".

Spec: docs/design/ppd-source-routing.md section 2.7.2.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from property_core.exceptions import InvalidPostcodeError
from property_core.ppd_client import PricePaidDataClient

EMPTY = {"results": {"bindings": []}}


@pytest.fixture
def client():
    return PricePaidDataClient()


@pytest.mark.parametrize(
    "prefix",
    ["", "   ", "!!", "B5;DROP", "12345", "ZZZZZZZZZZ", "B5 7AA 9ZZ", "../etc", "B5\n7"],
)
def test_malformed_prefix_raises_typed_error(client, prefix):
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY) as fetch:
        with pytest.raises(InvalidPostcodeError):
            client.sparql_search(postcode_prefix=prefix, limit=10)
        fetch.assert_not_called(), "malformed input must not reach the upstream"


@pytest.mark.parametrize("postcode", ["", "  ", "NOTAPOSTCODE", "B5 4BX EXTRA", "<script>"])
def test_malformed_exact_postcode_raises_typed_error(client, postcode):
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        with pytest.raises(InvalidPostcodeError):
            client.sparql_search(postcode=postcode, limit=10)


@pytest.mark.parametrize(
    "prefix", ["B5", "B50", "M3 7", "SW1A", "SW1A 1", "N1", "EC1V", "b5", " B5 "],
)
def test_valid_prefixes_are_accepted(client, prefix):
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        assert client.sparql_search(postcode_prefix=prefix, limit=10) == []


def test_invalid_postcode_error_is_typed_and_carries_the_offending_value():
    err = InvalidPostcodeError("B5;DROP")
    d = err.to_dict()
    assert d["error"] == "invalid_postcode"
    assert d["retryable"] is False
    assert "B5;DROP" in str(err) or d.get("value") == "B5;DROP"


def test_rest_returns_422_for_malformed_postcode():
    from fastapi.testclient import TestClient

    from app.main import app

    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        r = TestClient(app).get("/v1/ppd/transactions?postcode=NOTAPOSTCODE&limit=5")
    assert r.status_code == 422, r.text
    assert r.json()["detail"]


# --------------------------------------------------------------------------
# Regressions found in adversarial self-review of the PR 2 diff
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "postcode",
    ["GIR 0AA", "SW1A 0AA", "EC1A 1BB", "W1A 0AX", "M1 1AE", "B33 8TH",
     "CR2 6XH", "DN55 1PT"],
)
def test_real_uk_postcodes_are_not_rejected(client, postcode):
    """Rejecting a valid postcode is the same defect pointed the wrong way.

    GIR 0AA (Girobank, Bootle) fits no standard outcode pattern and was rejected
    by the first version of this allowlist.
    """
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        assert client.sparql_search(postcode=postcode, limit=5) == []


@pytest.mark.parametrize("prefix", ["GIR", "W1A", "EC1A", "DN55", "B33", "GIR 0"])
def test_real_uk_prefixes_are_not_rejected(client, prefix):
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        assert client.sparql_search(postcode_prefix=prefix, limit=5) == []


@pytest.mark.parametrize(
    "url",
    [
        "/v1/ppd/transactions?postcode=NOTAPOSTCODE&limit=5",
        "/v1/ppd/comps?postcode=NOTAPOSTCODE&months=24",
        "/v1/ppd/address-search?postcode=NOTAPOSTCODE&limit=5",
        "/v1/ppd/blocks?postcode=NOTAPOSTCODE&months=24",
    ],
)
def test_every_postcode_route_maps_caller_error_to_422_not_502(url):
    """A malformed postcode is caller error on every route, never an upstream failure."""
    from fastapi.testclient import TestClient

    from app.main import app

    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        r = TestClient(app).get(url)
    assert r.status_code == 422, f"{url} -> {r.status_code}: {r.text[:200]}"


def test_invalid_postcode_detail_distinguishes_exact_from_prefix():
    from property_core.exceptions import InvalidPostcodeError

    exact = InvalidPostcodeError("XX", field="postcode").to_dict()
    prefix = InvalidPostcodeError("XX", field="postcode_prefix").to_dict()
    assert exact["field"] == "postcode"
    assert prefix["field"] == "postcode_prefix"
    assert exact["error"] == prefix["error"] == "invalid_postcode"


def test_a_caller_error_is_not_softened_into_a_subject_lookup_warning():
    """comps() must not report malformed input as 'lookup unavailable'."""
    from property_core.exceptions import InvalidPostcodeError
    from property_core.ppd_service import PPDService

    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        with pytest.raises(InvalidPostcodeError):
            PPDService().comps(postcode="NOTAPOSTCODE", address="1 High Street",
                               search_level="sector", auto_escalate=False)


# --------------------------------------------------------------------------
# Re-review: GIR is exactly one postcode. Accepting a nonexistent one is the
# same defect as rejecting a real one.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("postcode", ["GIR 1ZZ", "GIR 9AA", "GIR 0AB", "GIR 2AA"])
def test_nonexistent_gir_postcodes_are_rejected(client, postcode):
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        with pytest.raises(InvalidPostcodeError):
            client.sparql_search(postcode=postcode, limit=5)


@pytest.mark.parametrize("prefix", ["GIR 9", "GIR 1", "GIR 5"])
def test_nonexistent_gir_sectors_are_rejected(client, prefix):
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        with pytest.raises(InvalidPostcodeError):
            client.sparql_search(postcode_prefix=prefix, limit=5)


def test_the_one_real_gir_postcode_and_its_prefixes_still_work(client):
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        assert client.sparql_search(postcode="GIR 0AA", limit=5) == []
        assert client.sparql_search(postcode_prefix="GIR", limit=5) == []
        assert client.sparql_search(postcode_prefix="GIR 0", limit=5) == []


def test_transactions_route_has_exactly_one_invalid_postcode_handler():
    """Re-review found a duplicate that an earlier cleanup claimed to remove."""
    import inspect

    import app.api.v1.ppd as rest

    src = inspect.getsource(rest.transactions)
    assert src.count("except InvalidPostcodeError") == 1, src.count(
        "except InvalidPostcodeError")


def test_transaction_id_route_has_no_postcode_handler():
    """That route takes no postcode; a handler there is dead code."""
    import inspect

    import app.api.v1.ppd as rest

    assert "InvalidPostcodeError" not in inspect.getsource(rest.transaction_record)


def test_rest_yield_maps_caller_error_to_422_not_502():
    from fastapi.testclient import TestClient

    from app.main import app

    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        r = TestClient(app).get("/v1/analysis/yield?postcode=NOTAPOSTCODE")
    assert r.status_code == 422, f"{r.status_code}: {r.text[:200]}"
