"""Pydantic schemas for Rightmove endpoints."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class RightmoveListing(BaseModel):
    """Normalized Rightmove listing row."""

    id: Any
    url: str
    price: Optional[int] = None
    currency: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    address: Optional[str] = None
    summary: Optional[str] = None
    property_type: Optional[str] = None
    agent_name: Optional[str] = None
    agent_branch: Optional[str] = None
    first_visible_date: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    # Rental-specific fields (None for sales)
    let_available_date: Optional[str] = None
    price_frequency: Optional[str] = None  # "monthly", "weekly" for rentals
    students: Optional[bool] = None
    transaction_type: Optional[str] = None  # "rent" or "buy"


class RightmoveSearchURLResponse(BaseModel):
    """Response for search URL creation."""

    url: str


class RightmoveListingsResponse(BaseModel):
    """Listings results for a Rightmove search."""

    count: int
    results: List[RightmoveListing] = Field(default_factory=list)

