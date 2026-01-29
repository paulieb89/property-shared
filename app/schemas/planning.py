"""API envelope schemas for Planning endpoints.

Domain models (Council, LocalAuthority, etc.) live in property_core.models.planning.
This file defines API response wrappers following the same pattern as other schemas.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

# Re-export domain models for backward compatibility within app/
from property_core.models.planning import (  # noqa: F401
    Council,
    CouncilSummary,
    LocalAuthority,
    SearchUrls,
)


class CouncilForPostcodeResponse(BaseModel):
    """Response for council-for-postcode lookup.

    Returns local authority info from postcodes.io and matched planning council.
    When include_raw=True, includes full postcodes.io response.
    """

    postcode: str = Field(..., description="Normalized postcode")
    local_authority: LocalAuthority | None = Field(
        None, description="Local authority info from postcodes.io"
    )
    council: Council | None = Field(
        None, description="Matched planning council from our database, if found"
    )
    council_found: bool = Field(..., description="Whether a council was matched")
    error: str | None = Field(None, description="Error message if postcode not found")
    raw: dict[str, Any] | None = Field(
        None,
        description="Raw postcodes.io response when include_raw=true. "
        "Contains NHS region, constituency, LSOA, police force, etc.",
    )


class PlanningSearchResponse(BaseModel):
    """Response for planning search by postcode.

    Returns council info and search URLs for the planning portal.
    """

    postcode: str = Field(..., description="Normalized postcode")
    local_authority: LocalAuthority | None = Field(
        None, description="Local authority info"
    )
    council_found: bool = Field(..., description="Whether a council was matched")
    council: CouncilSummary | None = Field(
        None, description="Matched council summary"
    )
    search_urls: SearchUrls | None = Field(
        None, description="URLs for searching the planning portal"
    )
    error: str | None = Field(None, description="Error if council not found")
    note: str | None = Field(
        None, description="Advisory note (e.g., about residential IP requirements)"
    )


class CouncilsListResponse(BaseModel):
    """Response for listing all councils."""

    verified_count: int = Field(..., description="Number of verified councils")
    untested_count: int = Field(..., description="Number of untested councils")
    councils: list[Council] = Field(default_factory=list, description="Verified councils")
    untested: list[Council] = Field(default_factory=list, description="Untested councils")
    systems: dict[str, Any] = Field(
        default_factory=dict, description="System type metadata"
    )


# Request/response models for scraping endpoints (moved from api/v1/planning.py)


class PlanningScraperRequest(BaseModel):
    """Request to scrape a planning application."""

    url: str = Field(..., description="URL of the planning application page")
    save_screenshots: bool = Field(False, description="Save screenshots to disk")


class PlanningScraperResponse(BaseModel):
    """Response from planning scraper."""

    url: str = Field(..., description="URL that was scraped")
    council_system: str = Field(..., description="Detected council system type")
    screenshots_captured: int = Field(..., description="Number of screenshots taken")
    data: dict[str, Any] = Field(..., description="Extracted planning data")


class ProbeRequest(BaseModel):
    """Request for connectivity probe."""

    url: str = Field(..., description="URL to probe")
    timeout_ms: int = Field(30000, description="Timeout in milliseconds")


class ProbeResponse(BaseModel):
    """Diagnostic probe response."""

    url: str
    success: bool
    page_title: str | None = None
    status_code: int | None = None
    load_time_ms: int | None = None
    screenshot_base64: str | None = None
    html_snippet: str | None = None
    blocking_indicators: list[str] = Field(default_factory=list)
    error: str | None = None
    proxy_used: str | None = None


class SearchResultsRequest(BaseModel):
    """Request to search for planning applications."""

    postcode: str = Field(..., description="UK postcode to search")
    portal_url: str | None = Field(None, description="Override portal URL")
    system: str | None = Field(None, description="Override system type")
    max_results: int = Field(10, description="Maximum results to return")


class PlanningApplication(BaseModel):
    """Single planning application result."""

    reference: str | None = None
    address: str | None = None
    description: str | None = None
    status: str | None = None
    link: str | None = None


class SearchResultsResponse(BaseModel):
    """Response with planning search results."""

    postcode: str
    council_name: str | None = None
    system: str | None = None
    portal_url: str
    results: list[PlanningApplication] = Field(default_factory=list)
    count: int
