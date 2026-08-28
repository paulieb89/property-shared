"""Red-first tests for bundling and for the manifest the runtime will read.

The published manifest is the narrowest interface in this PR: `SnapshotManifest`
is frozen and `extra="forbid"`, so a build that publishes the prototype's richer
manifest does not degrade -- it fails to parse at boot. These tests pin the
shape, and the richer provenance is kept in a separate report the runtime never
reads.
"""

from __future__ import annotations

import hashlib
import json
import tarfile
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")
zstandard = pytest.importorskip("zstandard",
                                reason="needs the optional 'snapshot' extra")

from property_core.snapshot.models import SnapshotManifest  # noqa: E402
from tools.ppd_snapshot.build import BuildRequest, build_snapshot  # noqa: E402
from tools.ppd_snapshot.package import (  # noqa: E402
    BundleMismatch,
    VersionAlreadyPublished,
    package_release,
    snapshot_version,
    verify_bundle,
)
from tests.snapshot.build_fixtures import csv_row, write_source_csv  # noqa: E402

COVERAGE_TO = date(2026, 6, 30)


@pytest.fixture
def released(tmp_path: Path):
    csv_path = write_source_csv(tmp_path / "pp.csv", [
        csv_row("{T-2024}", "B5 7AA", "2024-03-01 00:00", 210_000),
        csv_row("{T-2026}", "M3 7AA", "2026-06-30 00:00", 250_000),
    ])
    built = build_snapshot(BuildRequest(
        csv_path=csv_path, out_dir=tmp_path / "snapshot",
        coverage_to=COVERAGE_TO, temp_dir=tmp_path / "tmp"))
    release = package_release(
        built, dist_dir=tmp_path / "dist", candidate_root=tmp_path / "work",
        version=snapshot_version(datetime(2026, 8, 28, 10, 15, tzinfo=timezone.utc)),
        source={"file": "pp.csv", "sha256": "a" * 64, "etag": '"abc"'},
        facts={"rows_per_year": {"2024": 1, "2026": 1}},
    )
    return built, release


def members(bundle: Path) -> list[tarfile.TarInfo]:
    with open(bundle, "rb") as fh:
        with zstandard.ZstdDecompressor().stream_reader(fh) as reader:
            with tarfile.open(fileobj=reader, mode="r|") as tar:
                return list(tar)


# -- version ----------------------------------------------------------------

def test_version_is_the_utc_build_instant():
    stamp = datetime(2026, 8, 28, 10, 15, 30, tzinfo=timezone.utc)
    assert snapshot_version(stamp) == "v20260828T101530Z"


def test_version_is_a_path_component_the_store_will_accept():
    from property_core.snapshot.models import validate_component

    version = snapshot_version(datetime(2026, 8, 28, tzinfo=timezone.utc))
    assert validate_component(version, "snapshot_version") == version


# -- bundle -----------------------------------------------------------------

def test_bundle_holds_exactly_the_partition_files(released):
    _, release = released
    names = sorted(m.name for m in members(release.bundle_path))
    assert names == [f"year={y}/data.parquet" for y in range(2016, 2027)]


def test_bundle_holds_no_directory_or_special_members(released):
    _, release = released
    assert all(m.isreg() for m in members(release.bundle_path))


def test_bundle_carries_no_manifest_of_its_own(released):
    # The verification record is written by the store at activation. A manifest
    # inside the archive would become part of the inventory and could disagree
    # with the published one.
    _, release = released
    assert not any(m.name.endswith(".json") for m in members(release.bundle_path))


def test_bundle_members_are_normalised_for_reproducibility(released):
    _, release = released
    for member in members(release.bundle_path):
        assert member.uid == 0 and member.gid == 0
        assert member.uname == "" and member.gname == ""
        assert member.mtime == 0


# -- published manifest -----------------------------------------------------

