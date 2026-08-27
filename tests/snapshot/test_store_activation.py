"""Staging, atomic activation, and single-snapshot materialization.

The store is ephemeral: both Machines run Fly's default rootfs with no Volume
and no persist_rootfs, so nothing here survives a restart or deploy. It keeps
exactly one active snapshot and makes no durability claim.
"""

from __future__ import annotations

import json

import pytest

from property_core.snapshot.store import SnapshotStore


def _activate(store: SnapshotStore, version: str, rows: int = 3) -> None:
    with store.stage(version) as staging:
        (staging / "manifest.json").write_text(json.dumps({"rows": rows}))
        (staging / "data.parquet").write_bytes(b"PAR1")
        store.activate(staging, version, {"rows": rows, "parquet_files": 1})


def test_activation_makes_the_version_current(store_root):
    store = SnapshotStore(store_root)
    _activate(store, "v1")
    assert store.current_version() == "v1"
    assert store.is_verified("v1")
    assert (store.path_for("v1") / "data.parquet").exists()


def test_activation_is_atomic_via_rename(store_root):
    import inspect

    from property_core.snapshot import store as mod

    assert "os.replace" in inspect.getsource(mod), (
        "activation must use an atomic rename, not a copy or partial write"
    )


def test_a_failed_stage_leaves_the_previous_snapshot_untouched(store_root):
    store = SnapshotStore(store_root)
    _activate(store, "v1")
    before = store.current_version()

    with pytest.raises(RuntimeError):
        with store.stage("v2") as staging:
            (staging / "half.parquet").write_bytes(b"partial")
            raise RuntimeError("extraction blew up")

    assert store.current_version() == before == "v1"
    assert not store.path_for("v2").exists()
    assert store.staging_residue() == [], "staging must be cleaned on failure"


def test_interrupted_activation_does_not_leave_a_half_version(store_root):
    """A crash after staging but before the pointer flip keeps the old current."""
    store = SnapshotStore(store_root)
    _activate(store, "v1")
    with store.stage("v2") as staging:
        (staging / "data.parquet").write_bytes(b"PAR1")
        # simulate the process dying here: never call activate()
    assert store.current_version() == "v1"
    assert store.staging_residue() == []


def test_only_the_active_snapshot_is_kept(store_root):
    """One materialization. Retaining a 'previous' would imply a rollback path
    that does not survive the restart or deploy a rollback is for."""
    store = SnapshotStore(store_root)
    for v in ("v1", "v2", "v3", "v4"):
        _activate(store, v)
        store.prune()
    assert store.current_version() == "v4"
    assert sorted(store.versions()) == ["v4"]


def test_the_store_makes_no_durability_claim(store_root):
    """A wiped filesystem is indistinguishable from a first boot.

    Simulates the restart/deploy that Fly's default rootfs performs: the store
    must come back empty and unverified, not half-present.
    """
    import shutil

    store = SnapshotStore(store_root)
    _activate(store, "v1")
    assert store.is_verified("v1")

    shutil.rmtree(store_root)                      # the Machine restarted
    fresh = SnapshotStore(store_root)
    assert fresh.current_version() is None
    assert fresh.versions() == []
    assert not fresh.is_verified("v1")


def test_pruning_never_removes_the_active_version(store_root):
    store = SnapshotStore(store_root)
    _activate(store, "v1")
    store.prune()
    assert store.current_version() == "v1"
    assert store.is_verified("v1")


def test_no_previous_version_survives_pruning(store_root):
    """The counterpart of the removed rollback test: after pruning there is
    nothing to roll back to, and the store does not pretend otherwise."""
    store = SnapshotStore(store_root)
    _activate(store, "v1")
    _activate(store, "v2")
    store.prune()
    assert sorted(store.versions()) == ["v2"]
    assert not store.is_verified("v1")


def test_an_unverified_directory_is_not_treated_as_verified(store_root):
    store = SnapshotStore(store_root)
    _activate(store, "v1")
    (store.path_for("v1") / ".verified.json").unlink()
    assert not store.is_verified("v1")


def test_a_verification_record_that_disagrees_with_contents_is_rejected(store_root):
    """Verification is by full file inventory -- paths and sizes -- so a record
    that no longer describes what is on disk is not trusted."""
    store = SnapshotStore(store_root)
    _activate(store, "v1")
    rec = store.path_for("v1") / ".verified.json"
    payload = json.loads(rec.read_text())
    payload["inventory"] = {"data.parquet": 999999}
    rec.write_text(json.dumps(payload))
    assert not store.is_verified("v1")


def test_a_record_without_an_inventory_is_not_trusted(store_root):
    store = SnapshotStore(store_root)
    _activate(store, "v1")
    rec = store.path_for("v1") / ".verified.json"
    payload = json.loads(rec.read_text())
    payload.pop("inventory")
    rec.write_text(json.dumps(payload))
    assert not store.is_verified("v1")
