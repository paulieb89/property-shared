"""PR 2 — the comps completeness warning must survive to every consumer.

A warning that exists only on the core model is not a contract. It has to reach
REST, both MCP servers, the CLI, and the derived consumers (yield, report,
dashboards) wherever they expose comps.

No snapshot provenance fields are added in PR 2 -- only `warnings`.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from property_core.models.ppd import PPDTransaction
from property_core.ppd_client import PricePaidDataClient, SearchPage
from property_core.provenance import TransportEvidence


def _saturated_page(n: int = 3) -> SearchPage:
    """A full upstream window: completeness unknown, so a warning is required."""
    rows = [
        PPDTransaction(
            transaction_id=f"{{W-{i}}}", price=250000 + i, date="2025-06-01",
            postcode="B5 4BX", property_type="F", estate_type="L",
            transaction_category="A", new_build=False, paon=str(i),
            street="ESSEX STREET", town="BIRMINGHAM", county="WEST MIDLANDS",
            district="BIRMINGHAM",
        )
        for i in range(n)
    ]
    return SearchPage(
        transactions=rows,
        evidence=TransportEvidence(raw_bindings_returned=150, fetch_limit=150),
    )


@pytest.fixture
def saturated():
    with patch.object(PricePaidDataClient, "search_with_evidence",
                      return_value=_saturated_page()):
        yield


def _has_completeness_warning(warnings) -> bool:
    joined = " ".join(warnings or []).lower()
    return "incomplete" in joined or "exhaust" in joined


# --------------------------------------------------------------------------

def test_core_comps_carries_the_warning(saturated):
    from property_core import PPDService

    resp = PPDService().comps(postcode="B5 4BX", search_level="sector",
                              auto_escalate=False)
    assert _has_completeness_warning(resp.warnings), resp.warnings


def test_rest_comps_exposes_the_warning(saturated):
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/v1/ppd/comps?postcode=B5%204BX&months=24&limit=50")
    assert r.status_code == 200, r.text
    assert _has_completeness_warning(r.json().get("warnings")), r.json().get("warnings")


def test_plain_mcp_property_comps_exposes_the_warning(saturated):
    from app.mcp.server import property_comps

    fn = getattr(property_comps, "fn", property_comps)
    result = asyncio.run(fn(postcode="B5 4BX", months=24))
    assert _has_completeness_warning(result.get("warnings")), result.get("warnings")


def test_mcp_app_search_comps_exposes_the_warning(saturated):
    from property_app.dashboards.comps import _search_comps

    result = _search_comps(postcode="B5 4BX", months=24, limit=50)
    assert _has_completeness_warning(result.get("warnings")), result.get("warnings")


def test_cli_comps_exposes_the_warning(saturated):
    from typer.testing import CliRunner

    from property_cli.main import app as cli

    res = CliRunner().invoke(cli, ["ppd", "comps", "B5 4BX", "--months", "24"])
    assert res.exit_code == 0, res.stdout
    assert "incomplete" in res.stdout.lower() or "exhaust" in res.stdout.lower(), res.stdout


def test_no_snapshot_provenance_fields_are_added_in_pr2(saturated):
    """warnings only -- provenance wiring belongs to PR 4."""
    from property_core import PPDService

    dumped = PPDService().comps(postcode="B5 4BX", search_level="sector",
                                auto_escalate=False).model_dump()
    for field in ("source", "source_release", "coverage_from", "coverage_to",
                  "sample_complete", "completeness_basis", "older_records_exist",
                  "attribution_ref", "freshness_days"):
        assert field not in dumped, f"{field} leaked into PR 2"
