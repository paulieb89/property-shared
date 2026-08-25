"""Safe candidate selection.

"One search plus one certificate" is only true once a unique candidate exists.
The audit measured the legacy matcher accepting a different house on the same
street (score 36 against a threshold of 30), tying every flat in a block at 62
because the flat number is stripped before comparison, and tie-breaking to
whichever row the upstream happened to return first.

So selection here refuses rather than guesses. Ambiguity is a returned outcome,
never an arbitrary certificate fetch.

Order:
  1. exact UPRN, when the caller supplies one and exactly one row matches
  2. otherwise structured address evidence requiring an unambiguous winner
  3. otherwise EPCAmbiguousMatchError
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from property_core.epc.errors import EPCAmbiguousMatchError
from property_core.epc.source_models import EPCSearchRow

_UNIT_RE = re.compile(r"\b(?:flat|apartment|apt|unit)\s*([0-9a-z]+)\b", re.I)
_NUM_RE = re.compile(r"\b(\d+[a-z]?)\b", re.I)
_WORD_RE = re.compile(r"[a-z0-9]+", re.I)


def _norm(s: Optional[str]) -> str:
    return " ".join(_WORD_RE.findall((s or "").lower()))


def _unit(s: Optional[str]) -> Optional[str]:
    m = _UNIT_RE.search(s or "")
    return m.group(1).lower() if m else None


def _building(s: Optional[str]) -> Optional[str]:
    """The building/house number, parsed INDEPENDENTLY of any unit number.

    Comparing a flat set of all numbers lets a shared unit mask a conflicting
    building: "Flat 2, 24 Alexandra Road" and "Flat 2, 99 Alexandra Road" both
    contain "2", and an intersection test selected the wrong building. The unit
    clause is removed first so what remains is the building identifier.
    """
    text = _UNIT_RE.sub(" ", s or "")
    found = _NUM_RE.findall(text)
    return found[0].lower() if found else None


def _street_words(s: Optional[str]) -> set[str]:
    """Alphabetic tokens only — the street signal, with numbers removed.

    Note this is a SET, and agreement requires equality, not intersection:
    "High Street" and "High Road" share the token "high" while naming different
    streets. Abbreviations ("Rd" vs "Road") are deliberately NOT expanded —
    inferring an equivalence is the kind of guess this module exists to refuse.
    """
    dropped = {"flat", "apartment", "apt", "unit"}
    return {
        w for w in _norm(s).split()
        if not w.isdigit() and not w[:1].isdigit() and w not in dropped
    }


@dataclass(frozen=True)
class SelectionResult:
    """The selected row plus how it was identified.

    `confidence` is not a fuzzy score. 100 is reserved for identity evidence
    (a UPRN match or an exact address match); a street+number+unit agreement is
    strong but weaker than identity, and says so.
    """

    row: EPCSearchRow
    method: str          # "uprn" | "exact_address" | "street_number_unit"
    confidence: int      # 100 identity, 80 structured agreement


def select_candidate(
    rows: Iterable[EPCSearchRow],
    *,
    uprn: Optional[str] = None,
    address: Optional[str] = None,
) -> SelectionResult:
    """Return exactly one row with its selection evidence, or raise."""
    rows = [r for r in rows if r.usable]
    if not rows:
        raise EPCAmbiguousMatchError("no usable candidate rows", [])

    if uprn:
        hits = [r for r in rows if r.uprn and r.uprn == str(uprn)]
        if len(hits) == 1:
            return SelectionResult(hits[0], "uprn", 100)
        if len(hits) > 1:
            raise EPCAmbiguousMatchError(
                f"{len(hits)} certificates share UPRN {uprn}; cannot select one", hits)
        # A supplied UPRN that matches nothing is evidence of a MISS, not an
        # invitation to guess from weaker address text.
        raise EPCAmbiguousMatchError(
            f"UPRN {uprn} matched no candidate at this postcode; refusing to fall back "
            "to address matching, which could select a different property", rows)

    if not address:
        # Being the only row is not evidence that it is the right property. With
        # no address and no UPRN there is nothing to match against, so refuse
        # regardless of how few candidates came back.
        raise EPCAmbiguousMatchError(
            f"{len(rows)} candidate(s) but no address or UPRN supplied; there is no "
            "evidence to identify a specific property", rows)

    target_norm = _norm(address)
    target_unit = _unit(address)
    target_street = _street_words(address)

    exact = [r for r in rows if _norm(r.address) == target_norm]
    if len(exact) == 1:
        return SelectionResult(exact[0], "exact_address", 100)
    if len(exact) > 1:
        raise EPCAmbiguousMatchError(
            f"{len(exact)} certificates share the same address text", exact)

    # Street must agree EXACTLY before a number can mean anything. A shared
    # token is not agreement: "12 High Street" and "12 High Road" overlap on
    # "high" while naming different streets, and an intersection test selected
    # the wrong property.
    if not target_street:
        raise EPCAmbiguousMatchError(
            f"{address!r} contains no street name to match on", rows)
    same_street = [r for r in rows if _street_words(r.address) == target_street]
    if not same_street:
        raise EPCAmbiguousMatchError(
            f"no candidate's street matches {address!r} exactly; candidate streets are "
            f"{sorted(' '.join(sorted(_street_words(r.address))) for r in rows)[:5]}", rows)

    # Building number is compared on its own, never as part of a pooled set of
    # all numbers: a matching unit must not compensate for a mismatched
    # building ("Flat 2, 24 …" vs "Flat 2, 99 …" share the "2").
    target_building = _building(address)
    if target_building is not None:
        same_number = [r for r in same_street if _building(r.address) == target_building]
        if not same_number:
            raise EPCAmbiguousMatchError(
                f"no candidate on that street has building number {target_building!r}; "
                f"candidates are "
                f"{sorted(b for b in {_building(r.address) for r in same_street} if b)[:5]}",
                same_street)
    else:
        # The query names no building number. Any candidate that does is a
        # different, more specific address.
        same_number = [r for r in same_street if _building(r.address) is None]
        if not same_number:
            raise EPCAmbiguousMatchError(
                f"{address!r} names no building number but every candidate does", same_street)

    # Unit agreement is enforced even when only ONE candidate remains. A lone
    # "Flat 3" is not evidence for a "Flat 2" query — narrowing to one row says
    # nothing about whether that row is the right property.
    candidate_units = {_unit(r.address) for r in same_number}
    if target_unit is not None:
        unit_hits = [r for r in same_number if _unit(r.address) == target_unit]
        if len(unit_hits) == 1:
            return SelectionResult(unit_hits[0], "street_number_unit", 80)
        if not unit_hits:
            raise EPCAmbiguousMatchError(
                f"no candidate matches unit {target_unit!r} from {address!r}; the "
                f"available units are {sorted(u for u in candidate_units if u)}",
                same_number)
        raise EPCAmbiguousMatchError(
            f"{len(unit_hits)} candidates share unit {target_unit!r}", unit_hits)

    # Target names no unit. If any candidate is a unit within a building, the
    # query cannot distinguish between them.
    if any(u is not None for u in candidate_units):
        raise EPCAmbiguousMatchError(
            f"{address!r} names no unit but the building contains units "
            f"{sorted(u for u in candidate_units if u)}", same_number)

    if len(same_number) == 1:
        return SelectionResult(same_number[0], "street_number_unit", 80)

    raise EPCAmbiguousMatchError(
        f"{len(same_number)} candidates remain for {address!r}", same_number)
