"""Round-3 review regressions.

Reproduced on d78763d before fixing:
  1a. "12 High Street" selected the sole candidate "12 High Road" at confidence 80
      — one shared street token ("high") was treated as street agreement.
  1b. With no address and no UPRN, a lone row was returned as `sole_candidate`
      — being the only row is not evidence of identity.
  2.  A missing `totalRecords` collapsed to "no EPC data" on the MCP-app tool,
      the plain MCP tool and the CLI.
  3.  Three cold codebook tables were fetched sequentially, so at the 15s
      per-request timeout the cold certificate path could reach ~45s — past the
      30s MCP tool timeout.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from property_core.epc.codebook import EPCCodebook
from property_core.epc.errors import EPCAmbiguousMatchError
from property_core.epc.selection import select_candidate
from property_core.epc.source_models import EPCSearchRow
from property_core.epc_client import EPCClient

CERT = {"data": {
    "current_energy_efficiency_band": "D", "energy_rating_current": 62,
    "schema_type": "RdSAP-Schema-20.0.0", "built_form": 4,
    "property_type": 2, "tenure": 3,
}}
CERT_NO_SCHEMA = {"data": {k: v for k, v in CERT["data"].items() if k != "schema_type"}}


def _run(c):
    return asyncio.run(c)


def _row(cn, line1, line2=None, uprn=None):
    return EPCSearchRow.from_source({
        "certificateNumber": cn, "addressLine1": line1, "addressLine2": line2,
        "uprn": uprn, "postcode": "AA1 1AA", "currentEnergyEfficiencyBand": "D",
        "registrationDate": "2023-01-01", "schemaType": "RdSAP-Schema-20.0.0",
    })


class TestStreetAgreementMustBeExact:
    """A shared token is not a shared street."""

    @pytest.mark.parametrize("candidate,query", [
        ("12 High Road", "12 High Street"),
        ("12 High Street", "12 High Road"),
        ("5 Church Lane", "5 Church Close"),
        ("8 Victoria Park Road", "8 Victoria Road"),
    ])
    def test_partial_street_overlap_is_refused(self, candidate, query):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", candidate)], address=query)

    def test_exact_street_still_selected(self):
        got = select_candidate([_row("1", "12 High Street")], address="12 High Street")
        assert got.row.certificate_number == "1"

    def test_abbreviations_are_not_silently_equated(self):
        """Expanding 'Rd' to 'Road' would be an inference, not evidence."""
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "24 Alexandra Road")], address="24 Alexandra Rd")

    def test_address_without_a_street_name_is_refused(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "12 High Street")], address="12")


class TestNoEvidenceMeansNoSelection:
    def test_sole_candidate_without_address_or_uprn_is_refused(self):
        with pytest.raises(EPCAmbiguousMatchError) as exc:
            select_candidate([_row("1", "99 Nowhere Lane")])
        assert "no address or UPRN" in str(exc.value)

    def test_many_candidates_without_evidence_are_refused(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("1", "1 A Road"), _row("2", "2 A Road")])

    def test_uprn_alone_still_selects(self):
        rows = [_row("1", "1 A Road", uprn="100000000001")]
        assert select_candidate(rows, uprn="100000000001").method == "uprn"


class TestUnknownCountIsNotAbsence:
    """total_records None = unknown; 0 = genuinely none. Each outward surface."""

    NO_TOTAL = {"data": [{"certificateNumber": "1", "addressLine1": "X",
                          "currentEnergyEfficiencyBand": "C",
                          "schemaType": "RdSAP-Schema-20.0.0"}],
                "pagination": {"currentPage": 1, "pageSize": 5000}}
    ZERO = {"data": [], "pagination": {"totalRecords": 0, "currentPage": 1, "pageSize": 5000}}

    def _client(self, body):
        c = EPCClient(token="t")
        c._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=body))
        return c

    def _patch(self, monkeypatch, body):
        import property_core
        client = self._client(body)
        monkeypatch.setattr(property_core, "EPCClient", lambda *a, **k: client)
        return client

    def test_mcp_app_reports_unknown_not_absence(self, monkeypatch):
        import property_app.tools as T

        self._patch(monkeypatch, self.NO_TOTAL)
        result = _run(T.lookup_epc("AA1 1AA"))
        assert result.get("error") != "No EPC data", "unknown must not read as absence"
        assert result["summary"]["count"] is None
        assert result["summary"]["complete"] is False
        assert result["summary"]["warnings"]

    def test_mcp_app_still_reports_genuine_absence(self, monkeypatch):
        import property_app.tools as T

        self._patch(monkeypatch, self.ZERO)
        assert _run(T.lookup_epc("AA1 1AA")) == {"error": "No EPC data"}

    def test_plain_mcp_reports_unknown_not_absence(self, monkeypatch):
        import app.mcp.server as S

        self._patch(monkeypatch, self.NO_TOTAL)
        result = _run(S.property_epc("AA1 1AA"))
        assert result is not None, "unknown must not read as absence"
        assert result["summary"]["count"] is None
        assert result["complete"] is False
        assert result["warnings"]

    def test_plain_mcp_still_reports_genuine_absence(self, monkeypatch):
        import app.mcp.server as S

        self._patch(monkeypatch, self.ZERO)
        assert _run(S.property_epc("AA1 1AA")) is None

    def test_cli_reports_unknown_not_absence(self, monkeypatch, capsys):
        import typer
        from typer.testing import CliRunner

        import property_cli.main as M

        self._patch(monkeypatch, self.NO_TOTAL)
        monkeypatch.setattr(M, "EPCClient", lambda *a, **k: self._client(self.NO_TOTAL))
        result = CliRunner().invoke(M.app, ["epc", "search", "AA1 1AA"])
        assert result.exit_code == 0, result.output
        assert "No EPC certificates found" not in result.output
        assert "unknown, not zero" in result.output

    def test_cli_still_reports_genuine_absence(self, monkeypatch):
        from typer.testing import CliRunner

        import property_cli.main as M

        monkeypatch.setattr(M, "EPCClient", lambda *a, **k: self._client(self.ZERO))
        result = CliRunner().invoke(M.app, ["epc", "search", "AA1 1AA"])
        assert result.exit_code == 1
        assert "No EPC certificates found" in result.output


class TestCodebookConcurrencyAndBudget:
    def _transport(self, delay, counter):
        async def handler(request):
            if "/codes/info" in request.url.path:
                counter.append(request.url.params.get("code"))
                await asyncio.sleep(delay)
                return httpx.Response(200, json={"data": []})
            return httpx.Response(200, json=CERT)

        return httpx.MockTransport(handler)

    def test_cold_tables_are_fetched_concurrently(self):
        """Sequential x3 at the real 15s timeout would exceed the 30s tool limit."""
        delay, seen = 0.30, []
        c = EPCClient(token="t")
        c._transport = self._transport(delay, seen)
        c._codebook = EPCCodebook(transport=c._transport)

        started = time.perf_counter()
        _run(c.get_certificate("x"))
        elapsed = time.perf_counter() - started

        assert len(seen) == 3, f"expected 3 tables, saw {seen}"
        assert elapsed < delay * 2, (
            f"cold path took {elapsed:.2f}s for {delay}s tables — still sequential"
        )

    def test_budget_overrun_degrades_to_labels_none_with_warning(self):
        c = EPCClient(token="t")
        c._transport = self._transport(0.5, [])
        c._codebook = EPCCodebook(transport=c._transport, warm_budget=0.15)

        data = _run(c.get_certificate("x"))
        assert data.score == 62, "the certificate itself must still be returned"
        assert data.built_form is None and data.property_type is None
        assert any("budget" in w.lower() for w in data.warnings)

    def test_missing_schema_type_does_not_query_unscoped(self):
        """An unscoped lookup returns a value per schema; taking values[0] is a guess."""
        calls = []

        def handler(request):
            if "/codes/info" in request.url.path:
                calls.append(dict(request.url.params))
                return httpx.Response(200, json={"data": []})
            return httpx.Response(200, json=CERT_NO_SCHEMA)

        c = EPCClient(token="t")
        c._transport = httpx.MockTransport(handler)
        c._codebook = EPCCodebook(transport=c._transport)

        data = _run(c.get_certificate("x"))
        assert calls == [], "no codebook request may be made without a schemaVersion"
        assert data.built_form is None and data.tenure is None
        assert any("schema_type" in w for w in data.warnings)

    def test_concurrent_cold_certificates_share_the_cache(self):
        delay, seen = 0.20, []
        c = EPCClient(token="t")
        c._transport = self._transport(delay, seen)
        c._codebook = EPCCodebook(transport=c._transport)

        async def main():
            return await asyncio.gather(*(c.get_certificate(f"c{i}") for i in range(4)))

        started = time.perf_counter()
        results = _run(main())
        elapsed = time.perf_counter() - started

        assert all(r.score == 62 for r in results)
        assert elapsed < delay * 4, f"{elapsed:.2f}s — cache is not shared across calls"


class TestDeprecatedFromApiRow:
    def test_no_production_path_calls_it(self):
        """Pinned: the retired parser must stay unreferenced outside its own module."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        offenders = []
        for pkg in ("property_core", "app", "property_app", "property_cli"):
            for f in (root / pkg).rglob("*.py"):
                if f.name == "epc.py" and f.parent.name == "models":
                    continue
                if "from_api_row" in f.read_text():
                    offenders.append(str(f.relative_to(root)))
        assert offenders == [], f"from_api_row is still called by: {offenders}"

    def test_missing_rating_raises_instead_of_empty_string(self):
        from property_core.models.epc import EPCData

        with pytest.raises(ValueError, match="current-energy-rating"):
            EPCData.from_api_row({"current-energy-efficiency": "72"})

    def test_missing_score_raises_instead_of_zero(self):
        from property_core.models.epc import EPCData

        with pytest.raises(ValueError, match="current-energy-efficiency"):
            EPCData.from_api_row({"current-energy-rating": "C"})

    def test_complete_archived_row_still_parses(self):
        from property_core.models.epc import EPCData

        d = EPCData.from_api_row({
            "current-energy-rating": "C", "current-energy-efficiency": "72",
            "lmk-key": "abc", "address": "1 Test Street",
        })
        assert d.rating == "C" and d.score == 72


