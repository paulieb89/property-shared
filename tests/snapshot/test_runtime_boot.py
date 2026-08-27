"""Boot orchestration: readiness, live fallback, typed errors.

The materialization is ephemeral (Fly default rootfs, no Volume), so a snapshot
is never a fallback for a source outage -- the live source is.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from property_core.exceptions import SnapshotUnavailableError
from property_core.snapshot.models import Readiness
from property_core.snapshot.runtime import SnapshotRuntime
from property_core.snapshot.store import SnapshotStore

from tests.snapshot.archive_fixtures import good_bundle_bytes


class FakeSource:
    """In-memory object source. No network, no filesystem source, no cloud."""

    def __init__(self, objects: dict[str, bytes], *, fail: Exception | None = None):
        self.objects = objects
        self.fail = fail
        self.reads: list[str] = []

    def read_bytes(self, name, *, max_bytes=None):
        if self.fail:
            raise self.fail
        self.reads.append(name)
        return self.objects[name]

    def open_stream(self, name):
        if self.fail:
            raise self.fail
        self.reads.append(name)
        blob = self.objects[name]

        class _S:
            declared_length = len(blob)

            def __init__(self):
                self.pos = 0

            def read(self, n):
                out = blob[self.pos:self.pos + n]
                self.pos += len(out)
                return out

            def __enter__(self):
                return self

            def __exit__(self, *e):
                return False

        return _S()


def make_source(version: str = "v1", **manifest_over) -> tuple[FakeSource, bytes]:
    blob = good_bundle_bytes()
    manifest = {
        "snapshot_version": version,
        "bundle_object": f"snapshot-{version}.tar",
        "bundle_sha256": hashlib.sha256(blob).hexdigest(),
        "bundle_bytes": len(blob),
        "parquet_files": 1,
        "rows": 3,
    }
    manifest.update(manifest_over)
    objects = {
        "current.json": json.dumps({"current_manifest": f"manifest-{version}.json"}).encode(),
        f"manifest-{version}.json": json.dumps(manifest).encode(),
        f"snapshot-{version}.tar": blob,
    }
    return FakeSource(objects), blob


def runtime(root, source) -> SnapshotRuntime:
    return SnapshotRuntime(source=source, store=SnapshotStore(root))


# --- cold boot -------------------------------------------------------------

def test_cold_boot_reaches_ready(store_root):
    source, blob = make_source()
    report = runtime(store_root, source).boot()
    assert report.readiness is Readiness.READY
    assert report.version == "v1"
    assert report.bytes_downloaded == len(blob)
    assert report.activated is True


def test_restart_with_a_verified_cache_downloads_nothing(store_root):
    source, _ = make_source()
    runtime(store_root, source).boot()
    source.reads.clear()
    report = runtime(store_root, source).boot()
    assert report.readiness is Readiness.READY
    assert report.bytes_downloaded == 0
    assert report.reused_existing is True
    assert not any(r.endswith(".tar") for r in source.reads), source.reads


# --- fail closed -----------------------------------------------------------

@pytest.mark.parametrize("broken", ["manifest", "digest", "archive"])
def test_a_failed_update_leaves_the_previous_snapshot_serving(store_root, broken):
    source, blob = make_source("v1")
    rt = runtime(store_root, source)
    rt.boot()

    bad, _ = make_source("v2")
    if broken == "manifest":
        bad.objects["manifest-v2.json"] = b'{"snapshot_version": '
    elif broken == "digest":
        bad.objects["snapshot-v2.tar"] = b"different bytes entirely"
    else:
        from tests.snapshot.archive_fixtures import build_tar, reg
        hostile = build_tar([reg("../escape.txt")])
        bad.objects["snapshot-v2.tar"] = hostile
        m = json.loads(bad.objects["manifest-v2.json"])
        m["bundle_sha256"] = hashlib.sha256(hostile).hexdigest()
        m["bundle_bytes"] = len(hostile)
        bad.objects["manifest-v2.json"] = json.dumps(m).encode()

    report = runtime(store_root, bad).boot()
    store = SnapshotStore(store_root)
    # Same Machine, so v1 is still unpacked and is adopted -- flagged as behind
    # the advertised release, which is not a durability guarantee.
    assert report.readiness is Readiness.READY
    assert report.behind_advertised_release is True
    assert store.current_version() == "v1"
    assert "v2" not in store.versions()
    assert store.staging_residue() == []
    assert report.source_error


def test_source_outage_on_a_machine_that_already_materialized_adopts_it(store_root):
    """Legitimate only because this Machine has not restarted. Not a cache."""
    source, _ = make_source()
    runtime(store_root, source).boot()
    down = FakeSource({}, fail=OSError("connection refused"))
    report = runtime(store_root, down).boot()
    assert report.readiness is Readiness.READY
    assert report.behind_advertised_release is True
    assert report.fallback_to_live is False
    assert any("advertised release" in w for w in report.warnings), report.warnings


def test_source_outage_after_a_restart_hands_off_to_the_live_source(store_root):
    """The production case: the rootfs was wiped, so there is nothing to adopt."""
    down = FakeSource({}, fail=OSError("connection refused"))
    report = runtime(store_root, down).boot()
    assert report.readiness is Readiness.UNREADY
    assert report.version is None
    assert report.fallback_to_live is True
    assert any("live source" in w for w in report.warnings), report.warnings


def test_unready_runtime_raises_the_typed_error_never_empty_data(store_root):
    down = FakeSource({}, fail=OSError("down"))
    rt = runtime(store_root, down)
    rt.boot()
    with pytest.raises(SnapshotUnavailableError) as ei:
        rt.require_ready()
    payload = ei.value.to_dict()
    assert payload["error"] == "snapshot_unavailable"
    assert "results" not in payload and "count" not in payload


def test_an_adopted_materialization_is_usable_and_says_so(store_root):
    source, _ = make_source()
    runtime(store_root, source).boot()
    rt = runtime(store_root, FakeSource({}, fail=OSError("down")))
    rt.boot()
    assert rt.require_ready() is not None
    assert rt.readiness is Readiness.READY
    assert rt.report.behind_advertised_release is True


def test_there_is_no_stale_readiness_state():
    """Removed deliberately: an ephemeral store cannot promise a stale cache."""
    assert not hasattr(Readiness, "READY_STALE")
    assert {r.value for r in Readiness} == {"unready", "ready"}


# --- concurrency -----------------------------------------------------------

def test_concurrent_starters_download_once(store_root):
    """Two runtimes booting together must not both fetch the bundle."""
    import threading

    source, _ = make_source()
    reports = []

    def go():
        reports.append(runtime(store_root, source).boot())

    threads = [threading.Thread(target=go) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert all(r.readiness is Readiness.READY for r in reports), reports
    downloads = sum(1 for name in source.reads if name.endswith(".tar"))
    assert downloads == 1, f"bundle fetched {downloads} times"


# --- retention -------------------------------------------------------------

def test_boot_keeps_only_the_active_materialization(store_root):
    for v in ("v1", "v2", "v3"):
        source, _ = make_source(v)
        runtime(store_root, source).boot()
    assert sorted(SnapshotStore(store_root).versions()) == ["v3"]


# --- guardrails ------------------------------------------------------------

def test_no_hot_refresh_api_exists():
    import property_core.snapshot.runtime as mod

    for banned in ("refresh", "reload", "watch", "poll"):
        assert not hasattr(SnapshotRuntime, banned), (
            f"SnapshotRuntime.{banned} implies hot refresh, which v1 excludes"
        )
    assert "threading.Timer" not in mod.__doc__ if mod.__doc__ else True


def test_runtime_never_queries_duckdb(store_root):
    """PR 3 verifies bundles; it does not open or query them."""
    import inspect

    from property_core.snapshot import runtime as mod

    src = inspect.getsource(mod)
    for banned in ("duckdb.connect", "SELECT ", "read_parquet"):
        assert banned not in src, f"{banned!r} is querying, which PR 3 excludes"
