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

from property_core.snapshot.models import validate_component

VERIFIED_RECORD = ".verified.json"
#: One active snapshot. Not "current plus previous": the filesystem does not
#: survive a restart, so a retained previous version buys nothing and would
#: misrepresent the store as durable.
DEFAULT_KEEP = 1


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
    def verified_record(self, version: str) -> Optional[dict[str, Any]]:
        try:
            return json.loads((self.path_for(version) / VERIFIED_RECORD).read_text())
        except (FileNotFoundError, json.JSONDecodeError, NotADirectoryError):
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
        if not record or not directory.is_dir():
            return False
        declared = record.get("inventory")
        if not isinstance(declared, dict) or not declared:
            return False
        return self.inventory(directory) == {str(k): int(v)
                                             for k, v in declared.items()}

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
        """Move a verified staging directory into place and flip the pointer.

        **Version directories are immutable.** A rebuild of the same version
        lands in a fresh generation directory rather than replacing the existing
        one in place. Deleting the destination before the rename meant a failed
        rename left no snapshot at all -- destroying the only good copy to make
        room for one that never arrived.
        """
        staging = Path(staging)
        record = {**record, "inventory": self.inventory(staging)}
        (staging / VERIFIED_RECORD).write_text(json.dumps(record, indent=2))

        target = self.path_for(version)
        if target.exists():
            # Never reuse an occupied name. A generation suffix keeps the old
            # directory whole until the pointer has moved; pruning removes it.
            # The suffix uses '.', which is a valid component character, so the
            # resulting name still passes the same boundary validation.
            generation = 1
            while target.exists():
                target = self.path_for(f"{version}.{generation}")
                generation += 1

        # Atomic within the store filesystem: the directory appears complete or
        # not at all. Nothing ever observes a half-populated version.
        os.replace(staging, target)
        self._write_pointer(target.name)
        return target

    def _write_pointer(self, directory_name: str) -> None:
        tmp = self.current_file.with_suffix(".tmp")
        tmp.write_text(directory_name)
        os.replace(tmp, self.current_file)

    # -- retention ------------------------------------------------------
    def version_of(self, directory_name: str) -> str:
        """The manifest version a directory holds, stripping any generation."""
        return directory_name.split(".")[0]

    def prune(self, keep: int = DEFAULT_KEEP) -> list[str]:
        """Drop every materialization except the active one.

        Superseded generations of the same version are removed here, which is
        why activation can afford to leave the old directory whole.

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
