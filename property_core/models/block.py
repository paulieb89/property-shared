"""Block analysis models — buildings with multiple flat sales."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BlockUnit(BaseModel):
    """A single unit sale within a building."""
    saon: str | None = None
    price: int | None = None
    date: str | None = None
    new_build: bool | None = None


class BlockBuilding(BaseModel):
    """A building with multiple unit sales."""
    building_name: str | None = None
    street: str | None = None
    postcode: str | None = None
    transaction_count: int = 0
    new_build_count: int = 0
    avg_price: int | None = None
    min_price: int | None = None
    max_price: int | None = None
    total_value: int | None = None
    date_range: str | None = None
    transactions: list[BlockUnit] = Field(default_factory=list)


class BlockAnalysisResponse(BaseModel):
    """Top-level response for block analysis."""
    postcode: str
    search_level: str = "sector"
    months: int = 24
    blocks_found: int = 0
    blocks: list[BlockBuilding] = Field(default_factory=list)
