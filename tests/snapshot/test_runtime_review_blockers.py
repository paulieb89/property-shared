"""Regressions for the seven runtime-review blockers.

Each was reproduced against 76add0d before the fix. Grouped here so the class of
defect stays visible: every one is a boundary that trusted its input -- a
manifest field, an archive member name, or a decision cached from before a lock
was held.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from property_core.snapshot.archive import safe_extract
from property_core.snapshot.errors import ArchiveRejected
from property_core.snapshot.models import Readiness, SnapshotManifest
from property_core.snapshot.runtime import SnapshotRuntime
from property_core.snapshot.store import SnapshotStore


def _bundle(payload: bytes = b"PAR1tiny", name: str = "data.parquet") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        ti = tarfile.TarInfo(name); ti.size = len(payload)
        tar.addfile(ti, io.BytesIO(payload))
    return buf.getvalue()


def _objects(version: str, blob: bytes, *, parquet_files: int = 1) -> dict:
    manifest = {
        "snapshot_version": version, "bundle_object": f"s-{version}.tar",
        "bundle_sha256": hashlib.sha256(blob).hexdigest(),
        "bundle_bytes": len(blob), "parquet_files": parquet_files, "rows": 1,
    }
    return {
        "current.json": json.dumps({"current_manifest": f"m-{version}.json"}).encode(),
        f"m-{version}.json": json.dumps(manifest).encode(),
        f"s-{version}.tar": blob,
    }


class Src:
    def __init__(self, objects: dict):
        self.objects = objects

    def read_bytes(self, name, *, max_bytes=None):
        return self.objects[name]

    def open_stream(self, name):
        blob = self.objects[name]

        class S:
            declared_length = len(blob)

            def __init__(self):
                self.pos = 0

            def read(self, n):
                out = blob[self.pos:self.pos + n]; self.pos += len(out); return out

            def __enter__(self):
                return self

            def __exit__(self, *e):
                return False

        return S()


def _manifest(**over):
    payload = {"snapshot_version": "v1", "bundle_object": "b.tar",
               "bundle_sha256": "a" * 64, "bundle_bytes": 10,
               "parquet_files": 1, "rows": 1}
    payload.update(over)
    return SnapshotManifest(**payload)


# --- 1. snapshot_version must not escape the store -------------------------

@pytest.mark.parametrize(
    "version",
    ["../escaped", "../../escaped", "a/b", "./x", "..", ".", "/abs", "x/", "",
     "a\\b", "with\x00null", "  ", "CURRENT"],
)
def test_a_version_that_is_not_a_safe_single_component_is_rejected(version):
    with pytest.raises(ValidationError):
        _manifest(snapshot_version=version)


def test_a_normal_version_is_still_accepted():
    assert _manifest(snapshot_version="v20260827T123230Z").snapshot_version


def test_the_store_also_refuses_an_unsafe_version(tmp_path):
    """Defence in depth: the store does not rely on the manifest having validated."""
    store = SnapshotStore(tmp_path)
    for bad in ("../escape", "a/b", "..", ""):
        with pytest.raises(ValueError):
            store.path_for(bad)


# --- 2. unknown manifest fields must not be silently dropped ----------------

def test_manifest_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        _manifest(bundle_sha512="typo")


# --- 3. a same-version republish with different bytes must be detected -----

def test_a_changed_digest_for_the_same_version_is_reinstalled(tmp_path):
    first = _bundle(b"ORIGINAL")
    SnapshotRuntime(source=Src(_objects("v1", first)),
                    store=SnapshotStore(tmp_path)).boot()
    assert (SnapshotStore(tmp_path).path_for("v1") / "data.parquet").read_bytes() \
        == b"ORIGINAL"

    second = _bundle(b"REPLACED")
    report = SnapshotRuntime(source=Src(_objects("v1", second)),
                             store=SnapshotStore(tmp_path)).boot()
    assert report.readiness is Readiness.READY
    assert report.bytes_downloaded > 0, "a changed digest must trigger a refetch"
    # The rebuild lands in a fresh generation directory -- version directories
    # are immutable -- so read the active one rather than assuming its name.
    store = SnapshotStore(tmp_path)
    active = store.path_for(store.current_version())
    assert (active / "data.parquet").read_bytes() == b"REPLACED"
    assert report.version == "v1"


def test_an_unchanged_digest_still_skips_the_download(tmp_path):
    blob = _bundle(b"SAME")
    objects = _objects("v1", blob)
    SnapshotRuntime(source=Src(objects), store=SnapshotStore(tmp_path)).boot()
    report = SnapshotRuntime(source=Src(objects), store=SnapshotStore(tmp_path)).boot()
    assert report.bytes_downloaded == 0
    assert report.reused_existing is True


# --- 3b. an archive with no parquet files must not reach READY -------------

def test_a_manifest_declaring_no_parquet_files_is_rejected():
    """A snapshot with nothing to query is not a snapshot."""
    with pytest.raises(ValidationError):
        _manifest(parquet_files=0)


def test_an_archive_with_no_parquet_files_is_rejected(tmp_path):
    empty = io.BytesIO()
    with tarfile.open(fileobj=empty, mode="w") as tar:
        body = b"{}"
        ti = tarfile.TarInfo("manifest.json"); ti.size = len(body)
        tar.addfile(ti, io.BytesIO(body))
    # Declares one parquet file; the archive contains none.
    report = SnapshotRuntime(source=Src(_objects("v9", empty.getvalue(), parquet_files=1)),
                             store=SnapshotStore(tmp_path)).boot()
    assert report.readiness is Readiness.UNREADY
    assert report.fallback_to_live is True


def test_a_parquet_count_below_the_manifest_is_rejected(tmp_path):
    blob = _bundle(b"PAR1", "only.parquet")
    report = SnapshotRuntime(source=Src(_objects("v1", blob, parquet_files=5)),
                             store=SnapshotStore(tmp_path)).boot()
    assert report.readiness is Readiness.UNREADY


def test_a_parquet_count_above_the_manifest_is_rejected(tmp_path):
    """Exact, not 'at least': extra files are as much a mismatch as missing ones."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for n in ("a.parquet", "b.parquet"):
            ti = tarfile.TarInfo(n); ti.size = 4
            tar.addfile(ti, io.BytesIO(b"PAR1"))
    report = SnapshotRuntime(source=Src(_objects("v1", buf.getvalue(), parquet_files=1)),
                             store=SnapshotStore(tmp_path)).boot()
    assert report.readiness is Readiness.UNREADY


