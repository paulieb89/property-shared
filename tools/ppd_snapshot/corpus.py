"""The frozen shadow-corpus Definition, in one place, for both consumers.

`docs/design/ppd-shadow-corpus.md` is ACCEPTED AND FROZEN. Two tools execute it:

* `rehearse.py` -- the local rehearsal, snapshot arm only, no network;
* `stage1_shadow.py` -- the out-of-band production comparator, both arms.

**Both must execute the same corpus, or neither result means anything.** A
second copy of the case shapes, the frozen parameters, the warning-class
predicates or the `months` arithmetic is precisely the drift the freeze exists
to prevent: the two tools would diverge silently, and the rehearsal would stop
being a rehearsal *of* the Stage 1 run. So the Definition lives here and both
import it. Nothing in this module is artifact-specific, dated, or aggregate --
those belong to an Instance (Definition section 0).

This module makes no network call, opens no adapter and reads no environment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Optional

#: The page size every case is frozen at (Definition section 2, `limit`). A
#: result of exactly this length was truncated, and a truncated page cannot
#: answer a containment question.
LIMIT = 50

#: The Definition's placeholder geographies. Every one must be supplied by an
#: Instance; no others. `B5`, `B50` and `B5 4` are definitional and are not
#: placeholders -- see the `cases()` table.
REQUIRED_GEOGRAPHIES = frozenset({
    "S4_thin", "S5_dense", "S6_unit", "S7_type_weak",
    "S8_type_strong", "S11_provisional_empty", "S13_empty_unit",
})

#: Full-artifact counts that qualify the containment relations. A paged run
#: cannot re-derive these -- Definition section 9 says containment is
#: established during instance qualification, not from a page -- so they are
#: declared, and checked for consistency with what they claim to establish.
REQUIRED_BASELINES = frozenset({"S1_full", "S3_full", "S9_full"})

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^v\d{8}T\d{6}Z$")
#: Outward code, optional sector digit, optional unit. Deliberately narrow: a
#: placeholder that is not a real geography is a corpus error, not a query that
#: happens to return nothing.
GEOGRAPHY_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?( \d([A-Z]{2})?)?$")


class InstanceRefused(Exception):
    """The instance is malformed, incomplete, or bound to another artifact.

    Raised before anything is materialized or queried. Both CLIs map it to
    exit 2.
    """


# ---------------------------------------------------------------------------
# Case shapes -- the Definition's S1..S14
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Case:
    """One corpus shape, with the Definition's frozen parameters attached."""

    shape: str
    intent: str
    postcode: str
    search_level: str
    months: int = 24
    property_type: Optional[str] = None
    transaction_category: Optional[str] = "A"

    def request(self) -> dict[str, Any]:
        """The wire request, with omissions recorded as omissions.

        `property_type=None` and `address=None` are not values the HTTP surface
        can carry: omission is the only way to ask for the residential default.
        The record says so rather than implying a null was sent.
        """
        wire: dict[str, Any] = {
            "postcode": self.postcode,
            "search_level": self.search_level,
            "months": self.months,
            "limit": LIMIT,
            "transaction_category": self.transaction_category or "all",
            "filter_outliers": False,
            "auto_escalate": True,
            "enrich_epc": False,
        }
        if self.property_type is None:
            wire["property_type"] = "<omitted>"
        else:
            wire["property_type"] = self.property_type
        wire["address"] = "<omitted>"
        return wire

    def effective(self) -> dict[str, Any]:
        return {
            "property_type": (self.property_type
                              or "residential_default (F/D/S/T)"),
            "address": None,
            "transaction_category": self.transaction_category,
        }


