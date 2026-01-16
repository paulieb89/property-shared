"""Pydantic schemas for Price Paid Data (PPD) endpoints."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PPDTransaction(BaseModel):
    transaction_id: Optional[str] = None
    price: Optional[int] = None
    date: Optional[str] = None
    postcode: Optional[str] = None
    property_type: Optional[str] = None
    estate_type: Optional[str] = None
    transaction_category: Optional[str] = None
    new_build: Optional[bool] = None
    paon: Optional[str] = None
    saon: Optional[str] = None
    street: Optional[str] = None
    town: Optional[str] = None
    county: Optional[str] = None


class PPDSearchResponse(BaseModel):
    count: int
    limit: int
    offset: int
    results: List[PPDTransaction] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class PPDCompsQuery(BaseModel):
    postcode: str
    property_type: Optional[str] = None
    months: int
    search_level: str


class PPDCompsResponse(BaseModel):
    query: PPDCompsQuery
    count: int
    median: Optional[int] = None
    mean: Optional[int] = None
    min: Optional[int] = None
    max: Optional[int] = None
    thin_market: bool
    transactions: List[PPDTransaction] = Field(default_factory=list)


class PPDDownloadURLResponse(BaseModel):
    url: str
