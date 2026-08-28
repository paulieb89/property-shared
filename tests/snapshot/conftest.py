"""Shared fixtures for the snapshot runtime tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.snapshot.archive_fixtures import good_bundle_bytes


@pytest.fixture
def bundle() -> bytes:
    return good_bundle_bytes()


@pytest.fixture
def manifest_for():
    def _make(blob: bytes, version: str = "v20260101T000000Z", **over):
        payload = {
            "snapshot_version": version,
            "bundle_object": f"snapshot-{version}.tar",
            "bundle_sha256": hashlib.sha256(blob).hexdigest(),
            "bundle_bytes": len(blob),
            "parquet_files": 1,
            "rows": 3,
        }
        payload.update(over)
        return payload
    return _make


@pytest.fixture
def store_root(tmp_path: Path) -> Path:
    return tmp_path / "snapshots"


# ---------------------------------------------------------------------------
# Source-routing fixtures (PR 4)
#
# Two mutually exclusive worlds, chosen per test by fixture name:
#
#   snapshot_routing -- a validated adapter installed in process-scoped state,
#                       with PPD_SNAPSHOT_ENABLED on;
#   live_only        -- nothing installed, flag off.
#
# The flag is set through the real environment variable rather than by patching
# the accessor, so these also prove the flag genuinely gates routing.
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field  # noqa: E402
from typing import Any, Optional  # noqa: E402


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No test in this package may reach the network.

    A routing test that accidentally falls through to the real SPARQL endpoint
    does not fail -- it hangs, or worse, passes for the wrong reason against
    whatever the upstream happens to hold today. Blocked at the PPD client's own
    fetch seams rather than at `urlopen`, so the boot-runtime tests that stand up
    a loopback HTTP server on purpose keep working.
    """
    from property_core.ppd_client import PricePaidDataClient

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "a snapshot test attempted a real Land Registry call; patch the "
            "transport seam (fake_live / recording_sparql) instead")

    monkeypatch.setattr(PricePaidDataClient, "_fetch_sparql", _blocked)
    monkeypatch.setattr(PricePaidDataClient, "_fetch_json", _blocked)


@pytest.fixture
def live_only(monkeypatch):
    from property_core.snapshot import state

    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "0")
    state.clear()
    yield
    state.clear()


@dataclass
class _Routing:
    version: str
    adapter: Any
    directory: Path


@pytest.fixture
def snapshot_routing(tmp_path, monkeypatch):
    pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

    from property_core.snapshot import state
    from property_core.snapshot.adapter import SnapshotAdapter
    from tests.snapshot.snapshot_fixtures import build_snapshot, default_rows

    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "1")
    directory, record = build_snapshot(tmp_path / "store", default_rows())
    adapter = SnapshotAdapter.open(directory, record)
    state.clear()
    state.install(adapter)
    try:
        yield _Routing(version=record.version, adapter=adapter, directory=directory)
    finally:
        state.clear()


@dataclass
class _FakeLive:
    """Stands in for the live SPARQL transport at the client seam."""

    rows: list = field(default_factory=list)
    calls: int = 0
    raises: Optional[BaseException] = None
    queries: list = field(default_factory=list)
    #: Override to model a page with NO exhaustion observation. Left None, the
    #: fake reports what a real short page would report.
    evidence: Any = None


@pytest.fixture
def fake_live(monkeypatch):
    """Patch `search_with_evidence` so no test ever reaches the network."""
    from property_core.models.ppd import PPDTransaction
    from property_core.ppd_client import PricePaidDataClient, SearchPage
    from property_core.provenance import TransportEvidence

    spy = _FakeLive(rows=[
        PPDTransaction(transaction_id="LIVE-1", price=190_000, date="2013-04-01",
                       postcode="B5 7AA", property_type="F", estate_type="L",
                       transaction_category="A", new_build=False,
                       paon="1", street="HIGH STREET", town="BIRMINGHAM"),
    ])

    def _fake(self, **kwargs):
        spy.calls += 1
        spy.queries.append(kwargs)
        if spy.raises is not None:
            raise spy.raises
        rows = list(spy.rows)[: kwargs.get("limit", 20)]
        evidence = spy.evidence
        if evidence is None:
            evidence = TransportEvidence(
                raw_bindings_returned=len(rows),
                fetch_limit=max(kwargs.get("limit", 20), 1))
        return SearchPage(transactions=rows, evidence=evidence)

    monkeypatch.setattr(PricePaidDataClient, "search_with_evidence", _fake)
    return spy


@dataclass
class _ProbeSpy:
    calls: list = field(default_factory=list)
    result: Optional[bool] = None
    raises: Optional[BaseException] = None


@pytest.fixture
def probe_spy(monkeypatch):
    """Observe the existence probe without issuing one."""
    from property_core.ppd_probe import ExistenceProbe

    spy = _ProbeSpy()

    def _fake(self, *, postcode, postcode_prefix, coverage_from):
        spy.calls.append({"postcode": postcode, "postcode_prefix": postcode_prefix,
                          "coverage_from": coverage_from})
        if spy.raises is not None:
            return None
        return spy.result

    monkeypatch.setattr(ExistenceProbe, "older_records_exist", _fake)
    return spy


@dataclass
class _RecordingSparql:
    client: Any = None
    queries: list = field(default_factory=list)
    raise_on_call: Optional[BaseException] = None


@pytest.fixture
def recording_sparql(monkeypatch):
    """A real probe client whose HTTP seam records the query and answers empty."""
    import urllib.parse

    from property_core.ppd_client import PricePaidDataClient

    recorder = _RecordingSparql()

    def _fake_fetch(self, encoded_query: bytes):
        query = urllib.parse.parse_qs(encoded_query.decode())["query"][0]
        recorder.queries.append(query)
        if recorder.raise_on_call is not None:
            raise recorder.raise_on_call
        return {"results": {"bindings": []}}

    monkeypatch.setattr(PricePaidDataClient, "_fetch_sparql", _fake_fetch)

    from property_core.ppd_probe import build_probe_client

    recorder.client = build_probe_client()
    return recorder
