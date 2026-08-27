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


# --------------------------------------------------------------------------
# Review follow-up: only the OBSERVED bare-string stub proves not-found.
# Every other invalid-but-successful envelope is an upstream shape problem
# (502), not "this transaction does not exist" (404). Reporting a malformed
# response as 404 tells the caller a false fact about the world.
# --------------------------------------------------------------------------

MALFORMED_ENVELOPES = {
    "empty-envelope": {},
    "missing-result": {"other": 1},
    "result-null": {"result": None},
    "result-not-a-dict": {"result": "nope"},
    "primaryTopic-missing": {"result": {}},
    "primaryTopic-null": {"result": {"primaryTopic": None}},
    "primaryTopic-list": {"result": {"primaryTopic": [{"a": 1}]}},
    "primaryTopic-int": {"result": {"primaryTopic": 42}},
    "raw-not-a-dict": ["not", "an", "envelope"],
}


@pytest.mark.parametrize("name", sorted(MALFORMED_ENVELOPES))
def test_malformed_envelope_is_upstream_shape_not_not_found(name):
    from property_core.exceptions import UpstreamShapeError

    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json",
                      return_value=MALFORMED_ENVELOPES[name]):
        with pytest.raises(UpstreamShapeError):
            client.get_transaction_record(TXID)


@pytest.mark.parametrize("name", sorted(MALFORMED_ENVELOPES))
def test_malformed_envelope_is_never_reported_as_not_found(name):
    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json",
                      return_value=MALFORMED_ENVELOPES[name]):
        try:
            client.get_transaction_record(TXID)
        except TransactionNotFoundError:  # pragma: no cover - the defect
            pytest.fail(f"{name}: malformed response reported as 404 not-found")
        except Exception:
            pass


def test_upstream_shape_error_maps_to_502_and_is_retryable_upstream():
    from property_core.exceptions import UpstreamShapeError

    assert issubclass(UpstreamShapeError, UpstreamUnavailableError)
    assert UpstreamShapeError("bad shape").to_dict()["error"] == "upstream_shape_error"


def test_only_the_bare_string_stub_is_not_found():
    """The control: the one shape actually observed to mean 'no such record'."""
    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json", return_value=NOT_FOUND):
        with pytest.raises(TransactionNotFoundError):
            client.get_transaction_record(TXID)


def test_attribute_error_while_parsing_an_object_is_not_not_found():
    """A parse failure on a dict primaryTopic is our problem, not an absence."""
    from property_core.exceptions import UpstreamShapeError
    from property_core.models.ppd import PPDTransactionRecord

    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json", return_value=FOUND), \
         patch.object(PPDTransactionRecord, "from_linked_data",
                      side_effect=AttributeError("'str' object has no attribute 'get'")):
        with pytest.raises(UpstreamShapeError):
            client.get_transaction_record(TXID)


def test_rest_maps_malformed_envelope_to_502_not_404():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    with patch.object(PricePaidDataClient, "_fetch_json", return_value={"result": {}}):
        assert c.get(f"/v1/ppd/transaction/{TXID}").status_code == 502


def test_from_linked_data_rejects_a_malformed_shape_rather_than_emptying_it():
    """Item 2: silently normalising a bad shape to {} weakens the taxonomy.

    The model must refuse; only the client translates the specifically observed
    bare-string stub into not-found.
    """
    from property_core.models.ppd import PPDTransactionRecord

    with pytest.raises((ValueError, TypeError)):
        PPDTransactionRecord.from_linked_data({"result": {"primaryTopic": "http://x"}})
    with pytest.raises((ValueError, TypeError)):
        PPDTransactionRecord.from_linked_data({"result": {}})


# --------------------------------------------------------------------------
# Re-review: only the stub URI for THE REQUESTED transaction proves not-found.
# An arbitrary string says nothing about whether this record exists.
# --------------------------------------------------------------------------

_STUB = f"http://landregistry.data.gov.uk/data/ppi/transaction/{TXID}/current"


def test_the_exact_stub_uri_for_this_transaction_is_not_found():
    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json",
                      return_value={"result": {"primaryTopic": _STUB}}):
        with pytest.raises(TransactionNotFoundError):
            client.get_transaction_record(TXID)


@pytest.mark.parametrize(
    "value",
    ["", "   ", "garbage", "not a uri",
     "http://landregistry.data.gov.uk/data/ppi/transaction/{OTHER-ID}/current",
     "https://example.com/", _STUB + "/extra"],
    ids=["empty", "whitespace", "garbage", "prose", "other-transaction",
         "unrelated-url", "suffixed"],
)
def test_other_strings_are_upstream_shape_not_not_found(value):
    from property_core.exceptions import UpstreamShapeError

    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json",
                      return_value={"result": {"primaryTopic": value}}):
        with pytest.raises(UpstreamShapeError):
            client.get_transaction_record(TXID)


