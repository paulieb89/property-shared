"""EPC upstream failures must not be reported as "no certificate exists".

Context: the API host hardcoded in EPCClient.BASE_URL was retired and now 301s
to a GOV.UK landing page. Because every failure was caught by a broad
`except (httpx.HTTPError, KeyError, ValueError)` and turned into None/[], the
deployed product answered "No EPC certificate found" for every postcode in
England and Wales, and the area endpoint returned HTTP 200 with count: 0.

The distinction these tests pin is narrow and deliberate:
  * upstream reachable, genuinely nothing lodged  -> None / []   (unchanged)
  * upstream unreachable/erroring/misconfigured   -> EPCUpstreamError

Migrating to the replacement API is explicitly NOT in scope here. The goal is
that the system stops asserting a falsehood.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from property_core.epc_client import EPCClient, EPCUpstreamError


def _client(handler, *, configured=True):
    c = EPCClient(email="t@example.com" if configured else None,
                  api_key="k" if configured else None)
    c._transport = httpx.MockTransport(handler)  # honoured by the client under test
    return c


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# Upstream failure must raise, not return "no data"
# --------------------------------------------------------------------------


class TestUpstreamFailuresRaise:
    @pytest.mark.parametrize(
        "status",
        [301, 302, 400, 401, 403, 404, 429, 500, 502, 503],
    )
    def test_non_success_status_raises(self, status):
        """A redirect is the live failure mode — the retired host 301s."""
        c = _client(lambda req: httpx.Response(status, text="nope"))
        with pytest.raises(EPCUpstreamError):
            _run(c.search_all_by_postcode("NG7 1FN"))
        with pytest.raises(EPCUpstreamError):
            _run(c.search_by_postcode("NG7 1FN"))
        with pytest.raises(EPCUpstreamError):
            _run(c.get_certificate("abc"))

    def test_network_error_raises(self):
        def boom(request):
            raise httpx.ConnectError("dns failure", request=request)

        c = _client(boom)
        with pytest.raises(EPCUpstreamError):
            _run(c.search_all_by_postcode("NG7 1FN"))

    def test_malformed_json_raises(self):
        c = _client(lambda req: httpx.Response(200, text="<html>not json</html>"))
        with pytest.raises(EPCUpstreamError):
            _run(c.search_all_by_postcode("NG7 1FN"))

    def test_unexpected_envelope_raises(self):
        """The replacement API returns {"data": [...]}, not {"rows": [...]}.

        Silently reading .get("rows", []) off a foreign envelope is exactly how
        a migrated-but-unadapted upstream would look like an empty result.
        """
        c = _client(lambda req: httpx.Response(200, json={"data": [{"x": 1}], "pagination": {}}))
        with pytest.raises(EPCUpstreamError):
            _run(c.search_all_by_postcode("NG7 1FN"))

    def test_unconfigured_raises_not_empty(self):
        """Missing credentials is an operator error, not an absence of data."""
        c = _client(lambda req: httpx.Response(200, json={"rows": []}), configured=False)
        with pytest.raises(EPCUpstreamError):
            _run(c.search_all_by_postcode("NG7 1FN"))
        with pytest.raises(EPCUpstreamError):
            _run(c.get_certificate("abc"))


# --------------------------------------------------------------------------
# Genuine absence must still be absence
# --------------------------------------------------------------------------


class TestGenuineAbsenceUnchanged:
    def test_empty_rows_returns_empty_list(self):
        c = _client(lambda req: httpx.Response(200, json={"rows": []}))
        assert _run(c.search_all_by_postcode("NG7 1FN")) == []

    def test_empty_rows_returns_none_for_single_lookups(self):
        c = _client(lambda req: httpx.Response(200, json={"rows": []}))
        assert _run(c.search_by_postcode("NG7 1FN")) is None
        assert _run(c.get_certificate("abc")) is None

    def test_real_rows_still_parse(self):
        row = {
            "lmk-key": "abc123",
            "address": "1 TEST STREET",
            "postcode": "NG7 1FN",
            "current-energy-rating": "C",
            "current-energy-efficiency": "72",
            "total-floor-area": "55.5",
        }
        c = _client(lambda req: httpx.Response(200, json={"rows": [row]}))
        certs = _run(c.search_all_by_postcode("NG7 1FN"))
        assert len(certs) == 1
        assert certs[0].rating == "C" and certs[0].score == 72

    def test_address_matching_no_match_is_absence_not_failure(self):
        row = {"lmk-key": "k", "address": "1 OTHER STREET", "current-energy-rating": "C"}
        c = _client(lambda req: httpx.Response(200, json={"rows": [row]}))
        assert _run(c.search_by_postcode("NG7 1FN", address="999 NOWHERE LANE")) is None


# --------------------------------------------------------------------------
# The error must be distinguishable and actionable
# --------------------------------------------------------------------------


class TestErrorSemantics:
    def test_error_message_names_the_upstream_and_cause(self):
        c = _client(lambda req: httpx.Response(301, headers={"Location": "https://example.gov.uk/"}))
        with pytest.raises(EPCUpstreamError) as exc:
            _run(c.search_all_by_postcode("NG7 1FN"))
        msg = str(exc.value)
        assert "EPC" in msg
        assert "301" in msg or "redirect" in msg.lower()

    def test_is_not_a_valueerror_subclass_that_would_read_as_bad_input(self):
        """Must not be mistaken for caller error (which would map to 4xx)."""
        assert not issubclass(EPCUpstreamError, ValueError)


# --------------------------------------------------------------------------
# Enrichment must degrade per-postcode, not lose the whole batch
# --------------------------------------------------------------------------


class TestEnrichmentDegradesGracefully:
    def test_one_failing_postcode_does_not_abort_the_batch(self):
        """asyncio.gather without return_exceptions=True loses everything.

        With EPC now raising, an un-hardened gather would 500 every
        comps?enrich_epc=true request while the upstream is down.
        """
        from property_core.enrichment import enrich_comps_with_epc
        from property_core.models.ppd import PPDTransaction

        good_row = {
            "lmk-key": "k", "address": "10 GOOD STREET", "postcode": "AA1 1AA",
            "current-energy-rating": "B", "current-energy-efficiency": "85",
            "total-floor-area": "50",
        }

        def handler(request):
            if "BB2" in str(request.url):
                return httpx.Response(503, text="upstream down")
            return httpx.Response(200, json={"rows": [good_row]})

        comps = [
            PPDTransaction(transaction_id="1", price=200000, postcode="AA1 1AA",
                           paon="10", street="GOOD STREET"),
            PPDTransaction(transaction_id="2", price=300000, postcode="BB2 2BB",
                           paon="20", street="BAD STREET"),
        ]
        client = _client(handler)

        result = _run(enrich_comps_with_epc(comps, epc_client=client))

        # The healthy postcode is still enriched...
        assert result[0].epc_rating == "B", "successful postcode must survive a sibling failure"
        # ...and the failing one is simply un-enriched, not fatal.
        assert result[1].epc_rating is None


# --------------------------------------------------------------------------
# REST boundary: an outage must be 503, never 404 or an empty 200
# --------------------------------------------------------------------------


class TestRestBoundary:
    @pytest.fixture()
    def client(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.v1 import epc as epc_router

        dead = _client(lambda req: httpx.Response(301, headers={"Location": "https://gov.uk/"}))
        monkeypatch.setattr(epc_router, "_client", dead)
        app = FastAPI()
        app.include_router(epc_router.router, prefix="/v1")
        return TestClient(app, raise_server_exceptions=False)

    def test_search_returns_503_not_404(self, client):
        r = client.get("/v1/epc/search", params={"postcode": "NG7 1FN"})
        assert r.status_code == 503, f"outage must not read as 'not found' (got {r.status_code})"
        assert "unavailable" in r.json()["detail"].lower()

    def test_certificate_returns_503_not_404(self, client):
        r = client.get("/v1/epc/certificate/abc123")
        assert r.status_code == 503

    def test_search_area_returns_503_not_empty_200(self, client):
        """The worst failure mode: a 200 with count:0 looks like real data."""
        r = client.get("/v1/epc/search-area", params={"postcode": "NG7 1FN"})
        assert r.status_code == 503, "an outage must never render as a zero-count summary"

    def test_genuine_absence_still_404s(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.v1 import epc as epc_router

        empty = _client(lambda req: httpx.Response(200, json={"rows": []}))
        monkeypatch.setattr(epc_router, "_client", empty)
        app = FastAPI()
        app.include_router(epc_router.router, prefix="/v1")
        c = TestClient(app, raise_server_exceptions=False)

        assert c.get("/v1/epc/search", params={"postcode": "NG7 1FN"}).status_code == 404
        area = c.get("/v1/epc/search-area", params={"postcode": "NG7 1FN"})
        assert area.status_code == 200 and area.json()["summary"]["count"] == 0
