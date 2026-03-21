"""API envelope schemas for Rightmove endpoints.

Domain models (RightmoveListing, RightmoveListingDetail) live in
property_core.models.rightmove. This file defines only the API response wrappers.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

# Convenience re-exports for API layer imports
from property_core.models.rightmove import (  # noqa: F401
    RightmoveListing,
    RightmoveListingDetail,
)


class RightmoveSearchURLResponse(BaseModel):
    """Response for search URL creation."""

    url: str


class RightmoveListingsResponse(BaseModel):
    """Listings results for a Rightmove search."""

    count: int
    results: List[RightmoveListing] = Field(default_factory=list)


class RightmoveListingDetailResponse(BaseModel):
    """Response for individual listing detail."""

    result: RightmoveListingDetail
