"""Write a file without destroying the one already there.

`write_text` truncates before it writes. Interrupted, it leaves an empty or
half-written file where a valid one used to be -- which for a published pointer
or a source receipt is worse than never having tried, because it takes down what
was already working. Every write in this package that replaces an existing
document goes through here: write a unique sibling, then rename over the target.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def prepare_write_text(path: Path | str, text: str) -> Path:
    """Write `text` to a sibling temporary file and return it, unpublished.

    Split from the rename so a caller replacing SEVERAL files can get all the
    writing -- the part that runs out of disk -- done before any of the renames.
    Nothing the caller had is touched until it commits.

    The temporary file is a sibling so the rename stays within one filesystem
    (`os.replace` cannot cross devices), and uniquely named so two writers
    cannot collide on it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=path.parent,
                                        prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        # fdopen immediately: until a file object owns the descriptor, nothing
        # closes it on an error path.
        with os.fdopen(handle, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        try:
            os.close(handle)
        except OSError:
            pass
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def commit_prepared(tmp: Path | str, path: Path | str) -> None:
    """Rename a prepared file over its target."""
    os.replace(tmp, path)


def atomic_write_text(path: Path | str, text: str) -> None:
    """Replace `path` with `text`, or leave `path` exactly as it was."""
    tmp = prepare_write_text(path, text)
    try:
        commit_prepared(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def prepare_write_json(path: Path | str, payload: Any) -> Path:
    return prepare_write_text(path, json.dumps(payload, indent=2) + "\n")


def atomic_write_json(path: Path | str, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2) + "\n")
