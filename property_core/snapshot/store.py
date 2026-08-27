"""On-disk snapshot store: staging, atomic activation, retention.

Layout under the store root:

    snapshots/<version>/           a verified, extracted snapshot
    snapshots/<version>/.verified.json
    staging/<version>.<rand>/      an attempt in progress; never served
    CURRENT                        the active version, flipped atomically

The serving snapshot is never mutated in place. A new one is staged, verified,
then moved into place with a single rename, and only then does the pointer flip.
Any failure leaves the previous snapshot exactly as it was.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

VERIFIED_RECORD = ".verified.json"
#: Current plus one previous. Retaining the previous makes rollback a pointer
#: flip rather than a re-download.
DEFAULT_KEEP = 2


class SnapshotStore:
    def __init__(self, root):
        self.root = Path(root)
        self.snapshots_dir = self.root / "snapshots"
        self.staging_dir = self.root / "staging"
        self.current_file = self.root / "CURRENT"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    # -- layout ---------------------------------------------------------
    def path_for(self, version: str) -> Path:
        return self.snapshots_dir / version

    def versions(self) -> list[str]:
        return [p.name for p in self.snapshots_dir.iterdir() if p.is_dir()]

    def staging_residue(self) -> list[str]:
        return sorted(p.name for p in self.staging_dir.iterdir())

    # -- pointer --------------------------------------------------------
    def current_version(self) -> Optional[str]:
        try:
            return self.current_file.read_text().strip() or None
        except FileNotFoundError:
            return None

    def set_current(self, version: str) -> None:
        """Flip the pointer atomically: write beside it, then rename over it."""
        tmp = self.current_file.with_suffix(".tmp")
        tmp.write_text(version)
        os.replace(tmp, self.current_file)

    # -- verification ---------------------------------------------------
    def verified_record(self, version: str) -> Optional[dict[str, Any]]:
        try:
            return json.loads((self.path_for(version) / VERIFIED_RECORD).read_text())
        except (FileNotFoundError, json.JSONDecodeError, NotADirectoryError):
            return None

    def is_verified(self, version: str) -> bool:
        """Whether this version is present AND matches its verification record.

        The record is not taken on trust: its file count is re-counted on disk,
        so a truncated or half-copied directory is not mistaken for a good one.
        """
        record = self.verified_record(version)
        directory = self.path_for(version)
        if not record or not directory.is_dir():
            return False
        declared = record.get("parquet_files")
        if declared is None:
            return False
        actual = sum(1 for _r, _d, files in os.walk(directory)
                     for f in files if f.endswith(".parquet"))
        return actual == declared

    # -- staging and activation ----------------------------------------
    @contextmanager
    def stage(self, version: str) -> Iterator[Path]:
        """A private directory for one attempt, removed unless activated.

        Removed on success too: `activate` renames it away, so anything left
        here is by definition an abandoned attempt.
        """
        staging = Path(tempfile.mkdtemp(prefix=f"{version}.", dir=self.staging_dir))
        try:
            yield staging
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def activate(self, staging: Path, version: str,
                 record: dict[str, Any]) -> Path:
        """Move a verified staging directory into place and flip the pointer."""
        staging = Path(staging)
        (staging / VERIFIED_RECORD).write_text(json.dumps(record, indent=2))

        final = self.path_for(version)
        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        # Atomic within the store filesystem: the directory appears complete or
        # not at all. Nothing ever observes a half-populated version.
        os.replace(staging, final)
        self.set_current(version)
        return final

    # -- retention ------------------------------------------------------
    def prune(self, keep: int = DEFAULT_KEEP) -> list[str]:
        """Retain the current version plus the most recent others; drop the rest."""
        current = self.current_version()
        others = sorted((v for v in self.versions() if v != current), reverse=True)
        retain = {v for v in (current, *others[: max(0, keep - 1)]) if v is not None}
        removed = []
        for version in self.versions():
            if version not in retain:
                shutil.rmtree(self.path_for(version), ignore_errors=True)
                removed.append(version)
        return removed

    def clear_staging(self) -> None:
        for entry in self.staging_dir.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