def cases(geo: dict[str, str]) -> list[Case]:
    """The Definition's thirteen shapes, with placeholders resolved."""
    return [
        Case("S1", "contamination boundary", "B5", "district"),
        Case("S2", "reverse boundary", "B50", "district"),
        Case("S3", "sector isolation", "B5 4", "sector"),
        Case("S4", "thin market", geo["S4_thin"], "sector"),
        Case("S5", "dense market and truncation", geo["S5_dense"], "sector"),
        Case("S6", "exact-postcode geography", geo["S6_unit"], "postcode"),
        Case("S7", "type filter barely bites", geo["S7_type_weak"], "sector",
             property_type="F"),
        Case("S8", "type filter genuinely bites", geo["S8_type_strong"], "sector",
             property_type="F"),
        Case("S9", "category filtering", "B5 4", "sector",
             transaction_category=None),
        # S10 removed: "provisional tail, non-empty" discriminates nothing now
        # that every comps case is provisional (Definition section 3).
        Case("S11", "provisional flag is a window property",
             geo["S11_provisional_empty"], "sector", months=6),
        Case("S12", "widest window, deepest history", "B5", "district", months=120),
        Case("S13", "expected empty", geo["S13_empty_unit"], "postcode",
             property_type="D"),
        Case("S14", "expected empty, sector shape", "B5 4", "sector",
             property_type="T"),
    ]


def derived_from_date(observed_at: date, months: int) -> str:
    """The window a harness must reconstruct; `comps` does not report it.

    Mirrors `PPDService.comps`. Pinned behaviourally in
    `tests/snapshot/test_shadow_corpus_definition.py`, because if this drifts,
    every window recorded by every observation is wrong.
    """
    return (observed_at - timedelta(days=months * 30)).isoformat()


# ---------------------------------------------------------------------------
# Warning classes -- Definition section 5's executable predicates
# ---------------------------------------------------------------------------

def warning_classes(warnings: tuple[str, ...]) -> list[str]:
    """The Definition's classes, matched by their published predicates.

    Classes, never text: snapshot and live warnings are deliberately worded
    differently by source, so comparing strings would fail the corpus on a
    wording change and would encode prose as contract.
    """
    found = []
    for w in warnings:
        if "beyond snapshot coverage" in w and "are not included" in w:
            found.append("coverage_clamp")
        if "narrowed to" in w and "coverage" in w:
            found.append("coverage_floor_narrowing")
        if "days behind its coverage end" in w:
            found.append("freshness")
        if w.startswith("auto-escalation not applied:"):
            found.append("escalation_containment")
        if "the upstream window was not exhausted" in w:
            found.append("live_incompleteness")
        if "removed by geography containment" in w:
            found.append("geography_containment")
    return sorted(set(found))


# ---------------------------------------------------------------------------
# Geography and identity helpers
# ---------------------------------------------------------------------------

def outcodes(transactions: Iterable[Any]) -> list[str]:
    """Distinct outcodes in a result. Geography membership, never rows."""
    seen = set()
    for t in transactions:
        pc = (getattr(t, "postcode", None) or "").strip().upper()
        head = pc.partition(" ")[0]
        if head:
            seen.add(head)
    return sorted(seen)


def sectors(transactions: Iterable[Any]) -> list[str]:
    seen = set()
    for t in transactions:
        pc = (getattr(t, "postcode", None) or "").strip().upper()
        head, _, tail = pc.partition(" ")
        if head and tail:
            seen.add(f"{head} {tail[0]}")
    return sorted(seen)


