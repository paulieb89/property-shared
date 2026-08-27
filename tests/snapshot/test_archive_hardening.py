"""Adversarial archive tests. No member may escape the staging directory."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from property_core.snapshot.archive import ExtractionLimits, safe_extract
from property_core.snapshot.errors import ArchiveRejected

from tests.snapshot.archive_fixtures import build_tar, dev, directory, hard, reg, sym


def _write(tmp_path: Path, blob: bytes) -> Path:
    p = tmp_path / "bundle.tar"
    p.write_bytes(blob)
    return p


def _extract(tmp_path: Path, members, *, limits=None, payload=b"x" * 64):
    dest = tmp_path / "staging"
    dest.mkdir()
    return safe_extract(_write(tmp_path, build_tar(members, payload)), dest, limits)


@pytest.mark.parametrize(
    "name, rule",
    [
        ("../escape.txt", "path_traversal"),
        ("a/b/../../../escape.txt", "path_traversal"),
        ("/tmp/escape.txt", "absolute_path"),
        ("..", "path_traversal"),
        ("dir/../../out.txt", "path_traversal"),
    ],
)
def test_traversal_and_absolute_paths_are_rejected(tmp_path, name, rule):
    with pytest.raises(ArchiveRejected) as ei:
        _extract(tmp_path, [reg(name)])
    assert ei.value.rule == rule


def test_backslash_names_are_rejected(tmp_path):
    with pytest.raises(ArchiveRejected) as ei:
        _extract(tmp_path, [reg("dir\\..\\escape.txt")])
    assert ei.value.rule == "backslash_in_name"


def test_null_bytes_in_names_are_rejected():
    """Asserted on the validator: tarfile truncates at the NUL, so no real
    archive can carry such a name -- but the guard must still exist."""
    from property_core.snapshot.archive import _name_violation

    assert _name_violation("bad\x00name") == "null_byte_in_name"


@pytest.mark.parametrize(
    "member, rule",
    [
        (sym("link", "/etc/passwd"), "symlink"),
        (sym("link", "../outside"), "symlink"),
        (hard("hl", "/etc/passwd"), "hardlink"),
        (dev("node", "chr"), "special_file"),
        (dev("node", "blk"), "special_file"),
        (dev("node", "fifo"), "special_file"),
    ],
)
def test_link_and_device_members_are_rejected(tmp_path, member, rule):
    with pytest.raises(ArchiveRejected) as ei:
        _extract(tmp_path, [member])
    assert ei.value.rule == rule


def test_symlink_then_write_through_it_is_rejected(tmp_path):
    with pytest.raises(ArchiveRejected):
        _extract(tmp_path, [sym("d", "/tmp"), reg("d/escape.txt")])


def test_duplicate_member_paths_are_rejected(tmp_path):
    with pytest.raises(ArchiveRejected) as ei:
        _extract(tmp_path, [reg("dup.bin"), reg("dup.bin")])
    assert ei.value.rule == "duplicate_member"


def test_conflicting_file_and_directory_paths_are_rejected(tmp_path):
    with pytest.raises(ArchiveRejected):
        _extract(tmp_path, [reg("thing"), directory("thing")])


def test_member_count_limit(tmp_path):
    members = [reg(f"f{i}.bin", 4) for i in range(12)]
    with pytest.raises(ArchiveRejected) as ei:
        _extract(tmp_path, members, limits=ExtractionLimits(max_members=5))
    assert ei.value.rule == "too_many_members"


def test_total_decompressed_size_limit(tmp_path):
    members = [reg(f"f{i}.bin", 32) for i in range(10)]
    with pytest.raises(ArchiveRejected) as ei:
        _extract(tmp_path, members, limits=ExtractionLimits(max_total_bytes=64))
    assert ei.value.rule == "decompressed_size_limit"


def test_single_member_size_limit(tmp_path):
    with pytest.raises(ArchiveRejected) as ei:
        _extract(tmp_path, [reg("big.bin", 128)], payload=b"x" * 128,
                 limits=ExtractionLimits(max_member_bytes=16))
    assert ei.value.rule == "member_too_large"


def test_nothing_is_written_outside_the_staging_directory(tmp_path):
    canary = tmp_path / "escape.txt"
    with pytest.raises(ArchiveRejected):
        _extract(tmp_path, [reg("../escape.txt")])
    assert not canary.exists()
    assert not Path("/tmp/escape.txt").exists()


def test_a_well_formed_bundle_extracts(tmp_path, bundle):
    dest = tmp_path / "staging"
    dest.mkdir()
    path = tmp_path / "b.tar"
    path.write_bytes(bundle)
    stats = safe_extract(path, dest)
    assert stats.files == 2
    assert (dest / "manifest.json").is_file()
    assert (dest / "year=2026" / "data.parquet").is_file()


@pytest.mark.parametrize(
    "filename", ["b.tar", "b.tar.gz", "b.tgz", "b.tar.bz2", "b.tar.xz", "b.tar.zst"]
)
def test_every_supported_format_opens_in_streaming_mode(filename):
    """Streaming ('r|') means members are validated as they arrive; a seekable
    mode would let tarfile index a hostile archive first."""
    from property_core.snapshot.archive import _tar_mode

    mode = _tar_mode(Path(filename))
    assert mode.startswith("r|"), f"{filename} opens non-streaming: {mode}"
