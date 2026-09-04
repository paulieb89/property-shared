"""Worst-case upstream call budgets, asserted exactly.

The retired API let callers pull full rows for a whole postcode in one request.
The replacement cannot, so every path that used to be one call is now either a
summary call, a certificate call, or an explicit refusal. These budgets exist so
that "restored" never quietly means "N+1".
"""

from __future__ import annotations

import asyncio
from collections import Counter

import httpx
import pytest

from property_core.epc.codebook import EPCCodebook
from property_core.epc.errors import EPCAmbiguousMatchError
from property_core.epc_client import EPCClient

from tests.test_epc_source_models import CERT_DOC, PAGINATION, SEARCH_ROW


class CountingTransport(httpx.MockTransport):
    """Counts requests by endpoint family so budgets can be asserted."""

    def __init__(self, *, rows=None, codebook_ok=True):
        self.counts: Counter = Counter()
        self.rows = rows if rows is not None else [SEARCH_ROW]
        self.codebook_ok = codebook_ok

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/domestic/search"):
                self.counts["search"] += 1
                return httpx.Response(200, json={"data": self.rows,
                                                 "pagination": {**PAGINATION,
                                                                "totalRecords": len(self.rows)}})
            if path.endswith("/certificate"):
                self.counts["certificate"] += 1
                return httpx.Response(200, json={"data": CERT_DOC})
            if "/codes/info" in path:
                self.counts["codebook"] += 1
                if not self.codebook_ok:
                    return httpx.Response(503, text="down")
                return httpx.Response(200, json={"data": [
                    {"key": "4", "values": [{"value": "Mid-Terrace",
                                             "schemaVersion": "RdSAP-Schema-20.0.0",
                                             "assessmentType": "RdSAP"}]}]})
            self.counts["other"] += 1
            return httpx.Response(404, json={"data": {"error": "not found"}})

        super().__init__(handler)


def _client(transport, codebook=None):
    c = EPCClient(token="t")
    c._transport = transport
    c._codebook = codebook if codebook is not None else EPCCodebook(transport=transport)
    return c


def _run(coro):
    return asyncio.run(coro)


class TestBudgets:
    def test_direct_certificate_cold_is_one_plus_at_most_three_codebook_calls(self):
        t = CountingTransport()
        c = _client(t)
        _run(c.get_certificate("1111-2222-3333-4444-5555"))
        assert t.counts["certificate"] == 1
        assert t.counts["codebook"] <= 3, "only built_form, property_type, tenure in v1.14.0"
        assert t.counts["search"] == 0

    def test_direct_certificate_warm_is_one_call(self):
        t = CountingTransport()
        book = EPCCodebook(transport=t)
        c = _client(t, codebook=book)
        _run(c.get_certificate("1111-2222-3333-4444-5555"))
        before = t.counts["codebook"]
        t.counts["certificate"] = 0
        _run(c.get_certificate("1111-2222-3333-4444-5555"))
        assert t.counts["certificate"] == 1
        assert t.counts["codebook"] == before, "codebook must be cached, not re-fetched"

    def test_summary_search_is_one_call_and_no_detail_calls(self):
        t = CountingTransport(rows=[SEARCH_ROW] * 3)
        c = _client(t)
        _run(c.search_summaries("AA1 1AA"))
        assert t.counts["search"] == 1
        assert t.counts["certificate"] == 0, "summary search must never fan out"

    def test_unique_address_lookup_is_one_search_plus_one_certificate(self):
        t = CountingTransport(rows=[SEARCH_ROW])
        c = _client(t)
        _run(c.search_by_postcode("AA1 1AA", address="Flat 2, 42 Example Boulevard"))
        assert t.counts["search"] == 1
        assert t.counts["certificate"] == 1

    def test_ambiguous_address_lookup_makes_zero_certificate_calls(self):
        rows = [{**SEARCH_ROW, "certificateNumber": "0001-0000-0000-0000-0000",
                 "addressLine1": "Flat 1", "addressLine2": "24 Alexandra Road"},
                {**SEARCH_ROW, "certificateNumber": "0002-0000-0000-0000-0000",
                 "addressLine1": "Flat 3", "addressLine2": "24 Alexandra Road"}]
        t = CountingTransport(rows=rows)
        c = _client(t)
        with pytest.raises(EPCAmbiguousMatchError):
            _run(c.search_by_postcode("AA1 1AA", address="24 ALEXANDRA ROAD"))
        assert t.counts["search"] == 1
        assert t.counts["certificate"] == 0, "never fetch an arbitrary certificate on ambiguity"

    def test_area_summary_is_one_bounded_search_and_zero_certificate_calls(self):
        t = CountingTransport(rows=[SEARCH_ROW] * 29)
        c = _client(t)
        _run(c.area_summary("AA1 1AA"))
        assert t.counts["search"] == 1
        assert t.counts["certificate"] == 0, "no N+1 to compute area statistics"


