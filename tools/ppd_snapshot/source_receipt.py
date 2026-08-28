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

Writing a receipt refuses unless those agree, and every build re-checks the file
against its receipt and the receipt against the latest observation. Any
disagreement stops the build: a snapshot that cannot say which release it came
from has no provenance, whatever its gates say.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tools.ppd_snapshot.release_check import ReleaseObservation

CHUNK_BYTES = 1024 * 1024


class SourceMismatch(RuntimeError):
    """The file, its receipt and the observed release do not describe one thing."""


@dataclass(frozen=True)
class SourceReceipt:
    file: str
    sha256: str
    bytes: int
    etag: Optional[str]
    last_modified: Optional[str]
    content_length: Optional[int]
    recorded_at: str

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
                  receipt_path: Path | str, *,
                  now: Optional[datetime] = None) -> SourceReceipt:
    """Record what this file is, refusing if it is not what the release says.

    The length comparison is the one that catches a stale download: a file that
    is not the size the release declares is not that release, whatever it is
    named.
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

    receipt = SourceReceipt(
        file=csv_path.name, sha256=digest, bytes=length,
        etag=observation.etag, last_modified=observation.last_modified,
        content_length=observation.content_length,
        recorded_at=(now or datetime.now(timezone.utc)).isoformat())
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(asdict(receipt), indent=2) + "\n")
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
