"""Lightweight location scoring (placeholder).

Provides a deterministic, dependency-free scorer that produces a repeatable
LocationAssessment-style payload for a UK postcode. This is intentionally
heuristic-only so the API surface is available without external services.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional


def _stable_score(key: str, salt: str) -> int:
    """Return a stable score between 30 and 90 for a given key/salt combo."""
    digest = hashlib.sha1(f"{key}:{salt}".encode("utf-8")).hexdigest()
    return 30 + (int(digest[:6], 16) % 61)


class LocationAssessor:
    def __init__(self) -> None:
        self._cache: Dict[str, dict] = {}

    def assess(self, postcode: str, address: Optional[str] = None) -> dict:
        outcode = postcode.strip().upper().split()[0]
        if not outcode:
            raise ValueError("postcode is required")

        now = datetime.now(tz=timezone.utc)
        cached = self._cache.get(outcode)
        if cached and cached["cache_expires_at"] > now:
            return cached

        breakdown = {
            "safety": _stable_score(outcode, "safety"),
            "schools": _stable_score(outcode, "schools"),
            "transport": _stable_score(outcode, "transport"),
            "amenities": _stable_score(outcode, "amenities"),
            "employment": _stable_score(outcode, "employment"),
            "rental_demand": _stable_score(outcode, "rental"),
        }
        scores = list(breakdown.values())
        assessment = {
            "postcode": postcode,
            "score": int(sum(scores) / len(scores)),
            "breakdown": breakdown,
            "reasoning": "Deterministic heuristic scores for demo purposes; not real-world rated.",
            "confidence": 0.2,
            "data_sources": ["heuristic:deterministic-hash"],
            "local_highlights": [],
            "cached": False,
            "assessed_at": now,
            "cache_expires_at": now + timedelta(hours=6),
        }
        cached_assessment = assessment | {"cached": True}
        self._cache[outcode] = cached_assessment
        return assessment
