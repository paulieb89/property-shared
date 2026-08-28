"""Provenance reaches every consumer, and completeness is never inferred.

Spec section 3.1 and tests 21c/21d and 22-28c. Four consumers read this library
-- REST, two MCP servers, and the CLI -- and a provenance block that stops at the
service layer tells none of them anything. The LLM-facing surfaces matter most:
`content` is what the model reads, and a median without its caveat is exactly
the uncaveated figure the caveat exists to prevent.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

from property_core.provenance import (  # noqa: E402
    ATTRIBUTION_REF,
    CompletenessBasis,
    PPDProvenance,
    SourceKind,
)

#: Pinned literally, NOT imported from the constant the runtime uses. Deriving
#: it from the same source would let a corrupted constant pass this test.
REQUIRED_ATTRIBUTION = (
    "Contains HM Land Registry data © Crown copyright and database right "
    "2021. This data is licensed under the Open Government Licence v3.0."
)


def test_provenance_defaults_to_incomplete():
    """Spec test 21d."""
    provenance = PPDProvenance(source=SourceKind.SPARQL)
    assert provenance.sample_complete is False
    assert provenance.completeness_basis is None


def test_live_sparql_leaves_completeness_false(live_only, fake_live):
    """Spec test 21c. With no exhaustion observation, counts prove nothing.

    `sample_count = 1` against `sample_limit = 50` looks complete and is not:
    the upstream window is bounded BEFORE client-side filtering, so a short list
    is equally consistent with "the window was truncated and most rows were
    discarded". Only an explicit transport-layer observation may establish it.
    """
    from property_core.provenance import TransportEvidence

    from property_core.ppd_service import PPDService

    fake_live.rows = fake_live.rows[:1]
    fake_live.evidence = TransportEvidence()  # nothing observed
    result = PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                              limit=50)
    provenance = result["provenance"]
    assert provenance.sample_count == 1
    assert provenance.sample_limit == 50
    assert provenance.sample_complete is False
    assert provenance.completeness_basis is None


def test_live_sparql_may_claim_completeness_only_on_observed_exhaustion(live_only,
                                                                        fake_live):
    """The other half of 21c: an observation IS admissible, and is named."""
    from property_core.ppd_service import PPDService

    result = PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                              limit=50)
    provenance = result["provenance"]
    assert provenance.sample_complete is True
    assert provenance.completeness_basis is CompletenessBasis.SOURCE_EXHAUSTED


def test_snapshot_exhaustion_establishes_completeness(snapshot_routing):
    """Spec test 21b, end to end through the service.

    The window is named explicitly and sits inside coverage. That matters: the
    adapter's `limit + 1` evidence covers what it searched, so it can only
    establish completeness for an interval that was entirely searchable.
    """
    from property_core.ppd_service import PPDService

    result = PPDService().search_transactions(postcode=None, postcode_prefix="M3 7",
                                              from_date="2016-01-01",
                                              to_date="2026-06-30", limit=50)
    provenance = result["provenance"]
    assert provenance.sample_complete is True
    assert provenance.completeness_basis is CompletenessBasis.LIMIT_PLUS_ONE


def test_the_same_query_open_ended_is_not_complete(snapshot_routing):
    """No `to_date` means "up to now", and now is past `coverage_to`.

    Same postcode, same limit, same exhausted page -- and honestly incomplete,
    because part of what was asked for lies outside the snapshot entirely.
    """
    from property_core.ppd_service import PPDService

    result = PPDService().search_transactions(postcode=None, postcode_prefix="M3 7",
                                              from_date="2016-01-01", limit=50)
    assert result["provenance"].sample_complete is False
    assert result["provenance"].completeness_basis is None


def test_snapshot_result_at_the_limit_is_incomplete(snapshot_routing):
    """Spec test 20."""
    from property_core.ppd_service import PPDService

    result = PPDService().search_transactions(postcode=None, postcode_prefix="B5",
                                              limit=2)
    assert result["provenance"].sample_complete is False


def test_rest_comps_carries_the_provenance_block(snapshot_routing):
    """Spec test 22."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/v1/ppd/comps",
                              params={"postcode": "B5 7AA", "search_level": "district"})
    assert response.status_code == 200
    provenance = response.json()["provenance"]
    assert provenance["source"] == "snapshot"
    assert provenance["source_release"] == snapshot_routing.version
    assert provenance["coverage_from"] == "2016-01-01"
    assert provenance["coverage_to"] == "2026-06-30"
    assert provenance["attribution_ref"] == ATTRIBUTION_REF
    assert "sample_complete" in provenance
    assert isinstance(provenance["freshness_days"], int)