# --- 4. truncation must invalidate verification ----------------------------

def test_truncating_a_parquet_file_invalidates_verification(tmp_path):
    store = SnapshotStore(tmp_path)
    with store.stage("v1") as staging:
        (staging / "a.parquet").write_bytes(b"PAR1" * 100)
        store.activate(staging, "v1", {"parquet_files": 1, "rows": 5})
    assert store.is_verified("v1")

    (store.path_for("v1") / "a.parquet").write_bytes(b"P")
    assert not store.is_verified("v1"), "a truncated file is still reported verified"


def test_adding_a_file_invalidates_verification(tmp_path):
    store = SnapshotStore(tmp_path)
    with store.stage("v1") as staging:
        (staging / "a.parquet").write_bytes(b"PAR1")
        store.activate(staging, "v1", {"parquet_files": 1, "rows": 1})
    (store.path_for("v1") / "b.parquet").write_bytes(b"PAR1")
    assert not store.is_verified("v1")


def test_removing_a_file_invalidates_verification(tmp_path):
    store = SnapshotStore(tmp_path)
    with store.stage("v1") as staging:
        (staging / "a.parquet").write_bytes(b"PAR1")
        store.activate(staging, "v1", {"parquet_files": 1, "rows": 1})
    (store.path_for("v1") / "a.parquet").unlink()
    assert not store.is_verified("v1")


# --- 5. activation must never delete the active snapshot first -------------

