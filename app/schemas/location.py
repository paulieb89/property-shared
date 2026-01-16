"""Pydantic schemas for location assessments."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class LocationBreakdown(BaseModel):
    safety: int = 50
    schools: int = 50
    transport: int = 50
    amenities: int = 50
    employment: int = 50
    rental_demand: int = 50

    @property
    def average(self) -> int:
        values = [
            self.safety,
            self.schools,
            self.transport,
            self.amenities,
            self.employment,
            self.rental_demand,
        ]
        return int(sum(values) / len(values))


class LocationAssessment(BaseModel):
    postcode: str
    score: int = 50
    breakdown: LocationBreakdown = Field(default_factory=LocationBreakdown)
    reasoning: str = ""
    confidence: float = 0.5
    data_sources: List[str] = Field(default_factory=list)
    local_highlights: List[str] = Field(default_factory=list)
    cached: bool = False
    assessed_at: datetime = Field(default_factory=datetime.utcnow)
    cache_expires_at: Optional[datetime] = None

    class Config:
        arbitrary_types_allowed = True
