"""Manifest, readiness and boot-report models."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Readiness(str, Enum):
    """What a caller may assume about the snapshot right now."""

    #: No verified snapshot is open. Callers get a typed error, never empty data.
    UNREADY = "unready"
    #: A verified snapshot is open and matches the advertised release.
    READY = "ready"
    #: A verified snapshot is open, but a refresh failed. Serving is preferred to
    #: becoming unavailable; the staleness is reported, never hidden.
    READY_STALE = "ready_stale"


class SnapshotManifest(BaseModel):
    """The published description of one snapshot release.

    Frozen and strict: a manifest is evidence, and a field we silently dropped or
    later mutated would make the verification meaningless.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    snapshot_version: str = Field(min_length=1)
    bundle_object: str = Field(min_length=1)
    bundle_sha256: str
    bundle_bytes: int = Field(gt=0)
    parquet_files: int = Field(ge=0)
    rows: int = Field(ge=0)

    coverage_from: Optional[str] = None
    coverage_to: Optional[str] = None
    provisional_from: Optional[str] = None
    layout: Optional[str] = None
    duckdb_version: Optional[str] = None

    @field_validator("bundle_sha256")
    @classmethod
    def _digest_shape(cls, v: str) -> str:
        text = v.strip().lower()
        if not _SHA256.match(text):
            raise ValueError("bundle_sha256 must be 64 lowercase hex characters")
        return text

    @field_validator("bundle_object")
    @classmethod
    def _object_is_a_bare_name(cls, v: str) -> str:
        # The object name is joined onto a base location. A path segment or an
        # absolute name would let a manifest redirect the fetch elsewhere.
        if v.startswith("/") or ".." in v.split("/") or "\\" in v:
            raise ValueError("bundle_object must be a plain object name")
        return v


class BootReport(BaseModel):
    """What one boot attempt did. Frozen: a report is a record, not a scratchpad."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    readiness: Readiness = Readiness.UNREADY
    version: Optional[str] = None
    snapshot_dir: Optional[str] = None
    stale: bool = False
    activated: bool = False
    used_cache: bool = False
    bytes_downloaded: int = Field(0, ge=0)
    source_error: Optional[str] = None
    warnings: tuple[str, ...] = ()
    timings_ms: dict[str, float] = Field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.readiness in (Readiness.READY, Readiness.READY_STALE)