class TestBuildingAndUnitComparedIndependently:
    """A matching unit must never compensate for a mismatched building.

    Reproduced: query "Flat 2, 24 Alexandra Road" selected candidate
    "Flat 2, 99 Alexandra Road" at confidence 80, because a pooled set of all
    numbers intersected on the shared unit "2".
    """

    def test_same_unit_different_building_is_refused(self):
        rows = [_row("1", "Flat 2", "99 Alexandra Road")]
        with pytest.raises(EPCAmbiguousMatchError) as exc:
            select_candidate(rows, address="Flat 2, 24 Alexandra Road")
        assert "building" in str(exc.value).lower()

    def test_same_building_different_unit_is_refused(self):
        rows = [_row("1", "Flat 7", "24 Alexandra Road")]
        with pytest.raises(EPCAmbiguousMatchError) as exc:
            select_candidate(rows, address="Flat 2, 24 Alexandra Road")
        assert "unit" in str(exc.value).lower()

    def test_same_building_and_unit_is_accepted(self):
        rows = [_row("1", "Apartment 2", "24 Alexandra Road")]
        got = select_candidate(rows, address="Flat 2, 24 Alexandra Road")
        assert got.row.certificate_number == "1"
        assert got.confidence < 100

    def test_unitless_house_number_mismatch_is_refused(self):
        rows = [_row("1", "99 Alexandra Road")]
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate(rows, address="24 Alexandra Road")

    def test_unitless_house_number_match_is_accepted(self):
        rows = [_row("1", "24 Alexandra Road")]
        assert select_candidate(rows, address="24 Alexandra Road").row.certificate_number == "1"

    def test_building_only_query_does_not_match_a_flat(self):
        """"24 Alexandra Road" must not resolve to a specific flat within it."""
        rows = [_row("1", "Flat 2", "24 Alexandra Road")]
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate(rows, address="24 Alexandra Road")


