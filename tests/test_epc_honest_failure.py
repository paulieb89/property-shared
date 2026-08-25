"""EPC failures must never be reported as "no certificate exists".

Originally written for v1.13.1 against the retired epc.opendatacommunities.org
contract ({"rows": [...]}, Basic auth). The wire shape has moved to the GOV.UK
Bearer API, so the fixtures here changed — but every behavioural guarantee from
v1.13.1 is preserved, and several are now stronger:

  v1.13.1                              v1.14.0
  ------------------------------------ --------------------------------------
  outage -> EPCUpstreamError           unchanged
  unconfigured -> raises               now EPCConfigurationError, more precise
  absence -> None/[]                   unchanged (now a real upstream 404)
  REST outage -> 503 not 404           unchanged
  auth failure -> generic upstream     now EPCAuthenticationError
  404 -> treated as failure            now genuine absence (the upstream
                                        separates 400-invalid from 404-absent)
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from property_core.epc.errors import (
    EPCAuthenticationError,
    EPCInvalidQueryError,
    EPCConfigurationError,
    EPCRateLimitError,
    EPCUpstreamError,
    EPCUpstreamShapeError,
)
from property_core.epc_client import EPCClient

SEARCH_BODY = {
    "data": [{
        "certificateNumber": "1111-2222-3333-4444-5555",
        "addressLine1": "1 Test Street",
        "postcode": "AA1 1AA",
        "currentEnergyEfficiencyBand": "C",
        "registrationDate": "2023-01-01",
        "schemaType": "RdSAP-Schema-20.0.0",
        "uprn": 100000000001,
    }],
    "pagination": {"totalRecords": 1, "currentPage": 1, "totalPages": 1,
                   "pageSize": 5000, "nextPage": None, "prevPage": None},
}

CERT_BODY = {"data": {
    "address_line_1": "1 Test Street",
    "postcode": "AA1 1AA",
    "current_energy_efficiency_band": "C",
    "energy_rating_current": 72,
    "total_floor_area": 55.5,
    "schema_type": "RdSAP-Schema-20.0.0",
    "assessment_type": "RdSAP",
}}


def _client(handler, *, token="test-token"):
    c = EPCClient(token=token)
    c._transport = httpx.MockTransport(handler)
    return c


def _run(coro):
    return asyncio.run(coro)


class TestUpstreamFailuresRaise:
    @pytest.mark.parametrize("status,exc", [
        (403, EPCAuthenticationError),   # token supplied and rejected
        (401, EPCAuthenticationError),
        (429, EPCRateLimitError),
        (500, EPCUpstreamError),
        (502, EPCUpstreamError),
        (503, EPCUpstreamError),
        (301, EPCUpstreamError),         # the retired host's failure mode
        (400, EPCInvalidQueryError),     # caller error, not an outage
    ])
    def test_failure_statuses_raise_typed_errors(self, status, exc):
        c = _client(lambda req: httpx.Response(status, text="nope"))
        with pytest.raises(exc):
            _run(c.search_summaries("AA1 1AA"))
        with pytest.raises(exc):
            _run(c.get_certificate("1111-2222-3333-4444-5555"))

    def test_network_error_raises(self):
        def boom(request):
            raise httpx.ConnectError("dns failure", request=request)

        with pytest.raises(EPCUpstreamError):
            _run(_client(boom).search_summaries("AA1 1AA"))

    def test_malformed_json_raises(self):
        c = _client(lambda req: httpx.Response(200, text="<html>not json</html>"))
        with pytest.raises(EPCUpstreamShapeError):
            _run(c.search_summaries("AA1 1AA"))

    def test_retired_envelope_raises_rather_than_reading_as_empty(self):
        """The old {"rows": []} shape must not parse as an empty result."""
        c = _client(lambda req: httpx.Response(200, json={"rows": []}))
        with pytest.raises(EPCUpstreamShapeError):
            _run(c.search_summaries("AA1 1AA"))

    def test_unconfigured_raises_without_any_request(self):
        called = []

        def handler(request):
            called.append(request.url.path)
            return httpx.Response(200, json=SEARCH_BODY)

        c = _client(handler, token=None)
        c._legacy_email = c._legacy_api_key = None
        with pytest.raises(EPCConfigurationError):
            _run(c.search_summaries("AA1 1AA"))
        assert called == [], "no request may be made without a credential"

    def test_legacy_credentials_alone_are_not_a_fallback(self):
        """Never silently ignore legacy creds while reporting as configured."""
        c = _client(lambda req: httpx.Response(200, json=SEARCH_BODY), token=None)
        c._legacy_email, c._legacy_api_key = "a@b.c", "key"
        assert c.is_configured() is False
        with pytest.raises(EPCConfigurationError) as exc:
            _run(c.search_summaries("AA1 1AA"))
        assert "EPC_API_TOKEN" in str(exc.value)


class TestGenuineAbsenceUnchanged:
    def test_upstream_404_is_absence_not_failure(self):
        c = _client(lambda req: httpx.Response(
            404, json={"data": {"error": "No certificates could be found for that query"}}))
        assert _run(c.search_summaries("AA1 1AA")).results == []
        assert _run(c.get_certificate("1111-2222-3333-4444-5555")) is None

    def test_real_rows_still_parse(self):
        def handler(request):
            if request.url.path.endswith("/certificate"):
                return httpx.Response(200, json=CERT_BODY)
            return httpx.Response(200, json=SEARCH_BODY)

        c = _client(handler)
        page = _run(c.search_summaries("AA1 1AA"))
        assert len(page.results) == 1
        assert page.results[0].current_energy_efficiency_band == "C"

        data = _run(c.get_certificate("1111-2222-3333-4444-5555"))
        assert data.rating == "C" and data.score == 72 and data.floor_area == 55.5

    def test_no_matching_address_is_explicit_not_arbitrary(self):
        """A non-match must never silently return a neighbour's certificate."""
        from property_core.epc.errors import EPCAmbiguousMatchError

        c = _client(lambda req: httpx.Response(200, json=SEARCH_BODY))
        with pytest.raises(EPCAmbiguousMatchError):
            _run(c.search_by_postcode("AA1 1AA", address="999 NOWHERE LANE"))


