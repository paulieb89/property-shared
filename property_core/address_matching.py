"""Address matching and parsing utilities.

Pure functions for normalizing, scoring, and parsing UK property addresses.
Extracted so they can be used independently across the codebase.
"""

from __future__ import annotations

import re
from typing import Optional

from property_core.models.epc import EPCData

# UK postcode regex — matches at end of string (e.g., "10 Downing Street, SW1A 2AA")
UK_POSTCODE_RE = re.compile(
    r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\s*$",
    re.IGNORECASE,
)


def parse_address(q: str) -> tuple[str | None, str | None]:
    """Parse combined address string into (postcode, street_address).

    Extracts postcode from end of string, normalizes spacing.

    Examples:
        "10 Downing Street, SW1A 2AA" -> ("SW1A 2AA", "10 Downing Street")
        "SW1A2AA" -> ("SW1A 2AA", None)
        "not a postcode" -> (None, None)
    """
    q = q.strip()
    match = UK_POSTCODE_RE.search(q)
    if match:
        postcode = match.group(1).upper()
        # Normalize postcode spacing (e.g., "SW1A2AA" -> "SW1A 2AA")
        if " " not in postcode and len(postcode) >= 5:
            postcode = postcode[:-3] + " " + postcode[-3:]
        address = q[: match.start()].strip().rstrip(",").strip()
        return (postcode, address if address else None)
    return (None, None)


def normalize_address(address: str) -> str:
    """Normalize address for comparison."""
    addr = address.lower()
    addr = re.sub(r"[,.'\"()-]", " ", addr)
    addr = re.sub(r"\s+", " ", addr).strip()
    return addr


def extract_number(address: str) -> str | None:
    """Extract house number from address."""
    match = re.match(r"^(\d+[a-zA-Z]?)\b", address.strip())
    return match.group(1).lower() if match else None


def extract_street(address: str) -> str | None:
    """Extract street name from address."""
    addr = re.sub(r"^\d+[a-zA-Z]?\s*", "", address.strip())
    addr = normalize_address(addr)
    parts = addr.split()
    if len(parts) >= 2:
        return " ".join(parts[:2])
    return parts[0] if parts else None


def match_score(cert_address: str, target_address: str) -> int:
    """Score how well a certificate address matches the target (0-100)."""
    cert_norm = normalize_address(cert_address)
    target_norm = normalize_address(target_address)

    if cert_norm == target_norm:
        return 100

    score = 0
    cert_num = extract_number(cert_address)
    target_num = extract_number(target_address)
    if cert_num and target_num and cert_num == target_num:
        score += 50

    cert_street = extract_street(cert_address)
    target_street = extract_street(target_address)
    if cert_street and target_street:
        if cert_street == target_street:
            score += 30
        elif cert_street in target_street or target_street in cert_street:
            score += 15

    cert_words = set(cert_norm.split())
    target_words = set(target_norm.split())
    overlap = len(cert_words & target_words)
    score += min(overlap * 3, 15)

    return score


def match_epc_address(
    certificates: list[EPCData],
    address: str,
    min_score: int = 30,
) -> Optional[tuple[EPCData, int]]:
    """Find the best-matching EPC certificate for an address.

    Args:
        certificates: List of EPCData objects (from search_all_by_postcode).
        address: Address to match against.
        min_score: Minimum match score (0-100) to accept.

    Returns:
        Tuple of (EPCData, match_score) or None if no match meets threshold.
    """
    best_cert = None
    best_score = -1
    for cert in certificates:
        cert_addr = cert.address or ""
        score = match_score(cert_addr, address)
        if score > best_score:
            best_score = score
            best_cert = cert
    if best_cert and best_score >= min_score:
        return (best_cert, best_score)
    return None
