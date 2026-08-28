"""Manifest, readiness and boot-report models."""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: A version becomes a directory name under the store. Restricting it to one
#: safe path component is what stops a manifest choosing where we write.
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

#: Names the store uses for its own bookkeeping; a version may not claim them.
_RESERVED_COMPONENTS = frozenset({"CURRENT", "staging", "snapshots"})


def validate_component(value: object, field: str, *, reserved: bool = True) -> str:
    """A single, safe path component -- or a ValueError.

    Shared by the manifest and every store entry point so all boundaries apply
    one rule, and none has to assume another already checked.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string; got {type(value).__name__}")
    text = value.strip()
    if not _SAFE_COMPONENT.match(text) or text in {".", ".."}:
        raise ValueError(
            f"{field} must be a single path component matching "
            f"[A-Za-z0-9][A-Za-z0-9._-]{{0,127}}; got {value!r}"
        )
    if reserved and text in _RESERVED_COMPONENTS:
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
        # The object name is joined onto a base location, so anything with
        # structure lets a manifest redirect the fetch. The contract is a bare
        # name; "a/b.tar" and "./x.tar" were previously accepted.
        return validate_component(v, "bundle_object", reserved=False)


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


class FrozenInventory(dict):
    """A dict that refuses in-place mutation.

    The inventory IS the verification evidence: it is what `is_verified` compares
    the directory against. `frozen=True` on the model only stops rebinding the
    attribute, so `record.inventory["a"] = 999` silently rewrote the evidence and
    changed the record's serialisation. Subclassing dict keeps the JSON shape and
    equality with plain dicts unchanged while closing every mutator.
    """

    __slots__ = ()

    def _immutable(self, *args, **kwargs):
        raise TypeError(
            "the verification inventory is immutable evidence; build a new "
            "VerificationRecord rather than editing one"
        )

    __setitem__ = _immutable
    __delitem__ = _immutable
    __ior__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable

    def __reduce__(self):
        return (self.__class__, (dict(self),))


class VerificationRecord(BaseModel):
    """What was verified about a materialized snapshot, and how.

    **Structural verification only.** The boot runtime proves that the bundle
    matched its published digest and length, that every archive member was safe,
    and that the unpacked file inventory is exactly what was written. It does
    NOT open the snapshot, run a query, or check any schema or row count --
    "materialized and structurally verified" is a weaker claim than "queryable",
    and conflating the two would let a well-formed but unusable snapshot be
    reported as ready. DuckDB, schema and row validation belong to the routing
    layer, before it serves anything from the snapshot.

    Strict and validated on the way IN and on the way OUT. Reading it back with
    ad-hoc `int(...)` calls let a malformed value raise out of the readiness
    check and escape boot entirely, which is the opposite of failing closed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    bundle_sha256: str
    bundle_bytes: int = Field(gt=0)
    parquet_files: int = Field(gt=0)
    rows: int = Field(ge=0)
    verified_at: str

    #: The validated coverage/provenance fields carried through from the
    #: manifest. Persisted so a later routing layer can answer coverage
    #: questions from the materialized snapshot alone, with no network call and
    #: no second fetch of a manifest that may since have rotated.
    coverage_from: Optional[str] = None
    coverage_to: Optional[str] = None
    provisional_from: Optional[str] = None
    layout: Optional[str] = None
    duckdb_version: Optional[str] = None
    #: Required: the manifest requires it, and this record claims to persist the
    #: validated value. Optional here would let a record claim provenance it
    #: does not carry.
    bundle_object: str

    #: Relative POSIX path -> exact byte size, for every file in the snapshot.
    #: Annotated as a plain mapping so pydantic can build a schema and
    #: serialise it unchanged; an after-validator swaps in the immutable
    #: representation once validation has finished.
    inventory: dict[str, int] = Field(min_length=1)

    #: What this layer verified. A Literal, not a free string: the boot runtime
    #: can only ever establish structural verification, and a record reading
    #: `verification="queryable"` would assert something no code here checked.
    verification: Literal["structural"] = "structural"

    @field_validator("version")
    @classmethod
    def _version_component(cls, v: str) -> str:
        return validate_component(v, "version")

    @field_validator("bundle_sha256")
    @classmethod
    def _digest_shape(cls, v: str) -> str:
        text = v.strip().lower()
        if not _SHA256.match(text):
            raise ValueError("bundle_sha256 must be 64 lowercase hex characters")
        return text

    @field_validator("bundle_object")
    @classmethod
    def _object_component(cls, v: str) -> str:
        return validate_component(v, "bundle_object", reserved=False)

    @field_validator("inventory", mode="before")
    @classmethod
    def _inventory_shape(cls, v: object) -> dict[str, int]:
        # mode="before" on purpose: pydantic's lax int coercion turns True into
        # 1 *before* an after-validator runs, so a bool size would have slipped
        # through a check written there.
        if not isinstance(v, dict):
            raise ValueError("inventory must be an object of path -> size")
        out: dict[str, int] = {}
        for key, size in v.items():
            if not isinstance(key, str) or not key:
                raise ValueError("inventory keys must be non-empty strings")
            if key.startswith("/") or ".." in key.split("/"):
                raise ValueError(f"inventory path is not relative: {key!r}")
            # bool is an int subclass; a True size is a malformed record.
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ValueError(f"inventory size for {key!r} must be a non-negative int")
            out[key] = size
        return out

    @field_validator("inventory", mode="after")
    @classmethod
    def _inventory_is_immutable(cls, v: dict[str, int]) -> "FrozenInventory":
        # Runs last, so the stored value is the frozen representation while the
        # declared schema stays a plain mapping.
        return FrozenInventory(v)