class TestCodebookBudget:
    def test_table_fetched_at_most_once_per_code_and_schema(self):
        t = CountingTransport()
        book = EPCCodebook(transport=t)
        for _ in range(10):
            _run(book.label("built_form", "4", "RdSAP-Schema-20.0.0"))
        assert t.counts["codebook"] == 1, "one table fetch per (code, schemaVersion)"

    def test_schema_version_is_sent_verbatim(self):
        """Proven live 11/11 across RdSAP and SAP: no normalisation."""
        seen = []

        def handler(request):
            seen.append(dict(request.url.params))
            return httpx.Response(200, json={"data": []})

        book = EPCCodebook(transport=httpx.MockTransport(handler))
        _run(book.label("built_form", "4", "RdSAP-Schema-20.0.0"))
        assert seen[0].get("schemaVersion") == "RdSAP-Schema-20.0.0"

    def test_codebook_outage_is_circuit_broken_not_retried_per_certificate(self):
        t = CountingTransport(codebook_ok=False)
        book = EPCCodebook(transport=t)
        c = _client(t, codebook=book)
        for _ in range(5):
            _run(c.get_certificate("1111-2222-3333-4444-5555"))
        assert t.counts["codebook"] <= 3, "outage must trip a breaker, not retry per certificate"

    def test_codebook_outage_does_not_fail_certificate_retrieval(self):
        t = CountingTransport(codebook_ok=False)
        c = _client(t, codebook=EPCCodebook(transport=t))
        data = _run(c.get_certificate("1111-2222-3333-4444-5555"))
        assert data is not None
        assert data.score == 62, "v1 projection still works with labels absent"
        assert data.built_form is None, "label unavailable, never an integer"


class TestEnrichmentBudget:
    def test_one_search_per_postcode_and_one_certificate_per_selected_match(self):
        from property_core.enrichment import enrich_comps_with_epc
        from property_core.models.ppd import PPDTransaction

        rows = [{**SEARCH_ROW, "addressLine1": "10", "addressLine2": "Good Street"}]
        t = CountingTransport(rows=rows)
        c = _client(t)
        comps = [
            PPDTransaction(transaction_id="1", price=1, postcode="AA1 1AA",
                           paon="10", street="GOOD STREET"),
            PPDTransaction(transaction_id="2", price=2, postcode="AA1 1AA",
                           paon="10", street="GOOD STREET"),
        ]
        _run(enrich_comps_with_epc(comps, epc_client=c))
        assert t.counts["search"] == 1, "one search per DISTINCT postcode"
        assert t.counts["certificate"] <= 1, "certificate cached by certificate number"

    def test_ambiguity_leaves_enrichment_unavailable_not_arbitrary(self):
        from property_core.enrichment import enrich_comps_with_epc
        from property_core.models.ppd import PPDTransaction

        rows = [{**SEARCH_ROW, "certificateNumber": "0001-0000-0000-0000-0000",
                 "addressLine1": "Flat 1", "addressLine2": "24 Alexandra Road"},
                {**SEARCH_ROW, "certificateNumber": "0002-0000-0000-0000-0000",
                 "addressLine1": "Flat 3", "addressLine2": "24 Alexandra Road"}]
        t = CountingTransport(rows=rows)
        c = _client(t)
        comps = [PPDTransaction(transaction_id="1", price=1, postcode="AA1 1AA",
                                street="ALEXANDRA ROAD", paon="24")]
        out = _run(enrich_comps_with_epc(comps, epc_client=c))
        assert out[0].epc_rating is None, "ambiguity must not attach an arbitrary EPC"
        assert t.counts["certificate"] == 0
