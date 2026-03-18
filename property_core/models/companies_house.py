"""Companies House models — company records, officers, search results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CompanyOfficer(BaseModel):
    """A company officer (director, secretary, etc.)."""
    name: str | None = None
    role: str | None = None
    appointed: str | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> CompanyOfficer:
        return cls(
            name=data.get("name"),
            role=data.get("officer_role"),
            appointed=data.get("appointed_on"),
            raw=data,
        )


class CompanyRecord(BaseModel):
    """Full company record from Companies House."""
    company_number: str | None = None
    company_name: str | None = None
    company_status: str | None = None
    company_type: str | None = None
    date_of_creation: str | None = None
    registered_office: dict[str, Any] | None = None
    sic_codes: list[str] = Field(default_factory=list)
    officers: list[CompanyOfficer] = Field(default_factory=list)
    raw: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls,
        data: dict[str, Any],
        officers: list[dict[str, Any]] | None = None,
    ) -> CompanyRecord:
        officer_models = []
        if officers:
            officer_models = [CompanyOfficer.from_api_response(o) for o in officers[:5]]

        return cls(
            company_number=data.get("company_number"),
            company_name=data.get("company_name"),
            company_status=data.get("company_status"),
            company_type=data.get("type"),
            date_of_creation=data.get("date_of_creation"),
            registered_office=data.get("registered_office_address"),
            sic_codes=data.get("sic_codes", []),
            officers=officer_models,
            raw=data,
        )


class CompanySearchItem(BaseModel):
    """A single result from a Companies House name search."""
    company_number: str | None = None
    company_name: str | None = None
    company_status: str | None = None
    company_type: str | None = None
    date_of_creation: str | None = None
    address_snippet: str | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> CompanySearchItem:
        return cls(
            company_number=data.get("company_number"),
            company_name=data.get("title"),
            company_status=data.get("company_status"),
            company_type=data.get("company_type"),
            date_of_creation=data.get("date_of_creation"),
            address_snippet=data.get("address_snippet"),
            raw=data,
        )


class CompanySearchResult(BaseModel):
    """Search results from Companies House name search."""
    query: str
    total_results: int = 0
    companies: list[CompanySearchItem] = Field(default_factory=list)
