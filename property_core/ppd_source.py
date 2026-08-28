"""Source routing: which source answers, over what window, and what we say so.

Three jobs, all of them about the difference between a fact and an absence.

**Coverage.** A request whose range starts before `coverage_from` is
unsatisfiable as stated. Two policies decide what that means:

* ``GUARANTEED`` -- the surface bounds `months` (comps at 60/120, yield, report)
  and the snapshot is sized to cover the maximum. A window reaching past coverage
  therefore means a *stale snapshot*, not an impossible request, so it is
  narrowed to `coverage_from` and warned.
* ``EXPLICIT`` -- the caller named dates, or `months` has no upper bound
  (`/v1/ppd/transactions`, `/v1/ppd/blocks`). Refused with `PPDCoverageError`
  carrying both ranges as structured fields. Never a partial 200: a truncated
  result is indistinguishable from a complete one.

**Fallback.** Every `SnapshotFailure` hands off to the live source and says so
in a warning. A `PPDCoverageError` and an `InvalidPostcodeError` do not: the
first is the answer, the second is the caller's mistake, and routing either to
live would hide exactly the fact the caller needs.

**Provenance.** One validated block, built once from already-gathered evidence.
`PPDProvenance` is frozen precisely so it cannot be built early and refined by
assignment, and `model_copy(update=...)` -- which bypasses validation by design
-- is prohibited here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Iterable, Optional

from property_core.config import ppd_snapshot_enabled
from property_core.exceptions import PPDCoverageError
from property_core.provenance import (
    CompletenessBasis,
    PPDProvenance,
    SourceKind,
    TransportEvidence,
)

#: Freshness beyond which a response says so. Staleness is a warning, never an
#: outage: a stale verified snapshot always beats going unready (spec 4.9).
FRESHNESS_WARNING_DAYS = 45


class CoveragePolicy(str, Enum):
    """How a surface reacts to a window reaching past `coverage_from`."""

    #: Bounded `months`; narrow and warn.
    GUARANTEED = "guaranteed"
    #: Caller-supplied or unbounded dates; refuse, typed, with both ranges.
    EXPLICIT = "explicit"


@dataclass(frozen=True)
class CoverageDecision:
    """The window actually queried, and what had to be said about it."""

    from_date: Optional[str]
    to_date: Optional[str]
    warnings: tuple[str, ...]
    #: The caller gave no `from_date`, so the lower bound became `coverage_from`.
    #: Kept separate from `to_clamped` because only this one licenses the
    #: existence probe: the probe asks whether records exist BEFORE coverage,
    #: which is a question only a caller who did not choose the lower bound is
    #: asking. Conflating the two fired a probe -- an upstream request -- on
    #: every request that merely ran up to the present.
    from_narrowed: bool
    #: The requested window reached past `coverage_to` and was clamped to it.
    to_clamped: bool
    recent_period_provisional: bool
    #: Whether the caller's ENTIRE requested interval lies inside coverage.
    #: `sample_complete` may only be true when this is -- see
    #: `snapshot_provenance`. An interval that reaches past either bound was
    #: only partly answered, however exhaustively the overlap was searched.
    fully_contained: bool = False

    @property
    def narrowed(self) -> bool:
        """Whether the queried window differs from the requested one, either end."""
        return self.from_narrowed or self.to_clamped


def active_adapter() -> Optional[Any]:
    """The process's snapshot adapter, or `None` for the live source.

    The flag is checked BEFORE the import, so with the feature off a request
    path never so much as imports `property_core.snapshot` -- let alone DuckDB.
    The same check is repeated inside `state.active_adapter()`; that redundancy
    is deliberate, because either call site alone must fail closed.
    """
    if not ppd_snapshot_enabled():
        return None
    from property_core.snapshot import state

    return state.active_adapter()


def _today() -> date:
    return date.today()


def freshness_days(coverage_to: Optional[str]) -> Optional[int]:
    if not coverage_to:
        return None
    try:
        # Never negative: a coverage_to in the future would otherwise report a
        # negative age, which the model rejects and which means nothing anyway.
        return max(0, (_today() - date.fromisoformat(coverage_to)).days)
    except ValueError:
        return None


def resolve_coverage(
    adapter: Any,
    *,
    from_date: Optional[str],
    to_date: Optional[str],
    policy: CoveragePolicy,
) -> CoverageDecision:
    """Decide the queried window over the COMPLETE interval, or refuse.

    Both bounds are checked. Testing only the lower one let a request for a
    period entirely *after* `coverage_to` -- next month, say -- run against the
    snapshot, match nothing, and come back as an empty result marked complete:
    a confident statement that no such sales exist, made by a source that could
    not have known.

    Four cases, in order:

    1. **Disjoint** -- the interval and coverage do not overlap at all. Under
       EXPLICIT this is a typed refusal naming the boundary that was crossed;
       under GUARANTEED it is a `SnapshotCoverageGapError`, so the live source
       answers. The difference is who chose the dates: an EXPLICIT caller can
       act on a refusal, while a GUARANTEED caller never named a window and
       would just be blamed for a stale snapshot.
    2. **Starts before coverage** -- refuse (EXPLICIT) or narrow and warn
       (GUARANTEED, whose `months` is bounded and whose snapshot is sized for
       the maximum).
    3. **No `from_date`** -- narrow to `coverage_from` and warn. Silently
       turning "all time" into eleven years is the lie this exists to prevent.
    4. **Extends past `coverage_to`** (including every request with no
       `to_date`, since that means "up to now") -- clamp to `coverage_to`, warn
       naming what was excluded, and record that the interval was NOT fully
       contained, which forbids any completeness claim.

    Raises `PPDCoverageError` or `SnapshotCoverageGapError`.
    """
    from property_core.snapshot.errors import SnapshotCoverageGapError

    coverage_from = adapter.coverage_from
    coverage_to = adapter.coverage_to
    warnings: list[str] = []
    from_narrowed = False
    to_clamped = False
    resolved_from = from_date
    resolved_to = to_date

    # The adapter's metadata gate guarantees both bounds are present, ordered
    # ISO dates before it will route, so there is no "unknown coverage" branch
    # here. If that gate is ever loosened, this falls back to serving the window
    # verbatim rather than inventing bounds.
    if coverage_from and coverage_to:
        starts_after_coverage = from_date is not None and from_date > coverage_to
        ends_before_coverage = to_date is not None and to_date < coverage_from

        if starts_after_coverage or ends_before_coverage:
            side = "follows" if starts_after_coverage else "precedes"
            if policy is CoveragePolicy.EXPLICIT:
                raise PPDCoverageError(
                    coverage_from=coverage_from,
                    coverage_to=coverage_to,
                    requested_from=from_date,
                    requested_to=to_date,
                    source_release=adapter.version,
                    detail=f"requested range {side} available coverage entirely",
                    remedy=(
                        f"request a range within {coverage_from}..{coverage_to}; "
                        f"sales after {coverage_to} are not yet in this release"
                        if starts_after_coverage else
                        f"request a range within {coverage_from}..{coverage_to}, "
                        f"or look up a known transaction by its id"
                    ),
                )
            raise SnapshotCoverageGapError(
                f"snapshot coverage {coverage_from}..{coverage_to} does not "
                f"overlap the requested window {from_date}..{to_date}"
            )

        if from_date is None:
            resolved_from = coverage_from
            from_narrowed = True
            warnings.append(
                f"unbounded from_date narrowed to snapshot coverage "
                f"{coverage_from}")
        elif from_date < coverage_from:
            if policy is CoveragePolicy.EXPLICIT:
                raise PPDCoverageError(
                    coverage_from=coverage_from,
                    coverage_to=coverage_to,
                    requested_from=from_date,
                    requested_to=to_date,
                    source_release=adapter.version,
                )
            resolved_from = coverage_from
            from_narrowed = True
            warnings.append(
                f"requested window starts {from_date}, before snapshot coverage; "
                f"narrowed to {coverage_from}")

        if to_date is None or to_date > coverage_to:
            resolved_to = coverage_to
            to_clamped = True
            warnings.append(
                f"requested window extends to "
                f"{to_date or 'the present'}, beyond snapshot coverage "
                f"{coverage_to}; sales after {coverage_to} are not included")

        age = freshness_days(coverage_to)
        if age is not None and age > FRESHNESS_WARNING_DAYS:
            warnings.append(
                f"snapshot is {age} days behind its coverage end {coverage_to}; "
                f"recent sales may be missing")

    fully_contained = bool(
        coverage_from and coverage_to
        and from_date is not None and from_date >= coverage_from
        and to_date is not None and to_date <= coverage_to
    )

    provisional = _intersects_provisional(
        adapter, from_date=resolved_from, to_date=resolved_to)
    if provisional:
        warnings.append(
            f"the window overlaps the provisional period from "
            f"{adapter.provisional_from}; HM Land Registry revises recent "
            f"months, so those figures may change")

    return CoverageDecision(
        from_date=resolved_from,
        to_date=resolved_to,
        warnings=tuple(warnings),
        from_narrowed=from_narrowed,
        to_clamped=to_clamped,
        recent_period_provisional=provisional,
        fully_contained=fully_contained,
    )


def _intersects_provisional(adapter: Any, *, from_date: Optional[str],
                            to_date: Optional[str]) -> bool:
    """Whether the queried window touches `[provisional_from, coverage_to]`.

    `provisional_from` is *published in the manifest*, never inferred at query
    time: how far back HMLR's incremental publication is still moving is a
    property of the release, not something a query can work out.
    """
    provisional_from = adapter.provisional_from
    coverage_to = adapter.coverage_to
    if not provisional_from or not coverage_to:
        return False
    window_end = to_date or coverage_to
    window_start = from_date or adapter.coverage_from or provisional_from
    return not (window_end < provisional_from or window_start > coverage_to)


def snapshot_provenance(
    adapter: Any,
    *,
    decision: CoverageDecision,
    sample_count: int,
    sample_limit: int,
    completeness_basis: Optional[CompletenessBasis],
    offset: int = 0,
    older_records_exist: Optional[bool] = None,
    warnings: Iterable[str] = (),
) -> PPDProvenance:
    """One validated block, built once from evidence already gathered.

    `sample_complete` is derived from `completeness_basis` rather than passed
    alongside it, so the pair cannot disagree: a basis means complete, no basis
    means not complete, and there is no third spelling.

    **Two things withdraw the basis here, centrally, so no call site can forget
    them.** The adapter's `limit + 1` evidence is a fact about the page it
    fetched, and a page is not the sample when either holds:

    * the requested interval was not fully inside coverage -- part of what was
      asked for was never searched, so exhausting the rest proves nothing about
      it;
    * `offset > 0` -- a short final page says the page ended, not that the pages
      skipped over were seen.
    """
    basis = completeness_basis
    if basis is not None and (not decision.fully_contained or offset > 0):
        basis = None
    completeness_basis = basis
    return PPDProvenance(
        source=SourceKind.SNAPSHOT,
        source_release=adapter.version,
        snapshot_imported_at=adapter.imported_at,
        coverage_from=adapter.coverage_from,
        coverage_to=adapter.coverage_to,
        freshness_days=freshness_days(adapter.coverage_to),
        recent_period_provisional=decision.recent_period_provisional,
        older_records_exist=older_records_exist,
        sample_count=sample_count,
        sample_limit=sample_limit,
        sample_complete=completeness_basis is not None,
        completeness_basis=completeness_basis,
        warnings=tuple(warnings),
    )


def live_provenance(
    *,
    source: SourceKind = SourceKind.SPARQL,
    evidence: Optional[TransportEvidence] = None,
    sample_count: int = 0,
    sample_limit: int = 0,
    warnings: Iterable[str] = (),
) -> PPDProvenance:
    """Provenance for a live answer. Completeness stays false unless proven.

    The live path may only claim completeness through `SOURCE_EXHAUSTED`, and
    only when the transport actually observed it. Counts alone establish
    nothing: the upstream window is bounded *before* client-side filtering, so a
    short list is equally consistent with "the window was truncated and most
    rows were discarded".

    Snapshot fields are null, not zero or empty -- a live answer has no coverage
    bounds to state.
    """
    exhausted = evidence.source_exhausted if evidence is not None else None
    basis = CompletenessBasis.SOURCE_EXHAUSTED if exhausted is True else None
    return PPDProvenance(
        source=source,
        sample_count=sample_count,
        sample_limit=sample_limit,
        sample_complete=basis is not None,
        completeness_basis=basis,
        warnings=tuple(warnings),
    )


def fallback_warning(exc: Exception) -> str:
    """The one sentence a caller needs when the snapshot stepped aside."""
    return (f"snapshot source unavailable ({type(exc).__name__}: "
            f"{str(exc)[:160]}); answered from the live source instead")
