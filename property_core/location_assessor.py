"""Location scoring using live PPD transaction data.

This uses Land Registry Price Paid Data (via the vendored `PricePaidDataClient`)
to derive simple signals:
- transaction volume (demand/activity)
- median price (affordability/affluence proxy)

It keeps a short in-memory cache per outcode to avoid repeated SPARQL calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from property_core.ppd_client import PricePaidDataClient


def _clamp(value: float, minimum: float = 0, maximum: float = 100) -> int:
    return int(max(minimum, min(maximum, value)))


class LocationAssessor:
    def __init__(self, *, ppd_client: Optional[PricePaidDataClient] = None) -> None:
        self._cache: Dict[str, dict] = {}
        self.ppd = ppd_client or PricePaidDataClient()

    def assess(self, postcode: str, address: Optional[str] = None) -> dict:
        outcode = postcode.strip().upper().split()[0]
        if not outcode:
            raise ValueError("postcode is required")

        now = datetime.now(tz=timezone.utc)
        cached = self._cache.get(outcode)
        if cached and cached["cache_expires_at"] > now:
            return cached

        try:
            summary = self.ppd.get_comps_summary(
                postcode=outcode,
                months=12,
                limit=150,
                search_level="district",
            )
            count = int(summary.get("count", 0) or 0)
            median = summary.get("median")
            breakdown = self._derive_breakdown(count=count, median_price=median)
            confidence = 0.65 if count >= 5 else 0.35
            reasoning = (
                f"Derived from {count} Land Registry transactions in the last 12 months "
                f"for district {outcode}; median price "
                f"{'£{:,}'.format(median) if median else 'unknown'}."
            )
            data_sources = ["land_registry:price_paid"]
        except Exception as exc:  # noqa: BLE001
            breakdown = self._fallback_breakdown()
            reasoning = f"PPD lookup failed, returning neutral scores: {exc}"
            confidence = 0.15
            data_sources = ["fallback:neutral"]

        scores = list(breakdown.values())
        assessment = {
            "postcode": postcode,
            "score": int(sum(scores) / len(scores)),
            "breakdown": breakdown,
            "reasoning": reasoning,
            "confidence": confidence,
            "data_sources": data_sources,
            "local_highlights": [],
            "cached": False,
            "assessed_at": now,
            "cache_expires_at": now + timedelta(hours=6),
        }
        cached_assessment = assessment | {"cached": True}
        self._cache[outcode] = cached_assessment
        return assessment

    def _derive_breakdown(self, *, count: int, median_price: Optional[int]) -> Dict[str, int]:
        # Volume-based score: active markets get higher scores
        volume_score = _clamp(count * 5, 20, 95)  # 0 ->20, 20+ ->95

        # Affordability/affluence proxy from median price
        if median_price is None:
            price_score = 50
        elif median_price <= 200_000:
            price_score = 55
        elif median_price <= 400_000:
            price_score = 65
        elif median_price <= 800_000:
            price_score = 75
        elif median_price <= 1_500_000:
            price_score = 82
        else:
            price_score = 90

        # Map to breakdown dimensions
        return {
            "safety": _clamp(60 + (price_score - 70) / 2, 40, 90),
            "schools": price_score,
            "transport": price_score - 5,
            "amenities": volume_score,
            "employment": price_score,
            "rental_demand": volume_score,
        }

    def _fallback_breakdown(self) -> Dict[str, int]:
        return {
            "safety": 50,
            "schools": 50,
            "transport": 50,
            "amenities": 50,
            "employment": 50,
            "rental_demand": 50,
        }
