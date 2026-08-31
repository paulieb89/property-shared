"""Object-source interface and implementations.

Deliberately a narrow protocol rather than the lab harness's direct urllib
calls: the runtime is testable offline against an in-memory source, and the
transport can change without touching verification or activation logic.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.parse
import urllib.request

from property_core.snapshot.errors import DownloadDeadlineExceeded
from contextlib import contextmanager
from typing import IO, Iterator, Optional, Protocol, runtime_checkable

#: Connect/read timeout, per the governing specification section 4.1.
#: The single socket timeout urllib actually supports.
#:
#: `urlopen(timeout=...)` takes ONE value covering connection setup and every
#: blocking socket operation. Advertising separate connect and read timeouts was
#: a fiction: passing a second value to the bundle request simply changed that
#: connection's timeout too, so `timeout=1, read_timeout=60` gave the bundle a
#: 60-second connect. One honest setting instead.
DEFAULT_TIMEOUT = 10.0
#: Small control objects only (current.json, the manifest). The bundle is
#: NEVER read through this path -- it is streamed.
MAX_CONTROL_BYTES = 1 * 1024 * 1024


@runtime_checkable
class ObjectSource(Protocol):
    """Where snapshot objects come from."""

    def read_bytes(self, name: str, *, max_bytes: Optional[int] = None) -> bytes:
        """Fetch a small control object whole."""

    def open_stream(self, name: str) -> IO[bytes]:
        """Open a readable, chunkable stream for a large object.

        The returned object is a context manager and may carry
        ``declared_length`` when the transport knows it.
        """


def _is_timeout(exc: BaseException) -> bool:
    """Whether this failure is a timeout, however urllib chose to spell it.

    `socket.timeout` is an alias of `TimeoutError` on modern Python, but a
    connect-phase timeout arrives wrapped in `URLError`, so the reason has to be
    unwrapped. `HTTPError` is deliberately excluded: it subclasses `URLError`,
    and a 504 from the server is its answer, not our deadline.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return False
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, (TimeoutError, socket.timeout))
    return False


@contextmanager
def _timeouts_typed(what: str, seconds: float) -> Iterator[None]:
    """Translate timeout failures into the exported typed failure.

    Applied at EVERY seam where a socket operation can time out -- opening a
    control response, reading a control body, and opening the bundle response --
    not only once the bundle stream exists. Unrelated OSError and URLError pass
    through untouched; losing a connection-refused behind a deadline error would
    be its own misdiagnosis.
    """
    try:
        yield
    except Exception as exc:
        if _is_timeout(exc):
            raise DownloadDeadlineExceeded(
                f"{what} timed out after {seconds}s"
            ) from exc
        raise


class _HttpStream:
    """A response wrapper exposing the declared length alongside read()."""

    def __init__(self, response, *, socket_timeout: float):
        self._response = response
        self._socket_timeout = socket_timeout
        length = response.headers.get("Content-Length")
        self.declared_length = int(length) if length and length.isdigit() else None

    def read(self, size: int) -> bytes:
        """One bounded read.

        Uses `read1` where available: `HTTPResponse.read(n)` loops internally
        until it has n bytes, so a dribbling server can keep a single call
        active indefinitely and the caller's total-budget check never runs.
        `read1` returns after one underlying socket read, which the socket
        timeout bounds -- so the budget is evaluated at a real interval.

        A socket timeout is translated into the typed failure here, at the seam
        where it is raised, so callers handle one taxonomy rather than a bare
        builtins.TimeoutError.
        """
        reader = getattr(self._response, "read1", None)
        with _timeouts_typed("bundle read", self._socket_timeout):
            return reader(size) if reader is not None else self._response.read(size)

    def __enter__(self) -> "_HttpStream":
        return self

    def __exit__(self, *exc) -> bool:
        self._response.close()
        return False


class HttpObjectSource:
    """Read-only HTTP object source rooted at a base URL."""

    def __init__(self, base_url: str, *,
                 socket_timeout: float = DEFAULT_TIMEOUT,
                 user_agent: str = "property-shared-snapshot/1"):
        self.base_url = base_url.rstrip("/")
        #: One value, used for both control and bundle requests, because that is
        #: all urllib enforces. It bounds connection setup and every blocking
        #: socket operation -- and so is the only real interrupt in this design.
        self.socket_timeout = socket_timeout
        self.user_agent = user_agent

    def _url(self, name: str) -> str:
        # `name` comes from a manifest, which validates it is a bare object
        # name; quoting keeps a surprising character from altering the path.
        return f"{self.base_url}/{urllib.parse.quote(name)}"

    def _request(self, name: str):
        return urllib.request.Request(self._url(name),
                                      headers={"User-Agent": self.user_agent})

    def _open(self, name: str):
        return urllib.request.urlopen(self._request(name), timeout=self.socket_timeout)

    def read_bytes(self, name: str, *, max_bytes: Optional[int] = None) -> bytes:
        cap = MAX_CONTROL_BYTES if max_bytes is None else max_bytes
        # Two separate seams: waiting for the response, then reading its body.
        # A stalled body times out in the second even though the first succeeded.
        with _timeouts_typed(f"request for {name!r}", self.socket_timeout):
            resp = self._open(name)
        with resp:
            with _timeouts_typed(f"read of {name!r}", self.socket_timeout):
                # Read one byte past the cap so an oversized control object is an
                # error rather than a silent truncation.
                body = resp.read(cap + 1)
        if len(body) > cap:
            raise ValueError(f"control object {name!r} exceeds {cap} bytes")
        return body

    def open_stream(self, name: str) -> _HttpStream:
        # The socket timeout bounds connection setup and every read on this
        # stream. A server that never sends headers times out HERE, before any
        # stream exists, so the translation cannot live only in _HttpStream.read.
        with _timeouts_typed(f"request for {name!r}", self.socket_timeout):
            resp = self._open(name)
        return _HttpStream(resp, socket_timeout=self.socket_timeout)


class LocalDirectorySource:
    """Objects from a local directory. For offline development and tests."""

    def __init__(self, root):
        from pathlib import Path

        self.root = Path(root)

    def _path(self, name: str):
        candidate = (self.root / name).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"object name escapes the source root: {name!r}")
        return candidate

    def read_bytes(self, name: str, *, max_bytes: Optional[int] = None) -> bytes:
        cap = MAX_CONTROL_BYTES if max_bytes is None else max_bytes
        with open(self._path(name), "rb") as fh:
            body = fh.read(cap + 1)
        if len(body) > cap:
            raise ValueError(f"control object {name!r} exceeds {cap} bytes")
        return body

    def open_stream(self, name: str):
        path = self._path(name)

        class _FileStream:
            declared_length = path.stat().st_size

            def __init__(self):
                self._fh = open(path, "rb")

            def read(self, size: int) -> bytes:
                return self._fh.read(size)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self._fh.close()
                return False

        return _FileStream()