def geography_violations(case: "Case", transactions: Iterable[Any]) -> dict[str, Any]:
    """Rows outside the geography a case asked for, **at the level it asked at**.

    Outcode equality is the right test for a `district` case and far too weak
    for the others. A `sector` case asking for `B5 4` and handed a `B5 6` row
    has been contaminated exactly as surely as a `B5` case handed a `B50` row --
    the Definition names sector isolation (`M3 7` returns only `M3 7`) as its
    own trap -- and an outcode-only check calls both of those clean. The same
    goes for a `postcode` case handed a different unit in the same sector.

    **Reported at sector and outcode granularity only**, which is the hygiene
    rule the local rehearsal already follows. A unit-level violation that stays
    inside the requested sector is therefore recorded as a count rather than by
    naming the postcode: the count is what proves contamination, and the unit
    would be the most identifying thing in the report.
    """
    requested = case.postcode.strip().upper()
    head, _, tail = requested.partition(" ")
    requested_sector = f"{head} {tail[0]}" if tail else None

    unexpected_outcodes: set[str] = set()
    unexpected_sectors: set[str] = set()
    same_sector_unit_violations = 0

    for transaction in transactions:
        pc = (getattr(transaction, "postcode", None) or "").strip().upper()
        if not pc:
            continue
        row_head, _, row_tail = pc.partition(" ")
        row_sector = f"{row_head} {row_tail[0]}" if row_tail else None

        if row_head != head:
            unexpected_outcodes.add(row_head)
            continue
        if case.search_level in {"sector", "postcode"} and requested_sector:
            if row_sector != requested_sector:
                # Same outcode, wrong sector -- invisible to an outcode check.
                unexpected_sectors.add(row_sector or row_head)
                continue
        if case.search_level == "postcode" and pc != requested:
            same_sector_unit_violations += 1

    return {
        "level": case.search_level,
        "unexpected_outcodes": sorted(unexpected_outcodes),
        "unexpected_sectors": sorted(unexpected_sectors),
        "same_sector_unit_violations": same_sector_unit_violations,
    }


def is_contaminated(violations: dict[str, Any]) -> bool:
    return bool(violations["unexpected_outcodes"]
                or violations["unexpected_sectors"]
                or violations["same_sector_unit_violations"])


def ids(transactions: Iterable[Any]) -> set[str]:
    """In-memory only. Used for containment and diffing; never persisted."""
    return {t.transaction_id for t in transactions
            if getattr(t, "transaction_id", None)}


# ---------------------------------------------------------------------------
# Instance validation shared by the rehearsal and the Stage 1 comparator
# ---------------------------------------------------------------------------

def validate_geographies(raw: Any) -> dict[str, str]:
    """Every placeholder supplied, no others, each a plausible geography."""
    if not isinstance(raw, dict):
        raise InstanceRefused("geographies must be a JSON object")
    supplied = set(raw)
    if missing := REQUIRED_GEOGRAPHIES - supplied:
        raise InstanceRefused(
            f"the Definition's placeholder(s) {sorted(missing)} are unsupplied")
    if unknown := supplied - REQUIRED_GEOGRAPHIES:
        raise InstanceRefused(
            f"geographies carries unknown placeholder(s): {sorted(unknown)}")
    cleaned: dict[str, str] = {}
    for key, value in sorted(raw.items()):
        if not isinstance(value, str) or not GEOGRAPHY_RE.match(
                value.strip().upper()):
            raise InstanceRefused(
                f"{key} is {value!r}, which is not a postcode, sector or outcode")
        cleaned[key] = value.strip().upper()
    return cleaned


def validate_baselines(raw: Any) -> dict[str, int]:
    """The three full-aggregate counts, and the relations they establish.

    A baseline set contradicting the relation it exists to establish is
    refused: it would look like evidence while qualifying nothing.
    """
    if not isinstance(raw, dict):
        raise InstanceRefused("aggregate_baselines must be a JSON object")
    supplied = set(raw)
    if missing := REQUIRED_BASELINES - supplied:
        raise InstanceRefused(
            f"aggregate_baselines is missing {sorted(missing)}; these are the "
            f"qualification evidence for the containment relations")
    if unknown := supplied - REQUIRED_BASELINES:
        raise InstanceRefused(
            f"aggregate_baselines carries unknown key(s): {sorted(unknown)}")
    for key in sorted(REQUIRED_BASELINES):
        value = raw[key]
        # `bool` is an `int` subclass; True would sail through an isinstance
        # check and then compare as 1.
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InstanceRefused(
                f"aggregate_baselines[{key}] is {value!r}, not a count")
    baselines = {k: int(v) for k, v in raw.items()}
    # The baselines exist to establish two relations. A set that contradicts
    # them qualifies nothing, and would be worse than absent: it would look
    # like evidence.
    #
    # STRICT on the S1/S3 side. Equal counts would say the sector IS the whole
    # district, which qualifies nothing -- the Definition (section 4) requires
    # a strict subset, so `>=` is the refusal and `>` would be a relaxation.
    if baselines["S3_full"] >= baselines["S1_full"]:
        raise InstanceRefused(
            f"aggregate_baselines say S3 holds {baselines['S3_full']} rows and "
            f"S1 holds {baselines['S1_full']}; S3 is one sector inside S1's "
            f"district, and the Definition requires a STRICT subset. Equal "
            f"counts would say the sector is the whole district, which "
            f"qualifies nothing.")
    if baselines["S9_full"] <= baselines["S3_full"]:
        raise InstanceRefused(
            f"aggregate_baselines say S9 ({baselines['S9_full']}) does not "
            f"exceed S3 ({baselines['S3_full']}); including category B cannot "
            f"return fewer rows than excluding it")
    return baselines


