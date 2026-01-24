"""Property report endpoint: aggregated property assessment."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from property_core.models.report import PropertyReport
from property_core.report_service import PropertyReportService

router = APIRouter(prefix="/property", tags=["property"])


class ReportRequest(BaseModel):
    """Request to generate a property report."""
    address: str
    include_rentals: bool = True
    include_sales_market: bool = True
    ppd_months: int = 24
    search_radius: float = 0.5


@router.post("/report", response_model=PropertyReport)
async def generate_report(
    request: ReportRequest,
    format: Optional[str] = Query(None, description="Response format: 'html' or default JSON"),
):
    """
    Generate a comprehensive property report.

    Aggregates data from Land Registry (PPD), EPC register, and Rightmove
    (rentals + sales) into a single assessment with estimated value range,
    yield analysis, and market context.

    Address format: "10 Downing Street, SW1A 2AA" (postcode at end).
    """
    service = PropertyReportService()

    try:
        report = await service.generate_report(
            address_query=request.address,
            include_rentals=request.include_rentals,
            include_sales_market=request.include_sales_market,
            ppd_months=request.ppd_months,
            search_radius=request.search_radius,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Report generation failed: {e}") from e

    if format == "html":
        from pathlib import Path

        from jinja2 import Environment, FileSystemLoader

        template_dir = Path(__file__).parent.parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("report.html")
        html = template.render(report=report)
        return HTMLResponse(content=html)

    return report
