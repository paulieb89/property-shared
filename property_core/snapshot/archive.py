"""Member-validating, streamed archive extraction.

No member may escape the staging directory. Every member is validated BEFORE it
is written, and the archive is read as a stream so a hostile member count or
decompressed size is bounded as it arrives rather than discovered afterwards.

Compression is pluggable. The snapshot bundle is `.tar.zst`, which neither
Python 3.11 nor a slim base image can read without help, so the codec is
resolved explicitly and its absence is an actionable typed error rather than a
confusing tar failure.
"""

from __future__ import annotations

import io
import os
import posixpath
import shutil
import subprocess
import tarfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Iterator

from property_core.snapshot.errors import ArchiveRejected, SnapshotExtraMissingError


@dataclass(frozen=True)
class ExtractionLimits:
    """Caps applied while the archive streams past.

    Defaults are sized for the full-history snapshot (32 year partitions, one
    parquet file each, unpacking to ~1.2 GB) with headroom, not for arbitrary
    archives.

    `max_total_bytes` is deliberately kept above what
    `fetch.DEFAULT_MAX_BUNDLE_BYTES` can deliver. A bundle is compressed, so a
    2 GiB bundle unpacks to more than 2 GiB of parquet; leaving these equal
    would mean the fetch ceiling admitted an archive that extraction then
    refused, which is a failure discovered after the whole transfer rather than
    before it.
    """

    max_members: int = 5_000
    max_total_bytes: int = 4 * 1024 ** 3
    max_member_bytes: int = 4 * 1024 ** 3


@dataclass(frozen=True)
class ExtractionStats:
    members: int
    files: int
    directories: int
    decompressed_bytes: int


#: Only these member kinds are ever written.
_ALLOWED_TYPES = frozenset({tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE})


def _canonical(name: str) -> str:
    """The path a member actually resolves to, as one canonical key.

    "dir/data.parquet", "dir/./data.parquet", "./dir/data.parquet" and
    "dir//data.parquet" all name the SAME target. Deduplicating on the raw name
    let the later member silently overwrite the earlier one; deduplicating on
    this key makes the collision visible.

    Called only after `_name_violation` has rejected traversal, so normpath
    cannot be used here to smuggle a "..".

    Only a leading "./" is removed, never leading dots: `lstrip("./")` stripped
    character-wise, collapsing ".hidden" onto "hidden" and treating two distinct
    files as one.
    """
    canonical = posixpath.normpath(name)
    while canonical.startswith("./"):
        canonical = canonical[2:]
    return "" if canonical in (".", "") else canonical


def _name_violation(name: str) -> str | None:
    if not name or name in (".", "./"):
        return None
    if "\x00" in name:
        return "null_byte_in_name"
    if "\\" in name:
        return "backslash_in_name"
    if name.startswith("/") or os.path.isabs(name):
        return "absolute_path"
    if any(part == ".." for part in name.split("/")):
        return "path_traversal"
    return None


@contextmanager
def _open_stream(path: Path) -> Iterator[IO[bytes]]:
    """Yield a readable byte stream for the archive, decompressing if needed."""
    name = path.name.lower()
    if name.endswith(".tar"):
        with open(path, "rb") as fh:
            yield fh
        return
    if name.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
        # Handled natively by tarfile's own stream modes.
        with open(path, "rb") as fh:
            yield fh
        return
    if name.endswith((".tar.zst", ".tzst")):
        try:
            import zstandard  # type: ignore
        except ImportError:
            zstd_bin = shutil.which("zstd")
            if not zstd_bin:
                raise SnapshotExtraMissingError(
                    feature="reading a .tar.zst snapshot bundle",
                    package="zstandard",
                ) from None
            proc = subprocess.Popen([zstd_bin, "-dc", str(path)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                assert proc.stdout is not None
                yield proc.stdout
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=30)
            return
        dctx = zstandard.ZstdDecompressor()
        with open(path, "rb") as fh:
            with dctx.stream_reader(fh) as reader:
                yield reader
        return
    raise ArchiveRejected("unsupported_archive_format", path.name)


def _tar_mode(path: Path) -> str:
    """Always a STREAM mode ('r|'): members are validated as they arrive, so a
    hostile archive cannot be indexed or seeked into first."""
    name = path.name.lower()
    if name.endswith((".tar.gz", ".tgz")):
        return "r|gz"
    if name.endswith(".tar.bz2"):
        return "r|bz2"
    if name.endswith(".tar.xz"):
        return "r|xz"
    return "r|"


def safe_extract(bundle: Path, dest: Path,
                 limits: ExtractionLimits | None = None) -> ExtractionStats:
    """Extract `bundle` into `dest`, validating every member first.

    Raises ArchiveRejected on the first violation, leaving the caller to discard
    the staging directory.
    """
    lim = limits or ExtractionLimits()
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    dest_real = os.path.realpath(dest)

    seen_files: set[str] = set()
    seen_dirs: set[str] = set()
    members = total = files = directories = 0

    with _open_stream(Path(bundle)) as stream:
        with tarfile.open(fileobj=stream, mode=_tar_mode(Path(bundle))) as tar:
            for member in tar:
                members += 1
                if members > lim.max_members:
                    raise ArchiveRejected("too_many_members", member.name,
                                          f"cap {lim.max_members}")

                violation = _name_violation(member.name)
                if violation:
                    raise ArchiveRejected(violation, member.name)

                if member.issym():
                    raise ArchiveRejected("symlink", member.name,
                                          f"-> {member.linkname}")
                if member.islnk():
                    raise ArchiveRejected("hardlink", member.name,
                                          f"-> {member.linkname}")
                if member.type not in _ALLOWED_TYPES:
                    # Devices, FIFOs, sockets and anything else we do not
                    # explicitly understand.
                    raise ArchiveRejected("special_file", member.name,
                                          f"type={member.type!r}")

                norm = _canonical(member.name)
                if norm:
                    if member.isdir():
                        if norm in seen_files:
                            raise ArchiveRejected("conflicting_member", member.name,
                                                  "already present as a file")
                        seen_dirs.add(norm)
                    else:
                        if norm in seen_files or norm in seen_dirs:
                            rule = ("duplicate_member" if norm in seen_files
                                    else "conflicting_member")
                            raise ArchiveRejected(rule, member.name)
                        seen_files.add(norm)

                if member.isreg():
                    if member.size > lim.max_member_bytes:
                        raise ArchiveRejected("member_too_large", member.name,
                                              str(member.size))
                    total += member.size
                    if total > lim.max_total_bytes:
                        raise ArchiveRejected("decompressed_size_limit", member.name,
                                              f"{total} > {lim.max_total_bytes}")

                target = os.path.realpath(os.path.join(dest_real, member.name))
                if target != dest_real and not target.startswith(dest_real + os.sep):
                    raise ArchiveRejected("escapes_staging_dir", member.name, target)

                tar.extract(member, dest_real, set_attrs=False)
                if member.isdir():
                    directories += 1
                else:
                    files += 1

    return ExtractionStats(members=members, files=files, directories=directories,
                           decompressed_bytes=total)
