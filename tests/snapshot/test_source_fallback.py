"""Missing is not unavailable: what each failure is allowed to look like.

Spec section 3.2 and tests 15-19. Three outcomes that a naive implementation
collapses into one empty list:

* no rows matched inside coverage -> 200, empty, honest;
* the snapshot could not answer -> fall back to the LIVE source, warn, and say
  `source: sparql`. The materialization is ephemeral, so "no snapshot" is a
  normal state, not an outage;
* the live upstream failed -> a typed upstream error, never empty data.

The fallback is on the *snapshot* failure taxonomy only. A caller error
(`InvalidPostcodeError`) and a coverage refusal (`PPDCoverageError`) must reach
the caller unchanged -- retrying those against live would hide the very thing
this design exists to report.
"""

from __future__ import annotations

import pytest

pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

from property_core.exceptions import (  # noqa: E402
    InvalidPostcodeError,
    PPDCoverageError,
    SnapshotFailure,
    UpstreamUnavailableError,
)
from property_core.ppd_service import PPDService  # noqa: E402
from property_core.provenance import SourceKind  # noqa: E402
from property_core.snapshot.errors import SnapshotQueryError  # noqa: E402


def test_no_snapshot_open_uses_the_live_source(live_only, fake_live):
    """Spec test 15, under section 4.5.

    UNREADY is a normal outcome after every restart, so it hands off to live
    rather than surfacing an error. What must never happen is empty data.
    """
    svc = PPDService()
    result = svc.search_transactions(postcode=None, postcode_prefix="B5", limit=10)
    assert result["provenance"].source is SourceKind.SPARQL
    assert result["provenance"].source_release is None
    assert result["count"] == len(fake_live.rows)


def test_snapshot_query_failure_falls_back_to_live_and_says_so(snapshot_routing,
                                                               fake_live, monkeypatch):
    """Every typed snapshot failure hands off, and the handoff is declared."""
    def _boom(*a, **k):
        raise SnapshotQueryError("duckdb blew up mid-query")

    monkeypatch.setattr(type(snapshot_routing.adapter), "search", _boom)

    svc = PPDService()
    result = svc.search_transactions(postcode=None, postcode_prefix="B5", limit=10)
    assert result["provenance"].source is SourceKind.SPARQL
    assert any("snapshot" in w and "live" in w for w in result["warnings"])
    assert result["count"] == len(fake_live.rows)


def test_snapshot_failure_subclasses_all_fall_back(snapshot_routing, fake_live,
                                                   monkeypatch):
    """The taxonomy is the contract, not an enumeration of known classes."""
    class NovelSnapshotFailure(SnapshotFailure):
        code = "snapshot_something_new"

    def _boom(*a, **k):
        raise NovelSnapshotFailure("a failure mode added after this test was written")

    monkeypatch.setattr(type(snapshot_routing.adapter), "search", _boom)
    svc = PPDService()
    result = svc.search_transactions(postcode=None, postcode_prefix="B5", limit=10)
    assert result["provenance"].source is SourceKind.SPARQL


def test_coverage_refusal_is_never_softened_into_a_live_fallback(snapshot_routing,
                                                                 fake_live):
    """The behavioural change of this design, and the one it must not undo."""
    svc = PPDService()
    with pytest.raises(PPDCoverageError):
        svc.search_transactions(postcode=None, postcode_prefix="B5",
                                from_date="2004-01-01", limit=10)
    assert fake_live.calls == 0


def test_caller_error_is_never_softened_into_a_live_fallback(snapshot_routing,
                                                             fake_live):
    svc = PPDService()
    with pytest.raises(InvalidPostcodeError):
        svc.search_transactions(postcode=None, postcode_prefix="not a postcode",
                                limit=10)
    assert fake_live.calls == 0


def test_live_upstream_failure_is_typed_never_empty(live_only, fake_live):
    """Spec test 16. Distinct from both 'empty' and 'no snapshot'."""
    fake_live.raises = RuntimeError("SPARQL 503")
    svc = PPDService()
    with pytest.raises(Exception) as exc:
        svc.search_transactions(postcode=None, postcode_prefix="B5", limit=10)
    assert not isinstance(exc.value, SnapshotFailure)


def test_rest_maps_live_failure_to_502(live_only, fake_live):
    from fastapi.testclient import TestClient

    from app.main import create_app

    fake_live.raises = RuntimeError("SPARQL 503")
    with TestClient(create_app()) as client:
        response = client.get("/v1/ppd/transactions", params={"postcode_prefix": "B5"})
    assert response.status_code == 502


def test_record_status_still_rejected_against_the_snapshot(snapshot_routing):
    """Spec test 19. Parity with live: a scope decision, not an ontology gap."""
    from property_core.ppd_client import UnsupportedRecordStatusFilterError

    svc = PPDService()
    with pytest.raises(UnsupportedRecordStatusFilterError):
        svc.search_transactions(postcode=None, postcode_prefix="B5",
                                record_status="A", limit=10)


def test_exact_id_lookup_stays_on_linked_data(snapshot_routing, monkeypatch):
    """Spec test 18. Exact ID works outside coverage, so it never routes to snapshot."""
    from property_core.models.ppd import PPDTransactionRecord
    from property_core.ppd_client import PricePaidDataClient

    seen: list[str] = []

    def _fake(self, transaction_id, view="all"):
        seen.append(transaction_id)
        return PPDTransactionRecord(transaction_id=transaction_id, price_paid=1,
                                    transaction_date="1998-04-01")

    monkeypatch.setattr(PricePaidDataClient, "get_transaction_record", _fake)
    svc = PPDService()
    out = svc.transaction_record("abc-123")
    assert seen == ["abc-123"]
    assert out["provenance"].source is SourceKind.LINKED_DATA
    assert out["provenance"].coverage_from is None


def test_upstream_unavailable_is_not_a_snapshot_failure():
    """The two taxonomies must not overlap, or fallback would loop."""
    assert not issubclass(UpstreamUnavailableError, SnapshotFailure)
    assert not issubclass(SnapshotFailure, UpstreamUnavailableError)
