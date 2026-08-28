"""Coverage routing: what happens when the request reaches past the snapshot.

Spec section 2.5 and tests 5-9. The rule the whole design turns on: a request
whose range starts before `coverage_from` is **unsatisfiable as stated** and is
refused with both ranges attached. It is never answered partially, because a
truncated answer is indistinguishable from a complete one.

Two policies, and the difference is whether the caller's window is bounded:

* GUARANTEED -- `months` has an upper bound the snapshot is sized to cover
  (comps, yield, report). A window reaching past coverage can only happen with a
  stale snapshot, so it is narrowed and warned rather than refused.
* EXPLICIT -- the caller named dates, or `months` has no upper bound (blocks,
  transactions). Refused, typed, with structured ranges.
"""

from __future__ import annotations

import pytest

pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

from property_core.exceptions import PPDCoverageError  # noqa: E402
from property_core.ppd_service import PPDService  # noqa: E402
from property_core.provenance import SourceKind  # noqa: E402


def test_explicit_from_date_before_coverage_is_refused(snapshot_routing):
    """Spec test 5. Never a 200 with partial rows."""
    svc = PPDService()
    with pytest.raises(PPDCoverageError) as exc:
        svc.search_transactions(postcode=None, postcode_prefix="B5",
                                from_date="2004-01-01", limit=10)
    payload = exc.value.to_dict()
    assert payload["error"] == "ppd_coverage_error"
    assert payload["requested"] == {"from_date": "2004-01-01", "to_date": None}
    assert payload["available"] == {"coverage_from": "2016-01-01",
                                    "coverage_to": "2026-06-30"}
    assert payload["source_release"] == snapshot_routing.version
    assert "2016-01-01" in payload["remedy"]


def test_ranges_are_structured_not_prose(snapshot_routing):
    """A caller reformulates from fields, never by parsing a sentence."""
    svc = PPDService()
    with pytest.raises(PPDCoverageError) as exc:
        svc.search_transactions(postcode=None, postcode_prefix="B5",
                                from_date="2004-01-01", to_date="2005-01-01",
                                limit=10)
    payload = exc.value.to_dict()
    assert isinstance(payload["requested"], dict)
    assert isinstance(payload["available"], dict)
    assert payload["requested"]["to_date"] == "2005-01-01"


def test_from_date_inside_coverage_is_served_from_the_snapshot(snapshot_routing):
    """Spec test 6."""
    svc = PPDService()
    result = svc.search_transactions(postcode=None, postcode_prefix="B5",
                                     from_date="2020-01-01", limit=10)
    assert result["provenance"].source is SourceKind.SNAPSHOT
    assert result["provenance"].source_release == snapshot_routing.version
    assert result["count"] > 0


def test_absent_from_date_is_narrowed_with_a_warning(snapshot_routing):
    """Spec test 7. 'All time' silently becoming '11 years' is the lie to avoid."""
    svc = PPDService()
    result = svc.search_transactions(postcode=None, postcode_prefix="B5", limit=10)
    provenance = result["provenance"]
    assert provenance.source is SourceKind.SNAPSHOT
    assert provenance.coverage_from == "2016-01-01"
    assert any("narrowed" in w for w in result["warnings"])
    assert any("narrowed" in w for w in provenance.warnings)


def test_blocks_with_an_unbounded_window_is_refused_not_clamped(snapshot_routing):
    """Spec test 8. `months` has no upper bound on this surface."""
    from property_core.block_service import analyze_blocks

    with pytest.raises(PPDCoverageError) as exc:
        analyze_blocks("B5 7AA", months=600)
    assert exc.value.coverage_from == "2016-01-01"
    assert exc.value.requested_from is not None
    assert exc.value.requested_from < "2016-01-01"


def test_comps_narrows_rather_than_refusing(snapshot_routing):
    """comps' `months` is bounded by every surface that exposes it (60 / 120).

    A window reaching past coverage therefore means a stale snapshot, not an
    unsatisfiable request -- so it is narrowed and warned, never refused.
    """
    svc = PPDService()
    result = svc.comps(postcode="B5 7AA", months=600, search_level="district")
    assert result.provenance.source is SourceKind.SNAPSHOT
    assert result.provenance.coverage_from == "2016-01-01"
    assert any("narrowed" in w for w in result.warnings)


def test_comps_inside_coverage_carries_no_narrowing_warning(snapshot_routing):
    svc = PPDService()
    result = svc.comps(postcode="B5 7AA", months=24, search_level="district")
    assert result.provenance.source is SourceKind.SNAPSHOT
    assert not any("narrowed" in w for w in result.warnings)


def test_rest_coverage_error_is_a_422_with_both_ranges(snapshot_routing):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/v1/ppd/transactions",
                              params={"postcode_prefix": "B5",
                                      "from_date": "2004-01-01"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "ppd_coverage_error"
    assert detail["available"]["coverage_from"] == "2016-01-01"
    assert detail["requested"]["from_date"] == "2004-01-01"


def test_cli_coverage_error_exits_non_zero_and_prints_both_ranges(snapshot_routing):
    """Spec test 9."""
    typer_testing = pytest.importorskip("typer.testing")

    from property_cli.main import app

    result = typer_testing.CliRunner().invoke(
        app, ["ppd", "blocks", "B5 7AA", "--months", "600"])
    assert result.exit_code != 0
    assert "2016-01-01" in result.output
    assert "2026-06-30" in result.output
    assert "ppd_coverage_error" in result.output


def test_provisional_tail_is_flagged_from_the_manifest(snapshot_routing):
    """Spec section 1.3. Provisional is published, never inferred at query time."""
    svc = PPDService()
    intersecting = svc.search_transactions(postcode=None, postcode_prefix="B5",
                                           from_date="2026-05-01", limit=10)
    assert intersecting["provenance"].recent_period_provisional is True
    assert any("provisional" in w for w in intersecting["provenance"].warnings)

    earlier = svc.search_transactions(postcode=None, postcode_prefix="B5",
                                      from_date="2020-01-01", to_date="2021-01-01",
                                      limit=10)
    assert earlier["provenance"].recent_period_provisional is False
