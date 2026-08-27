"""Tiny synthetic archive builders. Nothing large or real is ever committed."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path



def build_tar(members: list[tarfile.TarInfo], payload: bytes = b"x" * 64,
              *, compress: str = "") -> bytes:
    """A tar (optionally compressed) built from raw TarInfo objects."""
    buf = io.BytesIO()
    mode = f"w:{compress}" if compress else "w"
    with tarfile.open(fileobj=buf, mode=mode) as tar:
        for ti in members:
            if ti.isreg():
                tar.addfile(ti, io.BytesIO(payload[: ti.size] if ti.size else b""))
            else:
                tar.addfile(ti)
    return buf.getvalue()


def reg(name: str, size: int = 8) -> tarfile.TarInfo:
    ti = tarfile.TarInfo(name); ti.size = size; ti.type = tarfile.REGTYPE
    return ti


def directory(name: str) -> tarfile.TarInfo:
    ti = tarfile.TarInfo(name); ti.type = tarfile.DIRTYPE
    return ti


def sym(name: str, target: str) -> tarfile.TarInfo:
    ti = tarfile.TarInfo(name); ti.type = tarfile.SYMTYPE
    ti.linkname = target; ti.size = 0
    return ti


def hard(name: str, target: str) -> tarfile.TarInfo:
    ti = tarfile.TarInfo(name); ti.type = tarfile.LNKTYPE
    ti.linkname = target; ti.size = 0
    return ti


def dev(name: str, kind: str = "chr") -> tarfile.TarInfo:
    ti = tarfile.TarInfo(name); ti.size = 0
    ti.type = {"chr": tarfile.CHRTYPE, "blk": tarfile.BLKTYPE,
               "fifo": tarfile.FIFOTYPE}[kind]
    ti.devmajor, ti.devminor = 1, 3
    return ti


def good_bundle_bytes() -> bytes:
    """A minimal well-formed snapshot bundle: a manifest and one data file."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        body = json.dumps({"rows": 3}).encode()
        ti = tarfile.TarInfo("manifest.json"); ti.size = len(body)
        tar.addfile(ti, io.BytesIO(body))
        tar.addfile(directory("year=2026"))
        data = b"PAR1tiny"
        ti = tarfile.TarInfo("year=2026/data.parquet"); ti.size = len(data)
        tar.addfile(ti, io.BytesIO(data))
    return buf.getvalue()
