"""Manifest, readiness and boot-report models."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: A version becomes a directory name under the store. Restricting it to one
#: safe path component is what stops a manifest choosing where we write.
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

#: Names the store uses for its own bookkeeping; a version may not claim them.
_RESERVED_COMPONENTS = frozenset({"CURRENT", "staging", "snapshots"})


def validate_component(value: str, field: str) -> str:
    """A single, safe path component -- or a ValueError.

    Shared by the manifest and the store so both boundaries apply the same rule,
    and neither has to assume the other already checked.
    """
    text = (value or "").strip()
    if not _SAFE_COMPONENT.match(text) or text in {".", ".."}:
        raise ValueError(
            f"{field} must be a single path component matching "
            f"[A-Za-z0-9][A-Za-z0-9._-]{{0,127}}; got {value!r}"
        )
    if text in _RESERVED_COMPONENTS:
        raise ValueError(f"{field} {text!r} is reserved by the snapshot store")
    return text


class Readiness(str, Enum):
    """What a caller may assume about the snapshot right now.

    Two states only. There is deliberately no "serving a stale cache" state:
    the snapshot is materialized into an ephemeral filesystem that does not
    survive a restart or deploy, so a cached snapshot is not a dependable
    fallback. When no snapshot is materialized the caller uses the live source.
    """

    #: No snapshot is materialized. Callers get a typed error and fall back to
    #: the live source -- never empty data.
    UNREADY = "unready"
    #: A verified snapshot is materialized and open on this Machine.
    READY = "ready"


class SnapshotManifest(BaseModel):
    """The published description of one snapshot release.

    Frozen and strict: a manifest is evidence, and a field we silently dropped or
    later mutated would make the verification meaningless.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_version: str = Field(min_length=1)
    bundle_object: str = Field(min_length=1)
    bundle_sha256: str
    bundle_bytes: int = Field(gt=0)
    #: A snapshot with no parquet files is not a snapshot. Rejected here so an
    #: exact 0 == 0 inventory match cannot wave an empty archive through.
    parquet_files: int = Field(gt=0)
    rows: int = Field(ge=0)

    coverage_from: Optional[str] = None
    coverage_to: Optional[str] = None
    provisional_from: Optional[str] = None
    layout: Optional[str] = None
    duckdb_version: Optional[str] = None

    @field_validator("snapshot_version")
    @classmethod
    def _version_is_a_safe_component(cls, v: str) -> str:
        # This value becomes a directory name. Without this, "../../x" in a
        # published manifest chooses a path outside the store.
        return validate_component(v, "snapshot_version")

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
    #: True when this boot produced no snapshot and the caller must use the live
    #: source. The explicit contract, rather than something inferred from a null.
    fallback_to_live: bool = True
    #: True when the advertised release could not be fetched but a snapshot
    #: materialized earlier in THIS Machine's lifetime was adopted. Not a
    #: durability guarantee -- see property_core.snapshot.store.
    behind_advertised_release: bool = False
    activated: bool = False
    #: Reused a materialization already present on this Machine, typically
    #: produced by another worker in the same boot.
    reused_existing: bool = False
    bytes_downloaded: int = Field(0, ge=0)
    source_error: Optional[str] = None
    warnings: tuple[str, ...] = ()
    timings_ms: dict[str, float] = Field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.readiness is Readiness.READY
