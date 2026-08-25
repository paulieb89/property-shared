"""Safe candidate selection.

v1.14 contract — deliberately only two ways to select a certificate:

  1. exact UPRN match (exactly one candidate carries it), or
  2. exact normalized full-address equality,

and otherwise EPCAmbiguousMatchError.

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

Each fix was correct and each left another gap, because UK address text does not
decompose reliably by pattern. The asymmetry decides it: refusing a real match is
recoverable — the caller browses summaries and picks a certificate number —
whereas attaching another property's EPC silently corrupts floor area, rating and
every price-per-sqft derived from them.

Normalization is limited to case and punctuation. Nothing is inferred: no
abbreviation expansion, no component reordering, no dropped components.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class SelectionResult:
    """The selected row and the identity evidence that selected it.

    ``confidence`` is always 100: the only accepted evidence is identity. It is
    retained so callers that record a score keep a stable field, not because
    there is a spectrum.
    """

    row: EPCSearchRow
    method: str          # "uprn" | "exact_address"
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
            raise EPCAmbiguousMatchError(
                f"{len(hits)} certificates share UPRN {uprn}; cannot select one", hits)
        # A supplied UPRN that matches nothing is evidence of a MISS, not an
        # invitation to fall back to weaker address text.
        raise EPCAmbiguousMatchError(
            f"UPRN {uprn} matched no candidate at this postcode; refusing to fall back "
            "to address matching, which could select a different property", rows)

    if not address:
        raise EPCAmbiguousMatchError(
            f"{len(rows)} candidate(s) but no address or UPRN supplied; there is no "
            "evidence to identify a specific property", rows)

    target = _norm(address)
    exact = [r for r in rows if _norm(r.address) == target]
    if len(exact) == 1:
        return SelectionResult(exact[0], "exact_address", 100)
    if len(exact) > 1:
        raise EPCAmbiguousMatchError(
            f"{len(exact)} certificates share the address text {address!r}; cannot "
            "select one", exact)

    raise EPCAmbiguousMatchError(
        f"no candidate's address exactly matches {address!r}. Selection requires a "
        "UPRN or an exact address match — partial agreement on street, building or "
        "unit is not accepted, because it has repeatedly selected a different "
        f"property. Candidate addresses: "
        f"{sorted(r.address for r in rows if r.address)[:5]}",
        rows,
    )
