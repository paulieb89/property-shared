"""Companies House API client.

Free API key from https://developer.company-information.service.gov.uk/
Uses basic auth (API key as username, empty password).
"""

from __future__ import annotations

import os

import httpx

from property_core.models.companies_house import (
    CompanyRecord,
    CompanySearchItem,
    CompanySearchResult,
)


class CompaniesHouseClient:
    """Sync client for the Companies House API."""

    BASE_URL = "https://api.company-information.service.gov.uk"
    SANDBOX_URL = "https://api-sandbox.company-information.service.gov.uk"

    def __init__(
        self,
        api_key: str | None = None,
        sandbox: bool | None = None,
        timeout: float = 10.0,
    ):
        self.api_key = api_key or os.getenv("COMPANIES_HOUSE_API_KEY", "")
        if sandbox is None:
            sandbox = os.getenv("COMPANIES_HOUSE_SANDBOX", "").lower() in ("true", "1", "yes")
        self.sandbox = sandbox
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def _base_url(self) -> str:
        return self.SANDBOX_URL if self.sandbox else self.BASE_URL

    def _auth(self) -> tuple[str, str]:
        return (self.api_key, "")

    def search(self, query: str, items_per_page: int = 5) -> CompanySearchResult:
        """Search Companies House by company name.

        Args:
            query: Company name to search for.
            items_per_page: Max results (default 5).

        Returns:
            CompanySearchResult with matching companies.
        """
        if not self.is_configured():
            return CompanySearchResult(query=query, total_results=0)

        with httpx.Client(timeout=self.timeout) as client:
            try:
                resp = client.get(
                    f"{self._base_url}/search/companies",
                    params={"q": query, "items_per_page": items_per_page},
                    auth=self._auth(),
                )
                resp.raise_for_status()
                data = resp.json()

                companies = [
                    CompanySearchItem.from_api_response(item)
                    for item in data.get("items", [])
                ]

                return CompanySearchResult(
                    query=query,
                    total_results=data.get("total_results", 0),
                    companies=companies,
                )
            except httpx.HTTPError:
                return CompanySearchResult(query=query, total_results=0)

    def get_company(self, company_number: str) -> CompanyRecord | None:
        """Fetch a company by number, including officers.

        Args:
            company_number: 8-character company number (e.g. "00445790").

        Returns:
            CompanyRecord or None if not found.
        """
        if not self.is_configured():
            return None

        company_number = company_number.upper().zfill(8)

        with httpx.Client(timeout=self.timeout) as client:
            try:
                resp = client.get(
                    f"{self._base_url}/company/{company_number}",
                    auth=self._auth(),
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                company_data = resp.json()

                # Fetch officers
                officers_data: list = []
                try:
                    officers_resp = client.get(
                        f"{self._base_url}/company/{company_number}/officers",
                        auth=self._auth(),
                    )
                    if officers_resp.status_code == 200:
                        officers_data = officers_resp.json().get("items", [])
                except httpx.HTTPError:
                    pass  # Officers are optional

                return CompanyRecord.from_api_response(company_data, officers=officers_data)

            except httpx.HTTPError:
                return None

    def lookup(self, query: str) -> CompanyRecord | CompanySearchResult:
        """Smart lookup: company number → direct fetch, otherwise name search.

        Args:
            query: Company name or number.

        Returns:
            CompanyRecord for direct lookup, CompanySearchResult for name search.
        """
        if _looks_like_company_number(query):
            result = self.get_company(query)
            if result is not None:
                return result
            # Fall through to search if number not found
        return self.search(query)


def _looks_like_company_number(query: str) -> bool:
    """Check if query looks like a Companies House number (e.g. '00445790', 'SC123456')."""
    q = query.strip()
    if q.isdigit():
        return True
    if len(q) == 8 and q[:2].isalpha() and q[2:].isdigit():
        return True  # e.g. "SC123456"
    if len(q) <= 8 and q.lstrip("0").isdigit():
        return True
    return False
