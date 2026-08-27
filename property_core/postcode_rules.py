"""Allowlisted UK postcode grammar for PPD queries.

Two jobs, both about not lying to the caller:

1. Reject malformed input at the boundary with a typed error, instead of passing
   it to SPARQL and returning an empty 200 that reads as "no sales here".
2. Decide containment: whether a returned row genuinely belongs to the requested
   outcode or sector. ``STRSTARTS(?postcode, "B5")`` matches "B50 4AA", so
   membership is tested against the *parsed* outcode/sector, never by text prefix.
"""

from __future__ import annotations

import re
from typing import Optional

# Outcode: 1-2 letters, a digit, then an optional letter or digit (B5, B50, N1,
# EC1V, SW1A). Incode: a digit and two letters.
_OUTCODE = r"[A-Z]{1,2}[0-9][A-Z0-9]?"
_INCODE = r"[0-9][A-Z]{2}"

# GIR 0AA (Girobank, Bootle) is a real postcode that fits no standard outcode
# pattern. It is in the allowlist because rejecting a valid postcode as
# "malformed caller input" is the same defect as accepting a malformed one.
_SPECIAL_OUTCODES = ("GIR",)
_OUTCODE_ALT = "|".join([_OUTCODE, *_SPECIAL_OUTCODES])

OUTCODE_RE = re.compile(rf"^(?:{_OUTCODE_ALT})$")
SECTOR_RE = re.compile(rf"^(?:{_OUTCODE_ALT}) [0-9]$")
FULL_RE = re.compile(rf"^(?:{_OUTCODE_ALT}) {_INCODE}$")


#: Any of these means the input is not a postcode a human typed. Normalising a
#: newline into a space would silently accept "B5\n7" as the sector "B5 7".
_CONTROL = frozenset("\x00\t\n\r\x0b\x0c")


def _normalise(value: object) -> str:
    if not isinstance(value, str):
        return ""
    if _CONTROL & set(value):
        return ""
    # Collapse internal whitespace so "B5  4BX" normalises, but a newline or tab
    # never becomes a silent space in a SPARQL literal.
    return " ".join(value.strip().upper().split())


def normalise_postcode(value: object, *, field: str = "postcode") -> str:
    """Validate a full postcode. Raises InvalidPostcodeError."""
    from property_core.exceptions import InvalidPostcodeError

    text = _normalise(value)
    if not FULL_RE.match(text):
        raise InvalidPostcodeError(
            value=value if isinstance(value, str) else repr(value),
            field=field,
            expected="a full UK postcode, e.g. 'B5 4BX'",
        )
    return text


def normalise_prefix(value: object, *, field: str = "postcode_prefix") -> str:
    """Validate an outcode or sector prefix. Raises InvalidPostcodeError."""
    from property_core.exceptions import InvalidPostcodeError

    text = _normalise(value)
    if not (OUTCODE_RE.match(text) or SECTOR_RE.match(text)):
        raise InvalidPostcodeError(
            value=value if isinstance(value, str) else repr(value),
            field=field,
            expected="an outcode ('B5') or sector ('B5 7')",
        )
    return text


def is_sector(prefix: str) -> bool:
    return bool(SECTOR_RE.match(prefix))


def sparql_prefix(prefix: str) -> str:
    """The literal to hand STRSTARTS.

    An outcode must carry its trailing space, or "B5" matches "B50 4AA". A
    sector is already delimited by its own space.
    """
    return prefix if is_sector(prefix) else f"{prefix} "


def outcode_of(postcode: Optional[str]) -> Optional[str]:
    text = _normalise(postcode)
    if not text or " " not in text:
        return None
    head = text.split(" ", 1)[0]
    return head if OUTCODE_RE.match(head) else None


def sector_of(postcode: Optional[str]) -> Optional[str]:
    text = _normalise(postcode)
    if not FULL_RE.match(text):
        return None
    outcode, incode = text.split(" ", 1)
    return f"{outcode} {incode[0]}"


def matches_prefix(postcode: Optional[str], prefix: str) -> bool:
    """Membership by parsed geography, never by text prefix."""
    if is_sector(prefix):
        return sector_of(postcode) == prefix
    return outcode_of(postcode) == prefix