def validate_artifact_identity(version: Any, digest: Any) -> tuple[str, str]:
    """A version string and a full 64-character bundle digest, or a refusal."""
    if not isinstance(version, str) or not VERSION_RE.match(version):
        raise InstanceRefused(
            f"snapshot_version is not a version string: {version!r}")
    if not isinstance(digest, str) or not SHA256_RE.match(digest):
        raise InstanceRefused("bundle_sha256 is not a 64-character hex digest")
    return version, digest


# ---------------------------------------------------------------------------
# Per-case assertions -- Definition sections 3 and 9
# ---------------------------------------------------------------------------

def snapshot_invariants(case: Case, response: Any, provenance: Any,
                        classes: list[str]) -> dict[str, bool]:
    """The Definition's per-case assertions over a SNAPSHOT-arm response.

    Shared by the local rehearsal and the Stage 1 comparator so that the two
    check the same things. The universal block (section 3) is structural, not
    situational: `comps` never sends `to_date`, so routing takes the clamp
    branch unconditionally on every case, whatever the artifact, date or row
    count. A case reporting `sample_complete: true` is a defect, not a
    divergence.

    Booleans only -- no id, address or price is reachable from the result.
    """
    inv: dict[str, bool] = {
        # Universal (Definition section 3): comps never sends to_date.
        "coverage_clamp_warning_present": "coverage_clamp" in classes,
        "sample_complete_is_false": bool(
            provenance is not None and provenance.sample_complete is False),
        "completeness_basis_is_null": bool(
            provenance is not None and provenance.completeness_basis is None),
        "answered_by_snapshot": bool(
            provenance is not None and "snapshot" in str(provenance.source).lower()),
        # Universal, not per-shape: the resolved upper bound is always
        # `coverage_to` and `provisional_from` never exceeds it, so every comps
        # window intersects the provisional period (Definition section 3).
        "provisional_flagged": bool(
            provenance is not None and provenance.recent_period_provisional is True),
    }

    if case.search_level in {"district", "sector", "postcode"}:
        # Checked at the level the case asked at, not merely by outcode: a
        # sector case handed a same-outcode neighbouring sector is contaminated,
        # and an outcode-only test reports that as clean.
        inv["geography_isolation"] = not is_contaminated(
            geography_violations(case, response.transactions))

    if case.shape in {"S5", "S12"}:
        inv["truncated_at_limit"] = response.count == LIMIT
    if case.shape == "S4":
        inv["thin_market_flagged"] = response.thin_market is True
    if case.shape == "S11":
        inv["empty_result"] = response.count == 0
    if case.shape in {"S13", "S14"}:
        inv["expected_empty"] = response.count == 0
    return inv


def returned_date_bounds(transactions: Any) -> tuple[Optional[str], Optional[str]]:
    """The earliest and latest transfer date in a result. Bounds, never rows.

    Definition section 9 requires the date bounds of returned rows to be
    recorded: they are what shows a window was honoured, and two dates are not
    a transaction.
    """
    dates = sorted(t.date for t in transactions if getattr(t, "date", None))
    return (dates[0], dates[-1]) if dates else (None, None)