def test_rest_transactions_carries_the_provenance_block(snapshot_routing):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/v1/ppd/transactions", params={"postcode_prefix": "B5"})
    assert response.status_code == 200
    assert response.json()["provenance"]["source"] == "snapshot"


@pytest.mark.anyio
async def test_plain_mcp_property_comps_carries_provenance(snapshot_routing):
    """Spec test 23. The tool payload is what a programmatic consumer reads."""
    from app.mcp.server import property_comps

    result = await property_comps(postcode="B5 7AA", search_level="district")
    assert result["provenance"]["source"] == "snapshot"
    assert result["provenance"]["coverage_from"] == "2016-01-01"


def test_plain_mcp_ppd_transactions_carries_provenance(snapshot_routing):
    from app.mcp.server import ppd_transactions

    result = ppd_transactions(postcode="B5 7AA")
    assert result["provenance"]["source"] == "snapshot"
    assert result["provenance"]["coverage_to"] == "2026-06-30"


def test_mcp_app_search_comps_carries_provenance(snapshot_routing):
    """Spec test 24."""
    from property_app.dashboards.comps import _search_comps

    data = _search_comps(postcode="B5 7AA", search_level="district")
    assert data["provenance"]["source"] == "snapshot"


def test_cli_comps_carries_provenance_in_core_mode(snapshot_routing, capsys):
    """Spec test 25, core half."""
    typer_testing = pytest.importorskip("typer.testing")

    from property_cli.main import app

    result = typer_testing.CliRunner().invoke(
        app, ["ppd", "comps", "B5 7AA", "--search-level", "district"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["provenance"]["source"] == "snapshot"


def test_mixed_source_comps_declares_both(snapshot_routing, fake_live):
    """Spec test 26. Subject-property history is live; the comps are not."""
    from property_core.ppd_service import PPDService

    result = PPDService().comps(postcode="B5 7AA", address="1 High Street",
                                search_level="district")
    assert result.provenance.source is SourceKind.SNAPSHOT
    assert result.subject_property is not None
    assert result.subject_property.provenance.source is SourceKind.SPARQL


def test_subject_property_failure_warns_and_success_does_not(snapshot_routing,
                                                             fake_live):
    """Spec test 17. A failed lookup is never rendered as an absent history."""
    from property_core.ppd_service import PPDService

    fake_live.rows = []
    genuine = PPDService().comps(postcode="B5 7AA", address="1 High Street",
                                 search_level="district")
    assert genuine.subject_property is None
    assert not any("lookup unavailable" in w for w in genuine.warnings)

    fake_live.raises = RuntimeError("SPARQL down")
    failed = PPDService().comps(postcode="B5 7AA", address="1 High Street",
                                search_level="district")
    assert failed.subject_property is None
    assert any("lookup unavailable" in w for w in failed.warnings)


def test_attribution_ref_resolves_to_the_exact_required_string(snapshot_routing):
    """Spec tests 28 and 28b. The expected value is pinned in this file."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        meta = client.get("/v1/meta").json()
    assert meta["attribution"] == REQUIRED_ATTRIBUTION


def test_licence_prose_never_appears_in_a_data_payload(snapshot_routing):
    """Spec test 28c. Responses carry a reference, not the licence."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        body = client.get("/v1/ppd/transactions",
                          params={"postcode_prefix": "B5"}).text
    assert "Open Government Licence" not in body
    assert "Crown copyright" not in body
    assert ATTRIBUTION_REF in body


def test_provenance_is_built_atomically_never_patched():
    """Spec section 3.1.2.

    `model_copy(update=...)` bypasses validation by design: it can produce and
    serialise a block `__init__` would reject. Checked over the parsed AST, not
    the text, so prose explaining the prohibition does not read as a violation
    of it.
    """
    import ast
    import inspect

    from property_core import ppd_service, ppd_source

    for module in (ppd_service, ppd_source):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "model_copy"
                    and any(kw.arg == "update" for kw in node.keywords)):
                raise AssertionError(
                    f"{module.__name__} patches a model with model_copy(update=...)")


@pytest.mark.anyio
async def test_ppd_transactions_descriptions_state_coverage_bounded_semantics():
    """Spec test 29. Read from the REGISTERED tool, not the source docstring.

    These strings are the routing contract an LLM reads, so what matters is what
    FastMCP actually publishes.
    """
    from app.mcp.server import mcp as plain_server
    from property_app import tools  # noqa: F401 -- registers the app's tools
    from property_app.server import mcp as app_server

    for server in (plain_server, app_server):
        tool = await server.get_tool("ppd_transactions")
        description = (tool.description or "").lower()
        assert "every recorded transaction" not in description
        assert "coverage" in description
        assert "older_records_exist" in description
