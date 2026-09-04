"""Safe candidate selection.

v1.14 contract — deliberately only four ways to select a certificate:

  1. exact UPRN match (exactly one candidate carries it),
  2. exact normalized full-address equality,
  3. the same, after canonicalizing a LEADING "Flat <n>" / "Apartment <n>"
     designator to one token (see _canon), or
  4. several candidates proven to be ONE property -- an agreed non-empty UPRN
     and agreed canonical address -- in which case the newest certificate by
     registration date wins (see _one_property_latest),

and otherwise EPCAmbiguousMatchError.

Rule 4 is not a fifth relaxation of the kind catalogued below. Those all
invented a winner from partial evidence about *which property*. This one adds no
property evidence at all: it applies only once identity is already established
by rules 1-3's standard, and then chooses among that single property's own
certificate history, which is a thing properties genuinely have -- re-certified
on every sale and let.

There is no structured street/building/unit acceptance path. One existed and was
repaired four times, each round finding a new way for partial evidence to look
sufficient:

  * a different house on the same street scored 36 against a threshold of 30
  * every flat in a block tied at 62, resolved by upstream row order
  * "12 High Street" matched "12 High Road" on the shared token "high"
  * a lone remaining candidate was treated as identity
  * "Flat 2, 24 …" matched "Flat 2, 99 …" via a pooled set of all numbers
  * "Flat 2, Block 3, 24 …" matched "… Block 3, 99 …" — the block number was
    read as the building number
  * "10 1st Avenue" matched "10 2nd Avenue" — digit-leading tokens were dropped
    from the street, collapsing both to {"avenue"}
  * a whitespace- or punctuation-only address ("   ", "---") matched a candidate
    carrying no address at all — both normalized to "", so absence of evidence
    compared equal to absence of evidence and selected at confidence 100

Each fix was correct and each left another gap, because UK address text does not
decompose reliably by pattern. The asymmetry decides it: refusing a real match is
recoverable — the caller browses summaries and picks a certificate number —
whereas attaching another property's EPC silently corrupts floor area, rating and
every price-per-sqft derived from them.

Normalization is limited to case, punctuation and the leading flat designator.
Nothing else is inferred: no abbreviation expansion, no component reordering, no
dropped components.

The designator rule is measured, not assumed. Over 210 PPD cases against 1,063
live EPC rows, exact-address equality matched 8 (3.8%) where the removed
structured matcher had matched 66 (31.4%). Every one of the 58 lost matches
differed by exactly one token — PPD writes "FLAT n", the EPC register writes
"Apartment n" — with all numeric components identical, 29 in each direction, and
no designator-swapped rival certificate in any of the 12 postcodes. Folding the
two recovers all 58 and merges no two distinct EPC addresses in that corpus.

Unlike the structured matcher, this fails SAFE: canonicalization can only ever
make two addresses collide, and a collision is a duplicate, which the ambiguity
rule already refuses. It cannot invent a winner from partial evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

from property_core.epc.errors import EPCAmbiguousMatchError
from property_core.epc.source_models import EPCSearchRow

_WORD_RE = re.compile(r"[a-z0-9]+", re.I)


def _norm(s: Optional[str]) -> str:
    """Case- and punctuation-insensitive form, preserving token ORDER.

    Order is preserved deliberately: comparing sets would let a reordered or
    partial address match, which is exactly the class of guess this module
    refuses.
    """
    return " ".join(_WORD_RE.findall((s or "").lower()))


# Anchored at the start and requiring a numeric unit immediately after, so this
# rewrites a genuine leading designator and nothing else. "apartment road" has no
# unit token and is untouched; "24 apartment road" is not leading and is
# untouched. "apt" is deliberately absent — it has not been observed in the
# register, and unobserved synonyms are guesses.
_DESIGNATOR_RE = re.compile(r"^(?:flat|apartment)\s+(\d+[a-z]?)(?=\s|$)")


def _canon(s: Optional[str]) -> str:
    """``_norm`` plus one canonical spelling of a LEADING flat designator.

    Only the designator word is rewritten. The unit identifier is preserved
    verbatim, as is every other token and the order of all of them — so this can
    never make two addresses agree that differ anywhere else.
    """
    return _DESIGNATOR_RE.sub(r"flat \1", _norm(s), count=1)


def _registration_date(row: EPCSearchRow) -> Optional[date]:
    """The row's registration date, or None if it cannot be ordered.

    Requires a canonical ISO round trip. Comparing the strings directly would
    be safe only for `YYYY-MM-DD`, and the repo has the scar for it: an
    unvalidated date once sorted after a real one and was read as "beyond
    coverage" (see `ppd_source.validate_date_range`). Anything unparseable
    yields None, which refuses rather than orders arbitrarily.
    """
    text = (row.registration_date or "").strip()
    if not text:
        return None
    try:
        parsed = date.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.isoformat() == text else None


def _one_property_latest(rows: list[EPCSearchRow]) -> Optional[EPCSearchRow]:
    """The newest certificate, when every row is provably the SAME property.

    Properties are re-certified on sale and on let, so a property with several
    certificates is the normal case. Before this, every one of them was
    unreachable by address: the collision rule saw two rows and refused, and no
    amount of correct address text could get past it.

    Deliberately narrower than "same UPRN wins". All three must hold:

      * **every** row carries a non-empty UPRN and they are all equal. UPRN is
        optional upstream and often absent, so absence proves nothing and two
        blanks are not agreement.
      * the rows agree on canonical address text. A shared UPRN with *different*
        addresses is contradictory upstream data, not one property, and picking
        between them would be the precise failure this module exists to prevent.
      * the dates order strictly. A tie has no "most recent", and resolving one
        by row order is a defect already named in the module docstring.

    Any of those failing returns None, and the caller refuses as before.
    """
    uprns = {r.uprn for r in rows}
    if len(uprns) != 1:
        return None
    only = next(iter(uprns))
    if not only:
        return None
    if len({_canon(r.address) for r in rows}) != 1:
        return None

    dated = [(_registration_date(r), r) for r in rows]
    if any(d is None for d, _ in dated):
        return None
    dated.sort(key=lambda pair: pair[0])
    if dated[-1][0] == dated[-2][0]:
        return None
    return dated[-1][1]


@dataclass(frozen=True)
class SelectionResult:
    """The selected row and the identity evidence that selected it.

    ``confidence`` is always 100: the only accepted evidence is identity. It is
    retained so callers that record a score keep a stable field, not because
    there is a spectrum. ``method`` distinguishes literal equality from
    designator-canonicalized equality so a consumer can treat them differently.

    ``uprn_latest_certificate`` is still identity, hence still 100: the property
    is pinned by an agreed UPRN *and* agreed address text. What it additionally
    discloses is that the property had more than one certificate and the newest
    was taken -- a choice among one property's own history, never among
    properties.
    """

    row: EPCSearchRow
    method: str          # "uprn" | "exact_address" | "address_designator_normalized"
                         # | "uprn_latest_certificate"
    confidence: int      # always 100


def select_candidate(
    rows: Iterable[EPCSearchRow],
    *,
    uprn: Optional[str] = None,
    address: Optional[str] = None,
) -> SelectionResult:
    """Return exactly one row identified by UPRN or exact address, or raise.

    Raises:
        EPCAmbiguousMatchError: If no candidate is identified by exact evidence.
            The exception carries the candidates so a caller can present them
            for a human or model to choose between.
    """
    rows = [r for r in rows if r.usable]
    if not rows:
        raise EPCAmbiguousMatchError("no usable candidate rows", [])

    if uprn:
        hits = [r for r in rows if r.uprn and r.uprn == str(uprn)]
        if len(hits) == 1:
            return SelectionResult(hits[0], "uprn", 100)
        if len(hits) > 1:
            latest = _one_property_latest(hits)
            if latest is not None:
                return SelectionResult(latest, "uprn_latest_certificate", 100)
            raise EPCAmbiguousMatchError(
                f"{len(hits)} certificates share UPRN {uprn} but disagree on "
                f"address or registration date, so they cannot be shown to be "
                f"one property's certificate history; cannot select one", hits)
        # A supplied UPRN that matches nothing is evidence of a MISS, not an
        # invitation to fall back to weaker address text.
        raise EPCAmbiguousMatchError(
            f"UPRN {uprn} matched no candidate at this postcode; refusing to fall back "
            "to address matching, which could select a different property", rows)

    if not address:
        raise EPCAmbiguousMatchError(
            f"{len(rows)} candidate(s) but no address or UPRN supplied; there is no "
            "evidence to identify a specific property", rows)

    # Emptiness is ALSO tested after normalization. The guard above only catches
    # None and "": a whitespace- or punctuation-only address ("   ", "---") is
    # truthy but normalizes to "", and an addressless candidate row normalizes to
    # "" as well — so the two compared equal and absence of evidence was selected
    # as `exact_address` at confidence 100.
    target = _norm(address)
    if not target:
        raise EPCAmbiguousMatchError(
            f"{len(rows)} candidate(s) but the supplied address {address!r} carries no "
            "address text once normalized; there is no evidence to identify a specific "
            "property", rows)

    # Rows carrying no address text cannot participate in address matching, for
    # the same reason. A UPRN can still select such a row — that is independent
    # identity evidence — which is why this filter lives here and not in the
    # `usable` filter above.
    rows = [r for r in rows if _norm(r.address)]
    if not rows:
        raise EPCAmbiguousMatchError(
            "no candidate carries address text to match against; a certificate "
            "without an address can only be selected by UPRN", [])

    # Candidates are gathered on the CANONICAL form first, deliberately. Literal
    # equality implies canonical equality, so the canonical set is a superset of
    # the exact set — collecting it first is what makes a collision impossible to
    # miss. Selecting on the exact set first would let a literal match win while
    # a designator-variant duplicate sat unexamined beside it, which is precisely
    # the "one survivor is identity" mistake this module exists to refuse.
    # Only the leading flat designator is canonicalized; every other token, and
    # the order of all of them, still has to match exactly.
    canon_target = _canon(address)
    canon = [r for r in rows if _canon(r.address) == canon_target]

    if len(canon) == 1:
        row = canon[0]
        method = "exact_address" if _norm(row.address) == target \
            else "address_designator_normalized"
        return SelectionResult(row, method, 100)

    if len(canon) > 1:
        # Same property, certified more than once: identity is proven by UPRN,
        # so this is a choice among one property's certificates, not among
        # properties. The current certificate is the newest one.
        latest = _one_property_latest(canon)
        if latest is not None:
            return SelectionResult(latest, "uprn_latest_certificate", 100)
        if all(_norm(r.address) == target for r in canon):
            raise EPCAmbiguousMatchError(
                f"{len(canon)} certificates share the address text {address!r}; "
                "cannot select one", canon)
        raise EPCAmbiguousMatchError(
            f"{len(canon)} certificates share the address text {address!r} once the "
            "leading flat designator is canonicalized; cannot select one", canon)

    raise EPCAmbiguousMatchError(
        f"no candidate's address exactly matches {address!r}. Selection requires a "
        "UPRN, or an exact address match up to case, punctuation and the leading "
        "flat designator — partial agreement on street, building or "
        "unit is not accepted, because it has repeatedly selected a different "
        f"property. Candidate addresses: "
        f"{sorted(r.address for r in rows if r.address)[:5]}",
        rows,
    )
