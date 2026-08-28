"""Bind the local CSV to the release it claims to be.

Without this the pipeline validated an artifact and never asked what it was
built from. A 131-byte stale CSV built cleanly while the release record claimed
999,999,999 bytes under a different ETag, and the result booted READY: every
gate downstream checks the snapshot against itself, so an internally consistent
snapshot of the wrong data passes all of them.

A receipt is the binding, and it is deliberately made of two different kinds of
evidence:

* **computed from the file** -- SHA-256 and byte length, read off the bytes on
  disk;
* **observed from the release** -- `ETag`, `Last-Modified`, `Content-Length`, as
  the source reported them.

Those two alone are not enough, and the gap is worth stating plainly: a receipt
minted from a file and a set of validators binds *whatever bytes are on disk* to
*whatever release is claimed*, provided only that the lengths agree. Same-length
substitution passes. So minting also requires a digest captured **independently
of the file being read now**:

* `download_with_receipt` is the intended path -- it digests the bytes as they
  stream in, from the same response the validators come from, so the file, its
  digest and its release provenance all originate in one observation
  (`evidence: "streamed-download"`);
* for a file that already exists, the digest recorded when it was fetched must
  be supplied and must match (`evidence: "recorded-checksum"`). That is weaker,
  because it trusts a record made elsewhere, and the receipt says so.

Writing a receipt refuses unless those agree, and every build re-checks the file
against its receipt and the receipt against the latest observation. Any
disagreement stops the build: a snapshot that cannot say which release it came
from has no provenance, whatever its gates say.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tools.ppd_snapshot.atomic import (
    atomic_write_json,
    commit_prepared,
    prepare_write_json,
)
from tools.ppd_snapshot.release_check import ReleaseObservation

CHUNK_BYTES = 1024 * 1024


class SourceMismatch(RuntimeError):
    """The file, its receipt and the observed release do not describe one thing."""


class ReceiptRollbackFailed(RuntimeError):
    """A commit failed and the previous release could not be put back.

    The backup is the only copy of it at that moment, so it is **kept** and its
    path is reported. Deleting it to tidy up turns a recoverable half-commit
    into an unrecoverable one: the destination holds the new bytes, the receipt
    still describes the old ones, and nothing on disk can reconcile them.
    """

    def __init__(self, message: str, *, backup_path: Path):
        super().__init__(message)
        self.backup_path = backup_path


@dataclass(frozen=True)
class SourceReceipt:
    file: str
    sha256: str
    bytes: int
    etag: Optional[str]
    last_modified: Optional[str]
    content_length: Optional[int]
    recorded_at: str
    #: Where the digest came from. "streamed-download" means it was computed
    #: from the response that also carried the validators; "recorded-checksum"
    #: means it was taken on trust from a record made at some earlier fetch.
    evidence: str = "recorded-checksum"

    def observation(self) -> ReleaseObservation:
        return ReleaseObservation(etag=self.etag,
                                  last_modified=self.last_modified,
                                  content_length=self.content_length)


def digest_file(path: Path | str) -> tuple[int, str]:
    """Length and SHA-256, streamed. A 5.5 GB file is never held in memory."""
    digest = hashlib.sha256()
    length = 0
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK_BYTES):
            digest.update(chunk)
            length += len(chunk)
    return length, digest.hexdigest()


def write_receipt(csv_path: Path | str, observation: ReleaseObservation,
                  receipt_path: Path | str, *, expected_sha256: str,
                  evidence: str = "recorded-checksum",
                  now: Optional[datetime] = None) -> SourceReceipt:
    """Record what this file is, refusing if it is not what the release says.

    `expected_sha256` is required, and is the point of the function: the length
    comparison catches a stale download, but only the digest catches a file of
    the right size holding different bytes. Without it a receipt would bind any
    same-length content to any release.
    """
    csv_path = Path(csv_path)
    receipt_path = Path(receipt_path)
    if observation.content_length is None:
        raise SourceMismatch(
            "the release observation carries no Content-Length, so the local "
            "file cannot be shown to be that release")

    length, digest = digest_file(csv_path)
    if length != observation.content_length:
        raise SourceMismatch(
            f"{csv_path.name} is {length} bytes but the observed release "
            f"declares {observation.content_length}; this file is not that "
            f"release")
    if digest != expected_sha256:
        raise SourceMismatch(
            f"{csv_path.name} has sha256 {digest}, but the digest recorded when "
            f"this release was downloaded is {expected_sha256}; the file on "
            f"disk is not the one that was fetched")

    receipt = SourceReceipt(
        file=csv_path.name, sha256=digest, bytes=length,
        etag=observation.etag, last_modified=observation.last_modified,
        content_length=observation.content_length,
        recorded_at=(now or datetime.now(timezone.utc)).isoformat(),
        evidence=evidence)
    atomic_write_json(receipt_path, asdict(receipt))
    return receipt


def load_receipt(receipt_path: Path | str) -> SourceReceipt:
    """The receipt, or a refusal. There is no implied default."""
    receipt_path = Path(receipt_path)
    if not receipt_path.is_file():
        raise SourceMismatch(
            f"no source receipt at {receipt_path}; the CSV cannot be shown to "
            f"be any particular release, so the build stops")
    try:
        payload = json.loads(receipt_path.read_text())
        return SourceReceipt(**payload)
    except (OSError, ValueError, TypeError) as exc:
        raise SourceMismatch(
            f"the source receipt at {receipt_path} is unreadable: {exc}") from exc


def verify_source(csv_path: Path | str, receipt: SourceReceipt,
                  observation: Optional[ReleaseObservation]) -> None:
    """Refuse unless the file, its receipt and the latest observation agree.

    All three, not two: the file matching its receipt says the download has not
    rotted, and the receipt matching the observation says the release has not
    moved on since. Either alone leaves the build able to publish the wrong data
    under the right name.
    """
    csv_path = Path(csv_path)
    length, digest = digest_file(csv_path)
    if length != receipt.bytes:
        raise SourceMismatch(
            f"{csv_path.name} is {length} bytes; its receipt records "
            f"{receipt.bytes}")
    if digest != receipt.sha256:
        raise SourceMismatch(
            f"{csv_path.name} sha256 is {digest}; its receipt records "
            f"{receipt.sha256}")
    if receipt.content_length is not None and receipt.content_length != length:
        raise SourceMismatch(
            f"the receipt records a release Content-Length of "
            f"{receipt.content_length} for a file of {length} bytes")

    if observation is None:
        raise SourceMismatch(
            "no current release observation was supplied, so the receipt cannot "
            "be shown to describe the release that is published now")
    if observation.etag != receipt.etag:
        raise SourceMismatch(
            f"the published ETag {observation.etag!r} is not the one this file "
            f"was fetched under ({receipt.etag!r}); the release has moved")
    if observation.last_modified != receipt.last_modified:
        raise SourceMismatch(
            f"the published Last-Modified {observation.last_modified!r} is not "
            f"the one this file was fetched under ({receipt.last_modified!r})")
    if observation.content_length != receipt.content_length:
        raise SourceMismatch(
            f"the published Content-Length {observation.content_length} is not "
            f"the one this file was fetched under ({receipt.content_length})")


def download_with_receipt(url: str, dest: Path | str, receipt_path: Path | str,
                          *, opener=None, now: Optional[datetime] = None,
                          timeout: float = 300.0) -> SourceReceipt:
    """Stream a release to disk, digesting it as it arrives, and mint a receipt.

    This is the receipt path the pipeline is designed around: the bytes, the
    digest and the validators all come from **one** response, so there is no
    window in which the file could be something other than what the headers
    describe. Minting a receipt for a file that is merely sitting on disk is the
    fallback, and it is recorded as the weaker evidence it is.

    The body is streamed in fixed chunks and never held in memory, and it is
    streamed into a **unique sibling temporary file**, never into the
    destination. Writing the destination directly makes every refresh
    destructive: opening it truncates the release already held, so a transfer
    that dies half way leaves nothing where a working CSV was, next to a receipt
    that still describes it. The destination is replaced only once the length
    and digest have been checked, and a failure leaves the previous file and its
    receipt byte-for-byte intact.

    **Not exercised against the real host in this PR.** No download of the
    5.5 GB object is authorised here; the mechanism is tested against a loopback
    server.
    """
    import urllib.request

    dest = Path(dest)
    receipt_path = Path(receipt_path)
    if dest.resolve() == receipt_path.resolve():
        # Checked before anything is requested: otherwise the download succeeds
        # and the receipt is then written over the very file it describes.
        raise SourceMismatch(
            f"the destination and the receipt resolve to the same path "
            f"({dest}); the receipt would overwrite the release it describes")
    dest.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(
        url, headers={"User-Agent": "property-shared-snapshot-build/1"})

    handle, tmp_name = tempfile.mkstemp(dir=dest.parent,
                                        prefix=f".{dest.name}.", suffix=".part")
    tmp = Path(tmp_name)
    try:
        # The descriptor is adopted by a file object IMMEDIATELY. Anything that
        # fails between `mkstemp` and `fdopen` -- an opener that refuses to
        # connect, a header that will not parse -- leaves a raw descriptor that
        # nothing ever closes, and a daily check would leak one per attempt.
        out = os.fdopen(handle, "wb")
    except BaseException:
        os.close(handle)
        tmp.unlink(missing_ok=True)
        raise

    digest = hashlib.sha256()
    length = 0
    try:
        with out:
            with opener(request, timeout=timeout) as response:
                headers = response.headers
                declared = headers.get("Content-Length")
                observation = ReleaseObservation(
                    etag=headers.get("ETag"),
                    last_modified=headers.get("Last-Modified"),
                    content_length=int(declared)
                    if declared and declared.isdigit() else None)
                while chunk := response.read(CHUNK_BYTES):
                    out.write(chunk)
                    digest.update(chunk)
                    length += len(chunk)
            out.flush()
            os.fsync(out.fileno())

        if observation.content_length is None:
            raise SourceMismatch(
                f"{url} returned no Content-Length, so the transfer cannot be "
                f"shown to be complete")
        if length != observation.content_length:
            raise SourceMismatch(
                f"{url} declared Content-Length {observation.content_length} "
                f"but {length} bytes arrived; the transfer was interrupted")
    except BaseException:
        # The destination was never opened, so whatever was there is untouched.
        tmp.unlink(missing_ok=True)
        raise

    # The receipt is built from the digest computed AS THE BYTES ARRIVED rather
    # than by re-reading the file: re-reading would mean a second full pass over
    # 5.5 GB, and would digest a file that is no longer provably the one
    # received.
    receipt = SourceReceipt(
        file=dest.name, sha256=digest.hexdigest(), bytes=length,
        etag=observation.etag, last_modified=observation.last_modified,
        content_length=observation.content_length,
        recorded_at=(now or datetime.now(timezone.utc)).isoformat(),
        evidence="streamed-download")

    # The CSV and its receipt are ONE fact in two files, so both are written
    # before either is published. Replacing the CSV and then failing to write
    # the receipt destroys the previous valid pair: the old bytes are gone and
    # the surviving receipt describes a file that no longer exists.
    try:
        tmp_receipt = prepare_write_json(receipt_path, dataclasses.asdict(receipt))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    _publish_pair(tmp, dest, tmp_receipt, receipt_path)
    return receipt


def _discard(*paths: Optional[Path]) -> None:
    for path in paths:
        if path is not None:
            Path(path).unlink(missing_ok=True)


def _publish_pair(tmp_data: Path, dest: Path, tmp_receipt: Path,
                  receipt_path: Path) -> None:
    """Publish two staged files together, or leave the previous pair in place.

    An explicit transaction, because the interesting cases are all in the middle
    of it. The stages, in order:

        staged          both temporaries written; nothing on disk touched
        backed_up       the previous release renamed aside -- the backup is now
                        the ONLY copy of it
        dest_published  the new release is in place, the receipt is not
        published       both in place

    The backup is removed at exactly two points: after `published`, and after a
    restoration that was **confirmed to have worked**. Anywhere else it is what
    the previous release is recovered from, so it is kept -- including, and
    especially, when the restoration itself failed.
    """
    stage = "staged"
    backup: Optional[Path] = None
    try:
        if dest.exists():
            handle, name = tempfile.mkstemp(dir=dest.parent,
                                            prefix=f".{dest.name}.",
                                            suffix=".prev")
            os.close(handle)
            backup = Path(name)
            os.replace(dest, backup)
            stage = "backed_up"
        os.replace(tmp_data, dest)
        stage = "dest_published"
        os.replace(tmp_receipt, receipt_path)
        stage = "published"
    except BaseException as failure:
        if stage == "staged":
            # Nothing was moved. Any backup here is the empty placeholder
            # `mkstemp` made, not the previous release, so all three staging
            # files go.
            _discard(tmp_data, tmp_receipt, backup)
            raise
        try:
            if backup is not None:
                os.replace(backup, dest)
            else:
                # There was no previous release; the new one is withdrawn.
                Path(dest).unlink(missing_ok=True)
        except BaseException as restore_failure:
            _discard(tmp_data, tmp_receipt)
            raise ReceiptRollbackFailed(
                f"the download could not be committed ({failure}) and the "
                f"previous release could not be restored "
                f"({restore_failure}). {dest} now holds the NEW bytes while "
                f"{receipt_path} still describes the old ones. The previous "
                f"release has been RETAINED at {backup} -- move it back to "
                f"{dest}, or re-run the download.",
                backup_path=backup) from restore_failure
        # Restoration confirmed: the backup is redundant.
        _discard(tmp_data, tmp_receipt, backup)
        raise
    # Published: the backup is redundant.
    _discard(backup)
