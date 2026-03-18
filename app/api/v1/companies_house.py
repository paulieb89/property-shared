"""Companies House API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from property_core.companies_house_client import CompaniesHouseClient
from property_core.models.companies_house import CompanyRecord, CompanySearchResult

router = APIRouter(prefix="/companies", tags=["companies"])
client = CompaniesHouseClient()


@router.get("/search", response_model=CompanySearchResult)
def search(
    q: str = Query(..., description="Company name to search"),
    limit: int = Query(5, ge=1, le=20, description="Max results"),
) -> CompanySearchResult:
    """Search Companies House by company name."""
    if not client.is_configured():
        raise HTTPException(
            status_code=501,
            detail="Companies House not configured (set COMPANIES_HOUSE_API_KEY)",
        )
    return client.search(q, items_per_page=limit)


@router.get("/{company_number}", response_model=CompanyRecord)
def get_company(company_number: str) -> CompanyRecord:
    """Fetch a company by number (e.g. 00445790), including officers."""
    if not client.is_configured():
        raise HTTPException(
            status_code=501,
            detail="Companies House not configured (set COMPANIES_HOUSE_API_KEY)",
        )
    result = client.get_company(company_number)
    if result is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return result
