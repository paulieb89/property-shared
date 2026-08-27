"""Object-source interface and implementations.

Deliberately a narrow protocol rather than the lab harness's direct urllib
calls: the runtime is testable offline against an in-memory source, and the
transport can change without touching verification or activation logic.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from typing import IO, Optional, Protocol, runtime_checkable

DEFAULT_TIMEOUT = 30.0
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


class _HttpStream:
    """A response wrapper exposing the declared length alongside read()."""

    def __init__(self, response):
        self._response = response
        length = response.headers.get("Content-Length")
        self.declared_length = int(length) if length and length.isdigit() else None

    def read(self, size: int) -> bytes:
        return self._response.read(size)

    def __enter__(self) -> "_HttpStream":
        return self

    def __exit__(self, *exc) -> bool:
        self._response.close()
        return False


class HttpObjectSource:
    """Read-only HTTP object source rooted at a base URL."""

    def __init__(self, base_url: str, *, timeout: float = DEFAULT_TIMEOUT,
                 user_agent: str = "property-shared-snapshot/1"):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent

    def _url(self, name: str) -> str:
        # `name` comes from a manifest, which validates it is a bare object
        # name; quoting keeps a surprising character from altering the path.
        return f"{self.base_url}/{urllib.parse.quote(name)}"

    def _request(self, name: str):
        return urllib.request.Request(self._url(name),
                                      headers={"User-Agent": self.user_agent})

    def read_bytes(self, name: str, *, max_bytes: Optional[int] = None) -> bytes:
        cap = MAX_CONTROL_BYTES if max_bytes is None else max_bytes
        with urllib.request.urlopen(self._request(name), timeout=self.timeout) as resp:
            # Read one byte past the cap so an oversized control object is an
            # error rather than a silent truncation.
            body = resp.read(cap + 1)
        if len(body) > cap:
            raise ValueError(f"control object {name!r} exceeds {cap} bytes")
        return body

    def open_stream(self, name: str) -> _HttpStream:
        resp = urllib.request.urlopen(self._request(name), timeout=self.timeout)
        return _HttpStream(resp)


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
