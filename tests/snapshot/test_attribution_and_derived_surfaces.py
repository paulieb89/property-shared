"""Attribution, and provenance on the surfaces derived from comps.

Spec section 6 and 3.1. Two things being pinned:

* **The attribution reference resolves.** Every PPD response carries
  `attribution_ref` rather than licence prose, which is only honest if the thing
  it points at actually exists and says the required words. The expected string
  is pinned literally in this file, not imported -- a test that derived it from
  the same constant the runtime uses would pass even if that constant were
  corrupted.
* **Derived figures inherit their source's provenance.** A yield divides rent by
  the comps median, so an incomplete or coverage-bounded sales window makes the
  yield equally bounded. The caveat has to travel with the number.
"""

from __future__ import annotations

import pytest

pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

from property_core.provenance import SourceKind  # noqa: E402

#: Pinned literally. See the module docstring.
REQUIRED_ATTRIBUTION = (
    "Contains HM Land Registry data © Crown copyright and database right "
    "2026. This data is licensed under the Open Government Licence v3.0."
)


def test_cli_meta_states_the_attribution(snapshot_routing):
    import json

    typer_testing = pytest.importorskip("typer.testing")

    from property_cli.main import app

    result = typer_testing.CliRunner().invoke(app, ["meta"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["attribution"] == REQUIRED_ATTRIBUTION
    assert payload["ppd_snapshot"]["version"] == snapshot_routing.version


def test_both_mcp_instructions_state_the_licence_and_the_bound():
    """The instructions string is the first thing an LLM reads about this server."""
    from app.mcp.server import mcp as plain_server
    from property_app.server import mcp as app_server

    for server in (plain_server, app_server):
        instructions = server.instructions or ""
        assert "Open Government Licence" in instructions, server.name
        assert "HM Land Registry" in instructions, server.name
        assert "never sold" in instructions, server.name


def test_rest_meta_reports_the_snapshot_state(snapshot_routing):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        payload = client.get("/v1/meta").json()
    assert payload["snapshot"]["routable"] is True
    assert payload["snapshot"]["coverage_from"] == "2016-01-01"


def test_address_search_declares_the_live_source(snapshot_routing, fake_live):
    """Spec 2.6: address search takes no dates and is never routed to a snapshot."""
    from property_core.ppd_service import PPDService

    result = PPDService().address_search(postcode="B5 7AA", street="High Street")
    assert result["provenance"].source is SourceKind.SPARQL
    assert result["provenance"].coverage_from is None


@pytest.mark.anyio
async def test_yield_inherits_the_sale_side_provenance(snapshot_routing, monkeypatch):
    """A yield is only as bounded as the sale window it divides by."""
    from property_core import yield_service
    from property_core.rightmove_location import RightmoveLocationAPI

    # Both Rightmove seams stubbed: this test is about the sale side, and a real
    # listings call would make it slow and non-deterministic.
    monkeypatch.setattr(RightmoveLocationAPI, "build_search_url",
                        lambda self, *a, **k: "https://example.invalid/rent")
    monkeypatch.setattr(yield_service, "fetch_listings", lambda *a, **k: [])

    analysis = await yield_service.calculate_yield("B5 7AA", months=24,
                                                   search_level="district")
    assert analysis.sale_provenance is not None
    assert analysis.sale_provenance.source is SourceKind.SNAPSHOT
    assert analysis.sale_provenance.coverage_from == "2016-01-01"