# --------------------------------------------------------------------------
# Final review: the stub check must PARSE the URI, not substring-match it.
# A malformed response from anywhere must never become "this record does not
# exist" -- that is a false statement about the world, sourced from an attacker
# or a broken proxy.
# --------------------------------------------------------------------------

_PATH = f"/data/ppi/transaction/{TXID}/current"


@pytest.mark.parametrize(
    "uri",
    [
        f"https://evil.example/landregistry{_PATH}",
        f"https://landregistry.data.gov.uk.evil.example{_PATH}",
        f"https://evil.example/landregistry.data.gov.uk{_PATH}",
        f"https://landregistry.data.gov.uk@evil.example{_PATH}",
        f"https://user:pw@landregistry.data.gov.uk{_PATH}",
        f"https://landregistry.data.gov.uk:8443{_PATH}",
        f"file://landregistry.data.gov.uk{_PATH}",
        f"javascript:alert(1)#{_PATH}",
        f"http://landregistry.data.gov.uk{_PATH}?x=1",
        f"http://landregistry.data.gov.uk{_PATH}#frag",
        f"http://landregistry.data.gov.uk/evil{_PATH}",
        f"http://LANDREGISTRY.DATA.GOV.UK.evil.example{_PATH}",
    ],
    ids=["lookalike-path", "subdomain-suffix", "host-in-path", "userinfo-at",
         "userinfo-creds", "unexpected-port", "bad-scheme", "javascript-scheme",
         "query", "fragment", "path-prefix", "uppercase-subdomain"],
)
def test_spoofed_stub_uris_are_shape_errors_not_not_found(uri):
    from property_core.exceptions import UpstreamShapeError

    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json",
                      return_value={"result": {"primaryTopic": uri}}):
        with pytest.raises(UpstreamShapeError):
            client.get_transaction_record(TXID)


@pytest.mark.parametrize(
    "uri",
    [
        f"http://landregistry.data.gov.uk{_PATH}",
        f"https://landregistry.data.gov.uk{_PATH}",
        f"http://landregistry.data.gov.uk:80{_PATH}",
        f"https://landregistry.data.gov.uk:443{_PATH}",
        f"  http://landregistry.data.gov.uk{_PATH}  ",
    ],
    ids=["http", "https", "default-port-80", "default-port-443", "whitespace"],
)
def test_the_genuine_stub_uri_is_still_not_found(uri):
    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json",
                      return_value={"result": {"primaryTopic": uri}}):
        with pytest.raises(TransactionNotFoundError):
            client.get_transaction_record(TXID)


# --------------------------------------------------------------------------
# Final: validate the complete authority, not host/userinfo/port separately.
# Piecewise checks left gaps: an empty "@" gives a falsy username, "host:"
# parses to port None, and 80/443 were accepted for either scheme.
# --------------------------------------------------------------------------

_HOST = "landregistry.data.gov.uk"


@pytest.mark.parametrize(
    "uri",
    [
        f"http://{_HOST}:443{_PATH}",
        f"https://{_HOST}:80{_PATH}",
        f"http://@{_HOST}{_PATH}",
        f"http://:@{_HOST}{_PATH}",
        f"http://{_HOST}:{_PATH}",
    ],
    ids=["http-with-443", "https-with-80", "empty-userinfo-at",
         "empty-userinfo-colon-at", "explicit-empty-port"],
)
def test_malformed_authority_is_not_a_stub(uri):
    from property_core.exceptions import UpstreamShapeError

    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json",
                      return_value={"result": {"primaryTopic": uri}}):
        with pytest.raises(UpstreamShapeError):
            client.get_transaction_record(TXID)


@pytest.mark.parametrize(
    "uri",
    [f"http://{_HOST}{_PATH}", f"http://{_HOST}:80{_PATH}",
     f"https://{_HOST}{_PATH}", f"https://{_HOST}:443{_PATH}",
     f"https://{_HOST.upper()}{_PATH}"],
    ids=["http-default", "http-80", "https-default", "https-443", "uppercase-host"],
)
def test_scheme_appropriate_authorities_are_still_stubs(uri):
    client = PricePaidDataClient()
    with patch.object(PricePaidDataClient, "_fetch_json",
                      return_value={"result": {"primaryTopic": uri}}):
        with pytest.raises(TransactionNotFoundError):
            client.get_transaction_record(TXID)
