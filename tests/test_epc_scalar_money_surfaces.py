"""A legacy SAP scalar certificate must survive every outward surface.

The v1.14.0 defect was not confined to the parser: because EPCUpstreamShapeError
subclasses EPCUpstreamError, a bare-int cost field surfaced as REST 503 and as an
MCP tool error on certificate lookup, exact-address search, comps enrichment and
the report service. These tests drive each of those paths with a real SAP-13.0
fixture, and assert the aggregated currency warning survives without turning into
per-field spam.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from property_core.epc_client import EPCClient

FIXTURES = Path(__file__).parent / "fixtures" / "epc"
CERT_NO = "0000-0000-0000-0000-0001"
POSTCODE = "AA1 1AA"
ADDRESS = "1 Example Street"

SCALAR = json.loads((FIXTURES / "sap_schema_13_0.json").read_text())
MODERN = json.loads((FIXTURES / "rdsap_schema_20_0_0.json").read_text())


def _summary_body():
    return {
        "data": [{
            "certificateNumber": CERT_NO, "addressLine1": ADDRESS, "addressLine2": None,
            "addressLine3": None, "addressLine4": None, "uprn": None, "postcode": POSTCODE,
            "currentEnergyEfficiencyBand": "D", "registrationDate": "2012-01-01",
            "schemaType": "SAP-Schema-13.0", "postTown": None, "council": None,
            "constituency": None,
        }],
        "pagination": {"currentPage": 1, "pageSize": 5000, "totalRecords": 1, "totalPages": 1},
    }


def _client(cert_body=SCALAR):
    """EPCClient whose upstream returns the scalar-cost certificate."""
    def handler(request):
        p = request.url.path
        if p.endswith("/certificate"):
            return httpx.Response(200, json=cert_body)
        if "/codes/info" in p:
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json=_summary_body())

    c = EPCClient(token="t")
    c._transport = httpx.MockTransport(handler)
    return c


def _currency_warnings(warnings):
    return [w for w in (warnings or []) if "currenc" in w.lower()]


def _assert_disclosed_once(warnings, where):
    hits = _currency_warnings(warnings)
    assert len(hits) == 1, f"{where}: expected 1 aggregated warning, got {len(hits)}: {hits}"
    assert "gbp" in hits[0].lower(), f"{where}: warning does not name GBP"


class TestCoreClientPaths:
    def test_certificate_lookup(self):
        data = asyncio.run(_client().get_certificate(CERT_NO))
        assert data.heating_cost_current == 625
        assert data.lighting_cost_potential == 37
        _assert_disclosed_once(data.warnings, "get_certificate")

    def test_exact_address_search(self):
        data = asyncio.run(_client().search_by_postcode(POSTCODE, address=ADDRESS))
        assert data is not None, "scalar-cost certificate was dropped by search"
        assert data.heating_cost_current == 625
        _assert_disclosed_once(data.warnings, "search_by_postcode")

    def test_modern_object_costs_emit_no_currency_warning(self):
        data = asyncio.run(_client(MODERN).get_certificate(CERT_NO))
        assert data.heating_cost_current is not None
        assert _currency_warnings(data.warnings) == []


class TestEnrichmentAndReport:
    def test_comps_enrichment_attaches_the_certificate(self):
        from property_core.enrichment import enrich_comps_with_epc
        from property_core.models.ppd import PPDTransaction

        comps = [PPDTransaction(transaction_id="1", price=250000, postcode=POSTCODE,
                                paon="1", street="EXAMPLE STREET")]
        out = asyncio.run(enrich_comps_with_epc(comps, epc_client=_client()))
        assert out[0].epc_match is not None, "enrichment dropped a scalar-cost certificate"
        assert out[0].epc_rating == "D"

    def test_report_service_epc_step_succeeds(self):
        """_fetch_epc_data() swallows failures into success=False — the v1.14.0
        defect would have shown up as an EPC-less report, not an exception."""
        from property_core.report_service import PropertyReportService

        svc = PropertyReportService(epc_client=_client())
        result = asyncio.run(svc._fetch_epc_data(POSTCODE, ADDRESS))
        assert result["success"] is True, f"report EPC step failed: {result.get('error')}"
        ep = result.get("energy_performance")
        assert ep is not None, "report produced no EnergyPerformance block"
        # The report model flattens the cost fields; the scalar amounts must
        # reach it rather than being lost to a parse failure upstream.
        assert ep.heating_cost == 625
        assert ep.hot_water_cost == 136
        assert ep.lighting_cost == 58


def _rest(client):
    from app.api.v1 import epc as R

    R._client = client
    app = FastAPI()
    app.include_router(R.router, prefix="/v1")
    return TestClient(app, raise_server_exceptions=False)


class TestRestSurface:
    def test_certificate_endpoint_is_200_not_503(self):
        got = _rest(_client()).get(f"/v1/epc/certificate/{CERT_NO}")
        assert got.status_code == 200, f"regression: {got.status_code} {got.text[:200]}"
        body = got.json()["record"]
        assert body["heating_cost_current"] == 625
        _assert_disclosed_once(body["warnings"], "REST certificate")

    def test_search_endpoint_is_200_not_503(self):
        got = _rest(_client()).get("/v1/epc/search",
                                   params={"postcode": POSTCODE, "address": ADDRESS})
        assert got.status_code == 200, f"regression: {got.status_code} {got.text[:200]}"
        assert got.json()["record"]["heating_cost_current"] == 625


class TestMcpSurfaces:
    def test_plain_mcp_epc_certificate(self):
        from app.mcp import server as S

        S_client = _client()
        import property_core
        orig = property_core.EPCClient
        property_core.EPCClient = lambda *a, **k: S_client
        try:
            fn = S.epc_certificate.fn if hasattr(S.epc_certificate, "fn") else S.epc_certificate
            result = asyncio.run(fn(CERT_NO))
        finally:
            property_core.EPCClient = orig
        assert result is not None, "plain MCP dropped a scalar-cost certificate"
        assert result["heating_cost_current"] == 625
        _assert_disclosed_once(result.get("warnings"), "plain MCP")

    def test_mcp_app_epc_certificate(self):
        from property_app import tools as T

        app_client = _client()
        import property_core
        orig = property_core.EPCClient
        property_core.EPCClient = lambda *a, **k: app_client
        try:
            result = asyncio.run(T.fetch_epc_certificate(CERT_NO))
        finally:
            property_core.EPCClient = orig
        assert result is not None, "MCP app dropped a scalar-cost certificate"
        assert result["heating_cost_current"] == 625
        _assert_disclosed_once(result.get("warnings"), "MCP app")
