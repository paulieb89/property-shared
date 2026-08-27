"""Provenance and transport-evidence models for PPD responses.

Additive: nothing here changes an existing response. These types describe *where
data came from* and *how much of it was examined*, so a consumer can tell an
honest empty result from a truncated one.

Two invariants are enforced here rather than left to callers, because both were
got wrong during design:

1. **Completeness is never inferred from counts.** ``sample_count <
   sample_limit`` proves nothing: the upstream window is bounded *before*
   client-side filtering runs, so a short list is equally consistent with "the
   window was truncated and most rows were discarded". ``sample_complete`` is
   therefore false by default and requires an explicit ``completeness_basis``.
2. **Exhaustion is tri-state and derived.** ``TransportEvidence.source_exhausted``
   is computed from the raw binding count and the fetch limit, and cannot be set
   by a caller. Unknown stays unknown: only ``True`` authorises escalation.

See docs/design/ppd-source-routing.md sections 2.7.3 and 3.1.1.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Stable pointer to the dataset metadata carrying the full HM Land Registry
#: attribution. Responses carry this reference, not licence prose.
ATTRIBUTION_REF = "/v1/meta#attribution"


class SourceKind(str, Enum):
    """Where the rows in a response came from."""

    SNAPSHOT = "snapshot"
    LINKED_DATA = "linked_data"
    SPARQL = "sparql"


class CompletenessBasis(str, Enum):
    """The *evidence* permitting ``sample_complete=True``.

    Modelled explicitly so completeness can never be claimed without saying how
    it was established.
    """

    #: Transport reported fewer raw bindings than the fetch limit.
    SOURCE_EXHAUSTED = "source_exhausted"
    #: Adapter asked for ``limit + 1`` and got fewer than ``limit + 1`` back.
    LIMIT_PLUS_ONE = "limit_plus_one"
    #: Adapter has a direct exhaustion signal of its own.
    EXPLICIT_ADAPTER_EXHAUSTION = "explicit_adapter_exhaustion"


class TransportEvidence(BaseModel):
    """Page-level evidence carried up from the transport layer.

    ``source_exhausted`` is a derived, tri-state property. It is deliberately NOT
    a field: allowing a caller to assert exhaustion would reintroduce exactly the
    unfounded-escalation bug this model exists to prevent.

    ``extra="forbid"`` so that passing ``source_exhausted=`` raises rather than
    being silently dropped -- a caller who believes they set it must be told they
    did not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_bindings_returned: Optional[int] = Field(
        None, ge=0, description="Rows the upstream returned BEFORE client-side filtering"
    )
    #: A fetch limit of 0 would make `raw < limit` unsatisfiable and so could only
    #: ever yield False; it is a caller error, not a legitimate page size.
    fetch_limit: Optional[int] = Field(
        None, gt=0, description="Limit sent upstream for this page (must be > 0)"
    )

    @property
    def source_exhausted(self) -> Optional[bool]:
        """``True`` / ``False`` / ``None`` (unknown).

        ``None`` when either input is absent. Unknown must never collapse to
        ``False``, because "we did not measure" is not "the window was full".
        """
        if self.raw_bindings_returned is None or self.fetch_limit is None:
            return None
        return self.raw_bindings_returned < self.fetch_limit

    def authorises_escalation(self) -> bool:
        """Only proven exhaustion may widen the search geography."""
        return self.source_exhausted is True


class PPDProvenance(BaseModel):
    """Additive provenance block attached to PPD-bearing responses.

    **Frozen: build this atomically, once, from gathered evidence.**

    ``extra="forbid"`` so a misspelled field is a loud error rather than a
    silently absent one -- provenance that quietly drops a field is worse than no
    provenance, because it still looks authoritative.

    ``frozen=True`` because the completeness invariant below is a *construction*
    check. Without it, ``p.sample_complete = True`` on an incomplete block
    silently produced the exact state this model exists to forbid, and it
    serialised that way.

    ``validate_assignment=True`` is deliberately NOT used: under Pydantic 2.12.5
    an after-validator can raise *during* assignment while the object keeps the
    invalid mutated value, which is worse than no check at all. Freezing rejects
    the write before it happens.

    The block is immutable **including its warnings**, which are held as a tuple
    rather than a list -- freezing is shallow, so a list would still permit
    ``p.warnings.append(...)`` to change what the block serialises.

    Consequence for callers: gather the counts, the completeness evidence and the
    warnings first, then construct one validated block. Never build a block and
    refine it by assignment. ``model_copy(update=...)`` is a Pydantic escape
    hatch that bypasses validation by design and must not be used to patch a
    block; the supported update path is fresh validated construction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceKind
    source_release: Optional[str] = None
    snapshot_imported_at: Optional[str] = None
    coverage_from: Optional[str] = None
    coverage_to: Optional[str] = None
    freshness_days: Optional[int] = Field(None, ge=0)
    recent_period_provisional: bool = False

    #: Tri-state. ``None`` means the existence probe did not complete — it must
    #: never be reported as ``False``, which would assert "nothing older exists".
    older_records_exist: Optional[bool] = None

    sample_count: int = Field(0, ge=0)
    sample_limit: int = Field(0, ge=0)
    sample_complete: bool = False
    completeness_basis: Optional[CompletenessBasis] = None

    attribution_ref: str = ATTRIBUTION_REF
    #: A tuple, not a list: ``frozen=True`` is shallow, so a list field would
    #: still allow ``p.warnings.append(...)`` to change what the block
    #: serialises. Pydantic accepts a list here and normalises it, and both
    #: model_dump(mode="json") and model_dump_json() emit a JSON array.
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _completeness_requires_evidence(self) -> "PPDProvenance":
        if self.sample_complete and self.completeness_basis is None:
            raise ValueError(
                "sample_complete=True requires a completeness_basis; counts alone "
                "never establish completeness"
            )
        return self
