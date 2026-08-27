"""PR 2 — a failed lookup is never reported as an absent record.

Two paths currently conflate the two:

* `PPDTransactionRecord.from_linked_data` (models/ppd.py:249) does
  `primary = result.get("primaryTopic", {})` then `primary.get("propertyAddress")`
  at :270. When upstream returns `primaryTopic` as a bare string URI, `primary`
  is a `str` and that line raises `AttributeError` -- an internal error leaked
  for what is really "no record".
* `_find_subject_property` (ppd_service.py:409-411) swallows every exception and
  returns `None`, so "the lookup failed" is indistinguishable from "this property
  has no sale history".

Spec: docs/design/ppd-source-routing.md sections 2.8 and 2.6.
"""

from __future__ import annotations

import urllib.error
from unittest.mock import patch

import pytest

from property_core.exceptions import TransactionNotFoundError, UpstreamUnavailableError
from property_core.ppd_client import PricePaidDataClient
from property_core.ppd_service import PPDService

TXID = "{AAAAAAAA-0000-0000-0000-00000000ABCD}"

FOUND = {"result": {"primaryTopic": {
    "_about": f"http://landregistry.data.gov.uk/data/ppi/transaction/{TXID}/current",
    "pricePaid": 250000,
    "transactionDate": "2025-06-01",
    "propertyAddress": {"postcode": "B5 4BX", "paon": "33", "street": "ESSEX STREET"},
    "recordStatus": {"_about": "http://landregistry.data.gov.uk/def/ppi/add"},
}}}

#: The API's stub shape for an unknown id: primaryTopic is a bare URI string.
NOT_FOUND = {"result": {
    "primaryTopic": f"http://landregistry.data.gov.uk/data/ppi/transaction/{TXID}/current",
    "_about": "http://landregistry.data.gov.uk/data/ppi/transaction",
}}


# --------------------------------------------------------------------------
# Exact-ID: found / not_found / lookup_failed
# --------------------------------------------------------------------------

def test_object_primary_topic_is_found():
    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json", return_value=FOUND):
        record = client.get_transaction_record(TXID)
    assert record is not None
    assert record.price_paid == 250000


def test_bare_string_primary_topic_is_not_found_not_an_attribute_error():
    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json", return_value=NOT_FOUND):
        with pytest.raises(TransactionNotFoundError):
            client.get_transaction_record(TXID)


def test_bare_string_primary_topic_never_raises_attribute_error():
    """The specific leak: 'str' object has no attribute 'get'."""
    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json", return_value=NOT_FOUND):
        try:
            client.get_transaction_record(TXID)
        except TransactionNotFoundError:
            pass
        except AttributeError as exc:  # pragma: no cover - the defect
            pytest.fail(f"AttributeError leaked to the caller: {exc}")


@pytest.mark.parametrize(
    "boom",
    [
        urllib.error.HTTPError("u", 503, "unavailable", {}, None),
        urllib.error.URLError("connection refused"),
        TimeoutError("timed out"),
        ValueError("Expecting value: line 1 column 1 (char 0)"),
    ],
    ids=["http-503", "urlerror", "timeout", "unparseable-body"],
)
def test_upstream_failure_is_lookup_failed_not_not_found(boom):
    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json", side_effect=boom):
        with pytest.raises(UpstreamUnavailableError):
            client.get_transaction_record(TXID)


def test_lookup_failed_is_never_rendered_as_not_found():
    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json",
                      side_effect=urllib.error.URLError("down")):
        with pytest.raises(UpstreamUnavailableError):
            client.get_transaction_record(TXID)
        # and specifically NOT the not-found type
        with pytest.raises(Exception) as ei:
            client.get_transaction_record(TXID)
        assert not isinstance(ei.value, TransactionNotFoundError)


def test_rest_maps_not_found_to_404_and_failure_to_502():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    with patch.object(PricePaidDataClient, "_fetch_json", return_value=NOT_FOUND):
        assert c.get(f"/v1/ppd/transaction/{TXID}").status_code == 404
    with patch.object(PricePaidDataClient, "_fetch_json",
                      side_effect=urllib.error.URLError("down")):
        assert c.get(f"/v1/ppd/transaction/{TXID}").status_code == 502


# --------------------------------------------------------------------------
# Subject property: failure must not become absence
# --------------------------------------------------------------------------

def _empty_page():
    from property_core.ppd_client import SearchPage
    from property_core.provenance import TransportEvidence

    return SearchPage(transactions=[],
                      evidence=TransportEvidence(raw_bindings_returned=0, fetch_limit=150))


def test_subject_property_lookup_failure_warns_rather_than_reporting_no_history():
    svc = PPDService()
    with patch.object(PricePaidDataClient, "search_with_evidence",
                      return_value=_empty_page()), \
         patch.object(PPDService, "_subject_property_lookup",
                      side_effect=urllib.error.URLError("sparql down")):
        resp = svc.comps(postcode="B5 4BX", address="33 ESSEX STREET",
                         search_level="sector", auto_escalate=False)
    assert resp.subject_property is None
    assert any("subject" in w.lower() for w in resp.warnings), (
        f"a failed subject lookup must warn, got {resp.warnings}"
    )


def test_genuine_absence_of_subject_history_does_not_warn():
    """The two outcomes must be distinguishable in the response."""
    svc = PPDService()
    with patch.object(PricePaidDataClient, "search_with_evidence",
                      return_value=_empty_page()), \
         patch.object(PPDService, "_subject_property_lookup", return_value=None):
        resp = svc.comps(postcode="B5 4BX", address="33 ESSEX STREET",
                         search_level="sector", auto_escalate=False)
    assert resp.subject_property is None
    assert not any("subject" in w.lower() for w in resp.warnings), (
        f"a genuine no-match must not warn, got {resp.warnings}"
    )


def test_comps_still_succeeds_when_the_subject_lookup_fails():
    """Resilience of the original bare `except` is preserved."""
    svc = PPDService()
    with patch.object(PricePaidDataClient, "search_with_evidence",
                      return_value=_empty_page()), \
         patch.object(PPDService, "_subject_property_lookup",
                      side_effect=RuntimeError("boom")):
        resp = svc.comps(postcode="B5 4BX", address="33 ESSEX STREET",
                         search_level="sector", auto_escalate=False)
    assert resp is not None and resp.count == 0