class TestCodebookSingleFlight:
    """Concurrent cold callers must SHARE one fetch per (code, schemaVersion).

    Reproduced: four concurrent cold certificates issued 12 requests — four each
    for built_form, property_type and tenure. An elapsed-time assertion cannot
    catch this, because duplicate concurrent requests also finish quickly.
    """

    def _client(self, delay, seen, *, budget=8.0):
        async def handler(request):
            if "/codes/info" in request.url.path:
                seen.append(request.url.params.get("code"))
                await asyncio.sleep(delay)
                return httpx.Response(200, json={"data": []})
            return httpx.Response(200, json=CERT)

        c = EPCClient(token="t")
        c._transport = httpx.MockTransport(handler)
        c._codebook = EPCCodebook(transport=c._transport, warm_budget=budget)
        return c

    def test_concurrent_cold_calls_issue_exactly_one_request_per_table(self):
        from collections import Counter

        seen = []
        c = self._client(0.2, seen)

        async def main():
            return await asyncio.gather(*(c.get_certificate(f"c{i}") for i in range(4)))

        results = _run(main())
        counts = Counter(seen)
        assert all(r.score == 62 for r in results)
        assert len(seen) == 3, f"expected 3 requests (one per table), saw {len(seen)}: {dict(counts)}"
        assert set(counts.values()) == {1}, f"duplicate fetches per table: {dict(counts)}"

    def test_a_cancelled_caller_does_not_corrupt_the_shared_fetch(self):
        """One caller timing out must not tear down the fetch others await."""
        from collections import Counter

        seen = []
        # Budget shorter than the fetch, so the first caller's warm times out.
        c = self._client(0.25, seen, budget=0.05)

        async def main():
            impatient = await c.get_certificate("impatient")
            # Second call runs after the first gave up; the shared task should
            # have completed rather than been cancelled mid-flight.
            await asyncio.sleep(0.35)
            patient = await c.get_certificate("patient")
            return impatient, patient

        impatient, patient = _run(main())
        assert impatient.score == 62, "certificate must still be returned"
        assert any("budget" in w.lower() for w in impatient.warnings)
        # The shared fetch completed and populated the cache, so the later call
        # does not re-request the same tables.
        assert set(Counter(seen).values()) == {1}, f"tables refetched: {dict(Counter(seen))}"
