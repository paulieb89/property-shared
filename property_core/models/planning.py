"""Domain models for Planning data.

These are core business objects for planning council/postcode lookups,
independent of the API layer. Used by CLI, MCP apps, and other consumers.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LocalAuthority(BaseModel):
    """Local authority information from postcodes.io."""

    name: str | None = Field(None, description="Local authority name (e.g., 'Sheffield')")
    code: str | None = Field(None, description="ONS local authority code (e.g., 'E08000019')")
    region: str | None = Field(None, description="Region (e.g., 'Yorkshire and The Humber')")
    country: str | None = Field(None, description="Country (e.g., 'England')")


class Council(BaseModel):
    """Planning council with portal information.

    Represents a UK council's planning portal details from our verified database.
    Note: untested councils may have fewer fields populated.
    """

    name: str = Field(..., description="Council name (e.g., 'Sheffield')")
    code: str | None = Field(None, description="Council code/slug (e.g., 'sheffield')")
    system: str | None = Field(None, description="Planning system type: idox, northgate, ocella, arcus, lar, agile")
    base_url: str | None = Field(None, description="Base URL for the planning portal")
    search_url: str | None = Field(None, description="Direct search URL if available")
    status: str | None = Field(None, description="Verification status: verified, untested")
    notes: str | None = Field(None, description="Additional notes about the council portal")
    verified_date: str | None = Field(None, description="Date council was last verified (YYYY-MM-DD)")
    postcodes_io_name: str | None = Field(None, description="Name as returned by postcodes.io for matching")


class CouncilSummary(BaseModel):
    """Minimal council info for search results.

    Lighter version of Council with only essential fields.
    """

    name: str = Field(..., description="Council name")
    code: str = Field(..., description="Council code/slug")
    system: str = Field(..., description="Planning system type")
    status: str | None = Field(None, description="Verification status")


class SearchUrls(BaseModel):
    """URLs for searching a council's planning portal."""

    search_page: str | None = Field(None, description="Main search page URL")
    direct_search: str | None = Field(None, description="Direct postcode search URL (Idox only)")
    instructions: str | None = Field(None, description="Human-readable search instructions")
