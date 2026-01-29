"""Planning API endpoints: scrape UK council planning portals."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.planning import (
    Council,
    CouncilForPostcodeResponse,
    CouncilsListResponse,
    PlanningApplication,
    PlanningScraperRequest,
    PlanningScraperResponse,
    PlanningSearchResponse,
    ProbeRequest,
    ProbeResponse,
    SearchResultsRequest,
    SearchResultsResponse,
)
from property_core.planning_service import PlanningService

router = APIRouter(prefix="/planning", tags=["planning"])
service = PlanningService()


@router.post("/scrape", response_model=PlanningScraperResponse)
def scrape_application(
    request: PlanningScraperRequest,
) -> PlanningScraperResponse:
    """
    Scrape a single planning application from any UK council portal.

    Uses vision AI to extract structured data from screenshots.
    Supports Idox, Northgate, Ocella, Arcus, and generic systems.

    Note: This is a sync endpoint that may take 20-40 seconds.
    """
    try:
        from property_core.planning_scraper import scrape_planning_application
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Planning scraper not available: {e}. Install playwright and openai.",
        ) from e

    try:
        result = scrape_planning_application(
            url=request.url,
            save_screenshots=request.save_screenshots,
        )
        return PlanningScraperResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Scrape failed: {e}") from e


@router.post("/probe", response_model=ProbeResponse)
def probe_url(request: ProbeRequest) -> ProbeResponse:
    """
    Quick connectivity probe to diagnose access issues.

    Returns screenshot, HTML snippet, and blocking indicators.
    Use this to diagnose why scraping might be failing (IP blocks, captchas, etc).
    """
    try:
        from property_core.planning_scraper import probe_connectivity
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Probe not available: {e}",
        ) from e

    try:
        result = probe_connectivity(url=request.url, timeout_ms=request.timeout_ms)
        return ProbeResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Probe failed: {e}") from e


@router.get("/search", response_model=PlanningSearchResponse)
def search_by_postcode(
    postcode: str = Query(..., min_length=2, description="UK postcode"),
) -> PlanningSearchResponse:
    """Search for planning applications by postcode.

    Looks up the council for this postcode and returns search URLs.
    For Idox councils (most common), provides a direct search URL.
    For other systems, provides the search page and instructions.

    Note: Actual scraping of search results requires UK residential IP.
    """
    try:
        result = service.search(postcode)
        return PlanningSearchResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Planning search failed: {e}") from e


@router.get("/council-for-postcode", response_model=CouncilForPostcodeResponse)
def council_for_postcode(
    postcode: str = Query(..., min_length=2, description="UK postcode"),
    include_raw: bool = Query(False, description="Include full postcodes.io response"),
) -> CouncilForPostcodeResponse:
    """Look up the planning council for a UK postcode.

    Uses postcodes.io to identify the local authority, then matches to our
    councils database. Returns council info if found, otherwise returns
    local authority info for reference.

    When include_raw=true, includes full postcodes.io data (NHS region,
    constituency, LSOA, police force, etc.) in the 'raw' field.
    """
    try:
        result = service.council_for_postcode(postcode, include_raw=include_raw)
        return CouncilForPostcodeResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Postcode lookup failed: {e}") from e


@router.get("/councils", response_model=CouncilsListResponse)
def list_councils() -> CouncilsListResponse:
    """List verified UK council planning portals."""
    result = service.list_councils()
    return CouncilsListResponse(**result)


@router.get("/council/{code}", response_model=Council)
def get_council(code: str) -> Council:
    """Get details for a specific council by code."""
    council = service.get_council(code)
    if not council:
        raise HTTPException(status_code=404, detail=f"Council '{code}' not found")
    return Council(**council)


@router.post("/search-results", response_model=SearchResultsResponse)
def search_results(request: SearchResultsRequest) -> SearchResultsResponse:
    """
    Search for planning applications by postcode.

    Uses vision-guided browser automation to fill council search forms
    and extract results. Takes 30-60 seconds.

    Requires: Playwright, OpenAI API key, UK residential IP (or proxy).
    """
    try:
        from property_core.planning_scraper import search_planning_by_postcode
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Planning search not available: {e}. Install playwright and openai.",
        ) from e

    # Resolve portal_url from postcode if not provided
    portal_url = request.portal_url
    system = request.system
    council_name = None

    if not portal_url:
        search_data = service.search(request.postcode)
        if not search_data.get("council_found"):
            raise HTTPException(
                status_code=404,
                detail=f"No council found for postcode '{request.postcode}'",
            )
        council = search_data["council"]
        council_name = council.get("name")
        system = system or council.get("system")
        urls = search_data.get("search_urls", {})
        portal_url = urls.get("direct_search") or urls.get("search_page")
        # For Idox, use simple search form (not weeklyList)
        if system == "idox" and portal_url:
            if "weeklyList" in portal_url or "action=simple" not in portal_url:
                base = portal_url.split("/search.do")[0] if "/search.do" in portal_url else portal_url.rstrip("/")
                portal_url = f"{base}/search.do?action=simple"
        if not portal_url:
            raise HTTPException(
                status_code=404,
                detail="No search URL available for this council",
            )

    try:
        results = search_planning_by_postcode(
            portal_url=portal_url,
            postcode=request.postcode,
            max_results=request.max_results,
            system=system,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Search failed: {e}") from e

    return SearchResultsResponse(
        postcode=request.postcode,
        council_name=council_name,
        system=system,
        portal_url=portal_url,
        results=[PlanningApplication(**app) for app in results],
        count=len(results),
    )
