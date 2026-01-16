"""Location scoring service wrapper."""

from __future__ import annotations

from typing import Optional

from app.schemas.location import LocationAssessment, LocationBreakdown
from property_core.location_assessor import LocationAssessor


class LocationService:
    def __init__(self, assessor: Optional[LocationAssessor] = None) -> None:
        self.assessor = assessor or LocationAssessor()

    async def assess(self, postcode: str, address: Optional[str] = None) -> LocationAssessment:
        payload = self.assessor.assess(postcode, address=address)
        # Normalize into Pydantic schema
        return LocationAssessment(
            postcode=payload["postcode"],
            score=payload["score"],
            breakdown=LocationBreakdown(**payload["breakdown"]),
            reasoning=payload.get("reasoning", ""),
            confidence=payload.get("confidence", 0.0),
            data_sources=payload.get("data_sources", []),
            local_highlights=payload.get("local_highlights", []),
            cached=payload.get("cached", False),
            assessed_at=payload.get("assessed_at"),
            cache_expires_at=payload.get("cache_expires_at"),
        )
