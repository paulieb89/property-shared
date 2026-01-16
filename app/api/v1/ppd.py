from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.ppd import (
    PPDCompsResponse,
    PPDDownloadURLResponse,
    PPDSearchResponse,
    PPDTransactionRecordResponse,
)
from app.services.ppd_service import PPDService

router = APIRouter(prefix="/ppd", tags=["ppd"])
service = PPDService()


@router.get("/download-url", response_model=PPDDownloadURLResponse)
def download_url(
    kind: Literal["complete", "year", "monthly"] = "monthly",
    year: Optional[int] = Query(None, ge=1995),
    part: Optional[int] = Query(None, ge=1, le=2),
    fmt: Literal["csv", "txt"] = "csv",
) -> PPDDownloadURLResponse:
    try:
        return service.download_url(kind=kind, year=year, part=part, fmt=fmt)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/transactions", response_model=PPDSearchResponse)
def transactions(
    postcode: Optional[str] = Query(None, min_length=2),
    postcode_prefix: Optional[str] = Query(None, min_length=2),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    min_price: Optional[int] = Query(None, ge=0),
    max_price: Optional[int] = Query(None, ge=0),
    property_type: Optional[str] = Query(None, description="D/S/T/F/O"),
    estate_type: Optional[str] = Query(None, description="F/L"),
    transaction_category: Optional[str] = Query(None, description="A/B"),
    record_status: Optional[str] = Query(None, description="A/C/D"),
    new_build: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    order_desc: bool = True,
) -> PPDSearchResponse:
    if bool(postcode) == bool(postcode_prefix):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of postcode or postcode_prefix.",
        )

    try:
        return service.search_transactions(
            postcode=postcode,
            postcode_prefix=postcode_prefix,
            from_date=from_date,
            to_date=to_date,
            min_price=min_price,
            max_price=max_price,
            property_type=property_type,
            estate_type=estate_type,
            transaction_category=transaction_category,
            record_status=record_status,
            new_build=new_build,
            limit=limit,
            offset=offset,
            order_desc=order_desc,
        )
    except Exception as exc:  # noqa: BLE001 - surface as 502 for upstream failures
        raise HTTPException(status_code=502, detail=f"PPD search failed: {exc}") from exc


@router.get("/comps", response_model=PPDCompsResponse)
def comps(
    postcode: str = Query(..., min_length=2),
    property_type: Optional[str] = Query(None, description="D/S/T/F/O"),
    months: int = Query(24, ge=1, le=120),
    limit: int = Query(50, ge=1, le=200),
    search_level: Literal["postcode", "sector", "district"] = "sector",
) -> PPDCompsResponse:
    try:
        return service.comps(
            postcode=postcode,
            property_type=property_type,
            months=months,
            limit=limit,
            search_level=search_level,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"PPD comps failed: {exc}") from exc


@router.get("/transaction/{transaction_id}", response_model=PPDTransactionRecordResponse)
def transaction_record(
    transaction_id: str,
    view: str = Query("all", description="Linked Data view (e.g., all, basic)"),
    include_raw: bool = Query(False, description="Include raw linked-data JSON"),
) -> PPDTransactionRecordResponse:
    try:
        return service.transaction_record(
            transaction_id=transaction_id,
            view=view,
            include_raw=include_raw,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"PPD transaction lookup failed: {exc}",
        ) from exc