def test_published_manifest_parses_as_the_runtime_manifest(released):
    _, release = released
    payload = json.loads(release.manifest_path.read_text())
    manifest = SnapshotManifest(**payload)
    assert manifest.snapshot_version == release.version
    assert manifest.parquet_files == 11
    assert manifest.layout == "year"


def test_published_manifest_carries_only_the_fields_the_runtime_allows(released):
    _, release = released
    payload = json.loads(release.manifest_path.read_text())
    assert set(payload) == {
        "snapshot_version", "bundle_object", "bundle_sha256", "bundle_bytes",
        "parquet_files", "rows", "coverage_from", "coverage_to",
        "provisional_from", "layout", "duckdb_version",
    }


def test_published_manifest_declares_the_bundle_on_disk(released):
    _, release = released
    payload = json.loads(release.manifest_path.read_text())
    blob = release.bundle_path.read_bytes()
    assert payload["bundle_bytes"] == len(blob)
    assert payload["bundle_sha256"] == hashlib.sha256(blob).hexdigest()
    assert payload["bundle_object"] == release.bundle_path.name


def test_published_manifest_declares_the_coverage_window(released):
    built, release = released
    payload = json.loads(release.manifest_path.read_text())
    assert payload["coverage_from"] == built.coverage_from.isoformat()
    assert payload["coverage_to"] == built.coverage_to.isoformat()
    assert payload["provisional_from"] == built.provisional_from.isoformat()


def test_current_json_names_the_manifest_object(released):
    _, release = released
    pointer = json.loads(release.current_path.read_text())
    assert pointer == {"current_manifest": release.manifest_path.name}


# -- build report -----------------------------------------------------------

def test_build_report_keeps_the_provenance_the_manifest_may_not_carry(released):
    _, release = released
    report = json.loads(release.report_path.read_text())
    assert report["source"]["sha256"] == "a" * 64
    assert report["rows_per_year"] == {"2024": 1, "2026": 1}
    assert report["snapshot_version"] == release.version
    assert "timings_seconds" in report


# -- digest verification ----------------------------------------------------

def test_verify_bundle_accepts_the_bundle_it_published(released):
    _, release = released
    verify_bundle(release.bundle_path, expected_sha256=release.bundle_sha256,
                  expected_bytes=release.bundle_bytes)


