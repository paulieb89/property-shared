"""Planning API endpoints: scrape UK council planning portals."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, HttpUrl

router = APIRouter(prefix="/planning", tags=["planning"])


class PlanningScraperRequest(BaseModel):
    """Request to scrape a planning application."""
    url: str
    save_screenshots: bool = False


class PlanningScraperResponse(BaseModel):
    """Response from planning scraper."""
    url: str
    council_system: str
    screenshots_captured: int
    data: dict[str, Any]


class PlanningScrapeError(BaseModel):
    """Error response."""
    url: str
    error: str


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


class ProbeRequest(BaseModel):
    """Request for connectivity probe."""
    url: str
    timeout_ms: int = 30000


class ProbeResponse(BaseModel):
    """Diagnostic probe response."""
    url: str
    success: bool
    page_title: Optional[str]
    status_code: Optional[int]
    load_time_ms: Optional[int]
    screenshot_base64: Optional[str]
    html_snippet: Optional[str]
    blocking_indicators: list[str]
    error: Optional[str]
    proxy_used: Optional[str] = None


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


@router.get("/councils")
def list_councils() -> dict[str, Any]:
    """List verified UK council planning portals."""
    import json
    from pathlib import Path

    councils_file = Path(__file__).parent.parent.parent.parent / "property_core" / "planning_councils.json"
    if not councils_file.exists():
        return {"councils": [], "untested": [], "systems": {}}

    with open(councils_file) as f:
        data = json.load(f)

    return {
        "verified_count": len(data.get("councils", [])),
        "untested_count": len(data.get("untested", [])),
        "councils": data.get("councils", []),
        "untested": data.get("untested", []),
        "systems": data.get("systems", {}),
    }


@router.get("/council/{code}")
def get_council(code: str) -> dict[str, Any]:
    """Get details for a specific council by code."""
    import json
    from pathlib import Path

    councils_file = Path(__file__).parent.parent.parent.parent / "property_core" / "planning_councils.json"
    if not councils_file.exists():
        raise HTTPException(status_code=404, detail="Councils database not found")

    with open(councils_file) as f:
        data = json.load(f)

    # Search verified and untested
    for council in data.get("councils", []) + data.get("untested", []):
        if council.get("code") == code:
            return council

    raise HTTPException(status_code=404, detail=f"Council '{code}' not found")
