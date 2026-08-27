"""Ephemeral boot materialization of a snapshot.

**No durability claim.** Both production Machines run on Fly's default root
filesystem with no Volume and no `persist_rootfs`, so everything here is wiped on
restart and on deploy. What this store provides is a *materialization*: a
verified snapshot unpacked once per Machine lifetime and shared by the workers on
that Machine, serving as their read-only query database.

What it deliberately does NOT provide:

* **Retention across restarts.** Exactly one active snapshot is kept. Retaining a
  "previous" version would imply a rollback path that does not survive the very
  events -- restart, deploy -- a rollback is for.
* **A cache to fall back on.** A snapshot is not available after a restart, so it
  cannot be the answer to a source outage. That answer is the live source.

Layout under the store root:

    snapshots/<version>/           a verified, materialized snapshot
    snapshots/<version>/.verified.json
    staging/<version>.<rand>/      an attempt in progress; never served
    CURRENT                        the active version, flipped atomically

The active snapshot is never mutated in place. A new one is staged, verified,
then moved into place with a single rename, and only then does the pointer flip.
Any failure leaves whatever was active exactly as it was, for the remainder of
this Machine's lifetime.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from property_core.snapshot.models import VerificationRecord, validate_component

VERIFIED_RECORD = ".verified.json"
#: One active snapshot. Not "current plus previous": the filesystem does not
#: survive a restart, so a retained previous version buys nothing and would
#: misrepresent the store as durable.
DEFAULT_KEEP = 1


class VersionAlreadyMaterialized(ValueError):
    """A different bundle was published under an already-materialized version.

    **Published versions are immutable.** One version identifies one set of
    bytes; if the bytes change, the publisher must issue a new version.
    Re-materialising under the same name was how one published version came to
    identify several different snapshots.
    """


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
        """The directory for a version, refusing anything that is not one.

        Revalidated here rather than trusted from the manifest: this is the
        boundary that turns a string into a filesystem path.
        """
        return self.snapshots_dir / validate_component(version, "version")

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
        validate_component(version, "version")
        tmp = self.current_file.with_suffix(".tmp")
        tmp.write_text(version)
        os.replace(tmp, self.current_file)

    # -- verification ---------------------------------------------------
    def verified_record(self, version: str) -> Optional[VerificationRecord]:
        """The parsed record, or None if absent or malformed.

        Every failure returns None rather than raising: this is consulted on the
        readiness path, and a malformed record must make the snapshot unusable,
        not make boot explode. A bad `inventory` value previously raised
        ValueError straight out of the readiness check.
        """
        try:
            raw = json.loads((self.path_for(version) / VERIFIED_RECORD).read_text())
            return VerificationRecord(**raw)
        except Exception:
            return None

    @staticmethod
    def inventory(directory: Path) -> dict[str, int]:
        """Relative path -> size for every file, excluding the record itself.

        Sizes, not just names: a count matched while a file was truncated to a
        single byte, so the directory reported verified with unusable contents.
        """
        directory = Path(directory)
        out: dict[str, int] = {}
        for root, _dirs, files in os.walk(directory):
            for name in files:
                path = Path(root) / name
                rel = path.relative_to(directory).as_posix()
                if rel == VERIFIED_RECORD:
                    continue
                out[rel] = path.stat().st_size
        return out

    def is_verified(self, version: str) -> bool:
        """Whether this version is present AND matches its verification record.

        The record is not taken on trust. The full file inventory -- every
        relative path and its size -- must match exactly, so a truncated,
        extended or half-copied directory is never mistaken for a good one.
        """
        try:
            directory = self.path_for(version)
        except ValueError:
            return False
        record = self.verified_record(version)
        if record is None or not directory.is_dir():
            return False
        try:
            return self.inventory(directory) == record.inventory
        except OSError:
            return False

    # -- staging and activation ----------------------------------------
    @contextmanager
    def stage(self, version: str) -> Iterator[Path]:
        """A private directory for one attempt, removed unless activated.

        Removed on success too: `activate` renames it away, so anything left
        here is by definition an abandoned attempt.
        """
        # The version reaches mkdtemp as a filename prefix, so "../escaped"
        # produced a staging directory outside the store. Validated here as at
        # every other entry point.
        version = validate_component(version, "version")
        staging = Path(tempfile.mkdtemp(prefix=f"{version}.", dir=self.staging_dir))
        try:
            yield staging
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def activate(self, staging: Path, version: str,
                 record: dict[str, Any]) -> Path:
        """Move a verified staging directory into place and flip the pointer.

        **Published versions are immutable.** One version names one directory and
        one set of bytes. If the destination already exists this raises rather
        than replacing it: generation suffixes made a single published version
        identify several different snapshots, and deleting the destination first
        risked losing the only good copy to a rename that never completed.
        """
        staging = Path(staging)
        version = validate_component(version, "version")
        target = self.path_for(version)
        if target.exists():
            raise VersionAlreadyMaterialized(
                f"version {version!r} is already materialized at {target}; "
                f"a changed bundle requires a new published version"
            )

        # Validated on the way in, so a malformed record is never written.
        parsed = VerificationRecord(**{**record, "version": version,
                                       "inventory": self.inventory(staging)})
        (staging / VERIFIED_RECORD).write_text(parsed.model_dump_json(indent=2))

        # Atomic within the store filesystem: the directory appears complete or
        # not at all. Nothing ever observes a half-populated version.
        os.replace(staging, target)
        self.set_current(version)
        return target

    # -- retention ------------------------------------------------------
    def prune(self, keep: int = DEFAULT_KEEP) -> list[str]:
        """Drop every materialization except the active one.

        `keep` is retained as a parameter for tests and for a future durable
        store; production uses the default of one.
        """
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