def test_verify_bundle_rejects_a_flipped_byte(released):
    _, release = released
    blob = bytearray(release.bundle_path.read_bytes())
    blob[len(blob) // 2] ^= 0x01
    release.bundle_path.write_bytes(bytes(blob))
    with pytest.raises(BundleMismatch, match="sha256"):
        verify_bundle(release.bundle_path, expected_sha256=release.bundle_sha256,
                      expected_bytes=release.bundle_bytes)


def test_verify_bundle_rejects_a_length_that_disagrees(released):
    _, release = released
    with pytest.raises(BundleMismatch, match="bytes"):
        verify_bundle(release.bundle_path, expected_sha256=release.bundle_sha256,
                      expected_bytes=release.bundle_bytes + 1)


# -- immutability -----------------------------------------------------------

def test_publishing_the_same_version_twice_is_refused(released, tmp_path):
    built, release = released
    with pytest.raises(VersionAlreadyPublished):
        package_release(built, dist_dir=release.dist_dir,
                        candidate_root=release.candidate_dir.parent,
                        version=release.version, source={}, facts={})


# -- candidate, then promotion ----------------------------------------------

def test_packaging_writes_into_a_candidate_directory(released):
    _, release = released
    assert release.candidate_dir.name == f"candidate-{release.version}"
    assert release.candidate_dir.parent == release.dist_dir.parent / "work"
    assert release.bundle_path.parent == release.candidate_dir
    assert release.manifest_path.parent == release.candidate_dir


def test_packaging_leaves_the_dist_root_empty(released):
    _, release = released
    assert not release.dist_dir.exists() or \
        list(release.dist_dir.iterdir()) == []


def test_the_candidate_carries_its_own_pointer_so_it_can_be_booted(released):
    _, release = released
    pointer = json.loads((release.candidate_dir / "current.json").read_text())
    assert pointer == {"current_manifest": release.manifest_path.name}


def test_promotion_moves_the_release_into_the_dist_root(released):
    from tools.ppd_snapshot.package import promote_release

    _, release = released
    promoted = promote_release(release)
    assert sorted(p.name for p in release.dist_dir.iterdir()) == sorted([
        "current.json", release.manifest_path.name, release.bundle_path.name,
        release.report_path.name])
    assert promoted.bundle_path.parent == release.dist_dir
    assert not release.candidate_dir.exists()


def test_promotion_writes_the_pointer_last(released, monkeypatch):
    """A pointer is a promise that what it names is there.

    If promotion dies half way, the dist root may hold a partial release -- but
    it must never hold a `current.json` naming a manifest that was not moved.
    """
    from tools.ppd_snapshot import package as pkg

    _, release = released
    real_move = pkg.shutil.move

    def _fail_on_manifest(src, dst, *args, **kwargs):
        if "manifest" in str(dst):
            raise OSError("disk went away")
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr(pkg.shutil, "move", _fail_on_manifest)
    with pytest.raises(OSError):
        pkg.promote_release(release)
    assert not (release.dist_dir / "current.json").exists()


# -- the candidate lives outside dist; the pointer is replaced atomically ----

def test_the_candidate_is_not_inside_the_dist_root(released):
    _, release = released
    assert release.dist_dir not in release.candidate_dir.parents
    assert not release.dist_dir.exists() or \
        list(release.dist_dir.iterdir()) == []


def test_an_interrupted_promotion_leaves_a_previous_pointer_untouched(
        released, monkeypatch):
    """A dist root with a working release must survive a failed promotion.

    Truncating `current.json` and then dying takes down the release that was
    already published, which is worse than never having tried: the pointer is
    the one file a booting Machine reads first.
    """
    from tools.ppd_snapshot import package as pkg

    _, release = released
    release.dist_dir.mkdir(parents=True, exist_ok=True)
    previous = release.dist_dir / "current.json"
    previous.write_text(json.dumps({"current_manifest": "manifest-v1.json"}))
    before = previous.read_bytes()

    real_move = pkg.shutil.move
    monkeypatch.setattr(pkg.shutil, "move", lambda src, dst, *a, **k: (
        (_ for _ in ()).throw(OSError("disk went away")) if "manifest" in str(dst)
        else real_move(src, dst, *a, **k)))

    with pytest.raises(OSError):
        pkg.promote_release(release)
    assert previous.read_bytes() == before


def test_a_pointer_write_that_fails_leaves_the_previous_one_intact(
        released, monkeypatch):
    from tools.ppd_snapshot import package as pkg

    _, release = released
    release.dist_dir.mkdir(parents=True, exist_ok=True)
    previous = release.dist_dir / "current.json"
    previous.write_text(json.dumps({"current_manifest": "manifest-v1.json"}))
    before = previous.read_bytes()

    monkeypatch.setattr(pkg.os, "replace", lambda *a, **k: (
        _ for _ in ()).throw(OSError("rename failed")))
    with pytest.raises(OSError):
        pkg.promote_release(release)
    assert previous.read_bytes() == before
    assert json.loads(previous.read_text())["current_manifest"] == "manifest-v1.json"


def test_promotion_replaces_an_existing_pointer(released):
    from tools.ppd_snapshot.package import promote_release

    _, release = released
    release.dist_dir.mkdir(parents=True, exist_ok=True)
    (release.dist_dir / "current.json").write_text(
        json.dumps({"current_manifest": "manifest-v1.json"}))
    promoted = promote_release(release)
    assert json.loads(promoted.current_path.read_text()) == {
        "current_manifest": release.manifest_path.name}
    assert not list(release.dist_dir.glob("*.tmp"))