def test_activation_never_removes_an_existing_version_before_renaming(tmp_path):
    """Version directories are immutable: a rebuild lands somewhere new."""
    store = SnapshotStore(tmp_path)
    with store.stage("v1") as staging:
        (staging / "a.parquet").write_bytes(b"FIRST")
        store.activate(staging, "v1", {"parquet_files": 1, "rows": 1})
    original = store.path_for("v1")
    assert original.exists()

    with store.stage("v1") as staging:
        (staging / "a.parquet").write_bytes(b"SECOND")
        store.activate(staging, "v1", {"parquet_files": 1, "rows": 1})

    # The active snapshot is intact and now holds the new content; at no point
    # was the only copy deleted ahead of a rename that might fail.
    assert store.is_verified(store.current_version())
    active = store.path_for(store.current_version())
    assert (active / "a.parquet").read_bytes() == b"SECOND"


def test_activate_does_not_rmtree_its_destination():
    import inspect

    src = inspect.getsource(SnapshotStore.activate)
    assert "rmtree(final" not in src and "rmtree(destination" not in src, (
        "activation deletes its destination before renaming; a failed rename "
        "would then leave no snapshot at all"
    )


# --- 6. canonical archive paths --------------------------------------------

def test_alias_members_resolving_to_one_target_are_rejected(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, body in (("dir/data.parquet", b"FIRST"),
                           ("dir/./data.parquet", b"SECOND")):
            ti = tarfile.TarInfo(name); ti.size = len(body)
            tar.addfile(ti, io.BytesIO(body))
    path = tmp_path / "alias.tar"; path.write_bytes(buf.getvalue())
    with pytest.raises(ArchiveRejected) as ei:
        safe_extract(path, tmp_path / "out")
    assert ei.value.rule in ("duplicate_member", "conflicting_member")


@pytest.mark.parametrize(
    "first, second",
    [
        ("a/b.parquet", "a/./b.parquet"),
        ("a/b.parquet", "./a/b.parquet"),
        ("a/b.parquet", "a//b.parquet"),
        ("./x.parquet", "x.parquet"),
    ],
)
def test_every_alias_form_is_caught(tmp_path, first, second):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in (first, second):
            ti = tarfile.TarInfo(name); ti.size = 4
            tar.addfile(ti, io.BytesIO(b"data"))
    path = tmp_path / "a.tar"; path.write_bytes(buf.getvalue())
    with pytest.raises(ArchiveRejected):
        safe_extract(path, tmp_path / "out")


def test_distinct_paths_are_still_accepted(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in ("a/x.parquet", "a/y.parquet", "b/x.parquet"):
            ti = tarfile.TarInfo(name); ti.size = 4
            tar.addfile(ti, io.BytesIO(b"data"))
    path = tmp_path / "ok.tar"; path.write_bytes(buf.getvalue())
    assert safe_extract(path, tmp_path / "out").files == 3


# --- 7. the manifest must be reloaded under the lock -----------------------

def test_a_waiter_does_not_downgrade_using_a_stale_pre_lock_manifest(tmp_path):
    """The holder activated v2; a waiter holding a v1 manifest must not install it."""
    v1, v2 = _bundle(b"V1DATA"), _bundle(b"V2DATA")
    o1, o2 = _objects("v1", v1), _objects("v2", v2)

    SnapshotRuntime(source=Src(o2), store=SnapshotStore(tmp_path)).boot()
    assert SnapshotStore(tmp_path).current_version() == "v2"

    class StaleThenCurrent:
        """Advertises v1 on the pre-lock read and v2 once under the lock."""

        def __init__(self):
            self.objects = {**o1, **o2}
            self.pointer_reads = 0

        def read_bytes(self, name, *, max_bytes=None):
            if name == "current.json":
                self.pointer_reads += 1
                version = "v1" if self.pointer_reads == 1 else "v2"
                return json.dumps({"current_manifest": f"m-{version}.json"}).encode()
            return self.objects[name]

        def open_stream(self, name):
            return Src(self.objects).open_stream(name)

    source = StaleThenCurrent()
    report = SnapshotRuntime(source=source, store=SnapshotStore(tmp_path)).boot()

    assert source.pointer_reads >= 2, "the manifest was not reloaded under the lock"
    assert SnapshotStore(tmp_path).current_version() == "v2", "downgraded to v1"
    assert report.version == "v2"
