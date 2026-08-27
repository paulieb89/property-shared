"""Single-flight boot locking.

Several workers in one machine start together; exactly one should download and
activate, and the rest should wait and then use what it produced.

`flock` is advisory and per-host, which is the right scope: the deployment shape
is many workers on one machine. It does NOT coordinate across machines, and one
fetch per machine is intended. A lock held by a process that dies is released by
the kernel, so a leftover lock FILE is never a wedged boot.
"""

from __future__ import annotations

import errno
import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_TIMEOUT = 420.0
_POLL_SECONDS = 0.05


class LockTimeout(TimeoutError):
    """Another starter held the lock for longer than we were willing to wait."""


@contextmanager
def single_flight(path, *, timeout: float = DEFAULT_TIMEOUT) -> Iterator[None]:
    """Hold an exclusive lock on `path` for the duration of the block.

    Released on every exit path, including an exception in the holder -- a
    lock-holder failure must not wedge every later start.
    """
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    raise LockTimeout(
                        f"another process held {lock_path} for more than {timeout}s"
                    ) from exc
                time.sleep(_POLL_SECONDS)

        # Informational only. Never used to decide whether the lock is held --
        # that is the kernel's job, and a stale pid here means nothing.
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
        except OSError:
            pass

        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