class TestErrorSemantics:
    def test_upstream_error_names_the_cause(self):
        c = _client(lambda req: httpx.Response(503, text="down"))
        with pytest.raises(EPCUpstreamError) as exc:
            _run(c.search_summaries("AA1 1AA"))
        assert "503" in str(exc.value)

    def test_errors_are_not_valueerror_subclasses(self):
        for cls in (EPCUpstreamError, EPCConfigurationError,
                    EPCAuthenticationError, EPCRateLimitError):
            assert not issubclass(cls, ValueError), f"{cls.__name__} must not read as caller error"


class TestEnrichmentDegradesGracefully:
    def test_one_failing_postcode_does_not_abort_the_batch(self):
        from property_core.enrichment import enrich_comps_with_epc
        from property_core.models.ppd import PPDTransaction

        good_rows = {
            "data": [{**SEARCH_BODY["data"][0], "addressLine1": "10 Good Street"}],
            "pagination": SEARCH_BODY["pagination"],
        }

        def handler(request):
            if request.url.path.endswith("/certificate"):
                return httpx.Response(200, json=CERT_BODY)
            if "BB2" in str(request.url):
                return httpx.Response(503, text="upstream down")
            return httpx.Response(200, json=good_rows)

        comps = [
            PPDTransaction(transaction_id="1", price=200000, postcode="AA1 1AA",
                           paon="10", street="GOOD STREET"),
            PPDTransaction(transaction_id="2", price=300000, postcode="BB2 2BB",
                           paon="20", street="BAD STREET"),
        ]
        result = _run(enrich_comps_with_epc(comps, epc_client=_client(handler)))
        assert result[0].epc_rating == "C", "a healthy postcode must survive a sibling failure"
        assert result[1].epc_rating is None


class TestRestBoundary:
    @pytest.fixture()
    def client(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.v1 import epc as epc_router

        monkeypatch.setattr(epc_router, "_client",
                            _client(lambda req: httpx.Response(503, text="down")))
        app = FastAPI()
        app.include_router(epc_router.router, prefix="/v1")
        return TestClient(app, raise_server_exceptions=False)

    def test_search_returns_503_not_404(self, client):
        r = client.get("/v1/epc/search", params={"postcode": "AA1 1AA"})
        assert r.status_code == 503, "an outage must not read as 'not found'"

    def test_certificate_returns_503_not_404(self, client):
        assert client.get("/v1/epc/certificate/1111-2222-3333-4444-5555").status_code == 503

    def test_search_area_returns_503_not_empty_200(self, client):
        r = client.get("/v1/epc/search-area", params={"postcode": "AA1 1AA"})
        assert r.status_code == 503, "an outage must never render as a zero-count summary"

    def test_genuine_absence_still_404s(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.v1 import epc as epc_router

        monkeypatch.setattr(epc_router, "_client", _client(lambda req: httpx.Response(
            404, json={"data": {"error": "No certificates could be found for that query"}})))
        app = FastAPI()
        app.include_router(epc_router.router, prefix="/v1")
        c = TestClient(app, raise_server_exceptions=False)
        assert c.get("/v1/epc/search", params={"postcode": "AA1 1AA"}).status_code == 404
