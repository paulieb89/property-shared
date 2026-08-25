"""Regressions for defects adversarial review found despite a green suite.

Three were reproduced directly against the pre-fix branch:
  1. a lone `Flat 3` candidate was returned for a `Flat 2` query
  2. an upstream 403 surfaced as REST HTTP 500
  3. missing `totalRecords` surfaced as REST HTTP 200 with `count: 0`

The rest close gaps the same review identified.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from property_core.epc.errors import (
    EPCAmbiguousMatchError,
    EPCAuthenticationError,
    EPCConfigurationError,
    EPCInvalidQueryError,
    EPCRateLimitError,
    EPCUnsupportedOperationError,
    EPCUpstreamError,
)
from property_core.epc.selection import select_candidate
from property_core.epc.source_models import EPCSearchRow
from property_core.epc_client import EPCClient

from tests.test_epc_honest_failure import CERT_BODY, SEARCH_BODY


def _run(c):
    return asyncio.run(c)


def _row(cert_no, line1, line2=None, uprn=None):
    return EPCSearchRow.from_source({
        "certificateNumber": cert_no, "addressLine1": line1, "addressLine2": line2,
        "uprn": uprn, "postcode": "AA1 1AA", "currentEnergyEfficiencyBand": "D",
        "registrationDate": "2023-01-01", "schemaType": "RdSAP-Schema-20.0.0",
    })


class TestUnitAgreementWithSingleCandidate:
    """REPRODUCED: one remaining candidate is not evidence it is the right one."""

    def test_single_wrong_unit_candidate_is_refused(self):
        rows = [_row("0003", "Flat 3", "24 Alexandra Road")]
        with pytest.raises(EPCAmbiguousMatchError) as exc:
            select_candidate(rows, address="Flat 2, 24 Alexandra Road")
        assert "unit" in str(exc.value).lower()

    def test_single_correct_unit_candidate_is_accepted(self):
        rows = [_row("0002", "Flat 2", "24 Alexandra Road")]
        got = select_candidate(rows, address="Flat 2, 24 Alexandra Road")
        assert got.row.certificate_number == "0002"

    def test_unit_query_against_unitless_single_candidate_is_refused(self):
        rows = [_row("0001", "24 Alexandra Road")]
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate(rows, address="Flat 2, 24 Alexandra Road")

    def test_unitless_query_against_a_block_is_refused(self):
        rows = [_row("0001", "Flat 1", "24 Alexandra Road")]
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate(rows, address="24 Alexandra Road")


class TestSuppliedUprnMismatch:
    def test_uprn_miss_does_not_fall_back_to_address_evidence(self):
        rows = [_row("0002", "Flat 2", "24 Alexandra Road", uprn="100000000001")]
        with pytest.raises(EPCAmbiguousMatchError) as exc:
            select_candidate(rows, uprn="999999999999", address="Flat 2, 24 Alexandra Road")
        assert "refusing to fall back" in str(exc.value)

    def test_uprn_hit_is_identity_confidence(self):
        rows = [_row("0002", "Flat 2", "24 Alexandra Road", uprn="100000000001")]
        got = select_candidate(rows, uprn="100000000001")
        assert got.method == "uprn" and got.confidence == 100


class TestMatchScoreHonesty:
    def test_structured_narrowing_no_longer_selects_at_all(self):
        """Same unit and street, different wording ("Apartment" vs "Flat").

        This used to select at confidence 80. The structured acceptance path is
        gone in v1.14: partial agreement repeatedly selected a different
        property, so only identity evidence is accepted now. Refusing is
        recoverable — the caller browses summaries — whereas attaching another
        property's certificate is not.
        """
        rows = [_row("0002", "Flat 2", "24 Alexandra Road"),
                _row("0007", "Flat 7", "24 Alexandra Road")]
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate(rows, address="Apartment 2, 24 Alexandra Road")

    def test_selection_only_ever_reports_identity_confidence(self):
        rows = [_row("0002", "Flat 2", "24 Alexandra Road")]
        got = select_candidate(rows, address="Flat 2, 24 Alexandra Road")
        assert got.method == "exact_address" and got.confidence == 100

    def test_enrichment_records_the_match_method(self):
        from property_core.enrichment import enrich_comps_with_epc
        from property_core.models.ppd import PPDTransaction

        rows = {"data": [{**SEARCH_BODY["data"][0], "addressLine1": "10 Good Street"}],
                "pagination": SEARCH_BODY["pagination"]}

        def handler(request):
            if request.url.path.endswith("/certificate"):
                return httpx.Response(200, json=CERT_BODY)
            return httpx.Response(200, json=rows)

        c = EPCClient(token="t"); c._transport = httpx.MockTransport(handler)
        comps = [PPDTransaction(transaction_id="1", price=1, postcode="AA1 1AA",
                                paon="10", street="GOOD STREET")]
        out = _run(enrich_comps_with_epc(comps, epc_client=c))
        assert out[0].epc_match_method is not None
        assert out[0].epc_match_score != 100 or out[0].epc_match_method in ("uprn", "exact_address")


def _rest(handler):
    from app.api.v1 import epc as R

    c = EPCClient(token="t"); c._transport = httpx.MockTransport(handler)
    R._client = c
    app = FastAPI(); app.include_router(R.router, prefix="/v1")
    return TestClient(app, raise_server_exceptions=False)


class TestRestErrorTaxonomy:
    """REPRODUCED: 403 became 500. Every typed failure now has a real status."""

    @pytest.mark.parametrize("status,expected", [
        (403, 502),   # upstream rejected our credentials
        (401, 502),
        (429, 429),   # rate limit passes through
        (400, 400),   # caller error — NOT 503
        (503, 503),   # genuine outage
        (500, 503),
    ])
    def test_upstream_status_maps_to_a_meaningful_rest_status(self, status, expected):
        tc = _rest(lambda r: httpx.Response(status, text="x"))
        got = tc.get("/v1/epc/search", params={"postcode": "AA1 1AA"})
        assert got.status_code == expected, f"upstream {status} -> {got.status_code}"
        assert got.status_code != 500, "a typed failure must never surface as a crash"

    def test_ambiguity_is_409_not_500(self):
        body = {"data": [
            {**SEARCH_BODY["data"][0], "certificateNumber": "1", "addressLine1": "Flat 1",
             "addressLine2": "24 Alexandra Road"},
            {**SEARCH_BODY["data"][0], "certificateNumber": "2", "addressLine1": "Flat 3",
             "addressLine2": "24 Alexandra Road"}],
            "pagination": {**SEARCH_BODY["pagination"], "totalRecords": 2}}
        tc = _rest(lambda r: httpx.Response(200, json=body))
        got = tc.get("/v1/epc/search", params={"postcode": "AA1 1AA", "address": "24 Alexandra Road"})
        assert got.status_code == 409

    def test_configuration_error_is_501_not_500(self):
        from app.api.v1 import epc as R

        c = EPCClient(token=None)
        c._legacy_email, c._legacy_api_key = "a@b.c", "k"
        c._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=SEARCH_BODY))
        R._client = c
        app = FastAPI(); app.include_router(R.router, prefix="/v1")
        tc = TestClient(app, raise_server_exceptions=False)
        assert tc.get("/v1/epc/search", params={"postcode": "AA1 1AA"}).status_code == 501


class TestAreaCountNeverZeroWhenUnknown:
    """REPRODUCED: missing totalRecords became HTTP 200 with count: 0."""

    def test_missing_total_records_is_null_not_zero(self):
        body = {"data": SEARCH_BODY["data"], "pagination": {"currentPage": 1, "pageSize": 5000}}
        tc = _rest(lambda r: httpx.Response(200, json=body))
        got = tc.get("/v1/epc/search-area", params={"postcode": "AA1 1AA"})
        assert got.status_code == 200
        summary = got.json()["summary"]
        assert summary["count"] is None, "unknown must never render as zero"
        assert got.json()["complete"] is False

    def test_unavailable_stats_are_null_not_empty(self):
        tc = _rest(lambda r: httpx.Response(200, json=SEARCH_BODY))
        summary = tc.get("/v1/epc/search-area", params={"postcode": "AA1 1AA"}).json()["summary"]
        assert summary["property_type_breakdown"] is None
        assert summary["floor_area_avg"] is None


class TestWarningPropagation:
    def test_warnings_reach_the_rest_envelope(self):
        def handler(request):
            if request.url.path.endswith("/certificate"):
                return httpx.Response(200, json=CERT_BODY)
            if "/codes/info" in request.url.path:
                return httpx.Response(503, text="down")
            return httpx.Response(200, json=SEARCH_BODY)

        tc = _rest(handler)
        body = tc.get("/v1/epc/certificate/1111-2222-3333-4444-5555").json()
        warnings = body["record"]["warnings"]
        assert warnings, "codebook/no-source warnings must not be discarded"
        assert any("lodgement" in w.lower() for w in warnings)

    def test_warnings_present_on_a_plain_client_call(self):
        """to_epcdata created them; get_certificate must not drop them."""
        def handler(request):
            if request.url.path.endswith("/certificate"):
                return httpx.Response(200, json=CERT_BODY)
            return httpx.Response(503, text="down")

        c = EPCClient(token="t"); c._transport = httpx.MockTransport(handler)
        data = _run(c.get_certificate("1111-2222-3333-4444-5555"))
        assert data.warnings


class TestColdCodebookIsAsync:
    def test_cold_path_does_not_block_the_event_loop(self):
        """A sync request inside the async path would serialise concurrent work."""
        delay = 0.15

        async def slow(request):
            if "/codes/info" in request.url.path:
                await asyncio.sleep(delay)
                return httpx.Response(200, json={"data": []})
            return httpx.Response(200, json=CERT_BODY)

        async def main():
            c = EPCClient(token="t")
            c._transport = httpx.MockTransport(slow)
            started = time.perf_counter()
            await asyncio.gather(*[c.get_certificate(f"cert-{i}") for i in range(3)])
            return time.perf_counter() - started

        elapsed = asyncio.run(main())
        # Three certificates x three cold tables; if the codebook blocked the
        # loop these would serialise well past this budget.
        assert elapsed < delay * 9, f"cold path took {elapsed:.2f}s — likely blocking"
