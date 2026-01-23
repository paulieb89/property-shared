"""Service wrapper for planning-related operations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from property_core.postcode_client import PostcodeClient


# Search URL patterns for different council systems
SEARCH_URL_PATTERNS: Dict[str, Dict[str, str]] = {
    "idox": {
        "postcode": "{base_url}search.do?action=simple&searchType=Application&PostCode={postcode}",
        "weekly_list": "{base_url}search.do?action=weeklyList&searchType=Application",
        "advanced": "{base_url}search.do?action=advanced&searchType=Application",
    },
    "lar": {
        "search_page": "{base_url}index.html?fa=search",
    },
    "agile": {
        "search_page": "{base_url}",
    },
    "northgate": {
        "search_page": "{base_url}GeneralSearch.aspx",
    },
    "ocella": {
        "search_page": "{base_url}",
    },
    "arcus": {
        "search_page": "{base_url}",
    },
}


def _build_search_url(council: Dict[str, Any], postcode: str) -> Dict[str, Any]:
    """Build search URLs for a council based on its system type."""
    system = council.get("system", "").lower()
    base_url = council.get("base_url", "")
    search_url = council.get("search_url")
    postcode_clean = postcode.replace(" ", "").upper()

    result: Dict[str, Any] = {
        "search_page": search_url or base_url,
        "direct_search": None,
        "instructions": None,
    }

    patterns = SEARCH_URL_PATTERNS.get(system, {})

    if system == "idox":
        # Idox supports direct postcode search via URL
        if "postcode" in patterns:
            result["direct_search"] = patterns["postcode"].format(
                base_url=base_url,
                postcode=quote(postcode_clean),
            )
            result["instructions"] = (
                "Use the direct_search URL to search by postcode. "
                "Results will show planning applications in this area."
            )
    elif system == "lar":
        result["search_page"] = patterns.get("search_page", "").format(base_url=base_url) or base_url
        result["instructions"] = (
            f"Visit the search page and enter postcode '{postcode}' in the "
            "SiteAddress[postcode] field, then click Search."
        )
    elif system == "agile":
        result["search_page"] = patterns.get("search_page", "").format(base_url=base_url) or base_url
        result["instructions"] = (
            f"Visit the search page and enter postcode '{postcode}' in the "
            "Quick Search field, then click Quick search."
        )
    elif system == "northgate":
        result["search_page"] = patterns.get("search_page", "").format(base_url=base_url) or base_url
        result["instructions"] = (
            f"Visit the search page and enter postcode '{postcode}' in the search form. "
            "Northgate systems require form submission."
        )
    elif system == "ocella":
        result["instructions"] = (
            f"Visit the search page and enter postcode '{postcode}' in the search form."
        )
    elif system == "arcus":
        result["instructions"] = (
            f"Visit the search page and use the location filter with postcode '{postcode}'."
        )
    else:
        result["instructions"] = (
            f"Visit the planning portal and search for postcode '{postcode}'."
        )

    return result


def _normalize_name(name: str) -> str:
    """Normalize council name for matching."""
    # Lowercase, remove common suffixes, normalize whitespace
    name = name.lower().strip()
    # Remove common suffixes
    suffixes = [
        "city council",
        "borough council",
        "district council",
        "county council",
        "council",
        "london borough of",
        "royal borough of",
        "city of",
        "metropolitan borough of",
    ]
    for suffix in suffixes:
        name = name.replace(suffix, "")
    # Normalize whitespace and punctuation
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _name_to_code(name: str) -> str:
    """Convert council name to likely code format."""
    normalized = _normalize_name(name)
    # Replace spaces with hyphens
    return normalized.replace(" ", "-")


class PlanningService:
    """High-level planning operations used by the API layer."""

    def __init__(
        self,
        postcode_client: Optional[PostcodeClient] = None,
        councils_path: Optional[Path] = None,
    ):
        self.postcode_client = postcode_client or PostcodeClient()
        self.councils_path = councils_path or (
            Path(__file__).parent.parent.parent / "property_core" / "planning_councils.json"
        )
        self._councils_cache: Optional[Dict[str, Any]] = None

    def _load_councils(self) -> Dict[str, Any]:
        """Load councils database."""
        if self._councils_cache is not None:
            return self._councils_cache

        if not self.councils_path.exists():
            self._councils_cache = {"councils": [], "untested": [], "systems": {}}
            return self._councils_cache

        with open(self.councils_path) as f:
            self._councils_cache = json.load(f)
        return self._councils_cache

    def _get_all_councils(self) -> List[Dict[str, Any]]:
        """Get all councils (verified and untested)."""
        data = self._load_councils()
        return data.get("councils", []) + data.get("untested", [])

    def _match_council(self, local_authority_name: str) -> Optional[Dict[str, Any]]:
        """Try to match a local authority name to our councils database.

        Matching priority:
        1. Exact match on postcodes_io_name field (most reliable)
        2. Exact match on council code
        3. Normalized name match
        4. Partial name match (fallback)
        """
        if not local_authority_name:
            return None

        councils = self._get_all_councils()
        la_normalized = _normalize_name(local_authority_name)
        la_code = _name_to_code(local_authority_name)

        # Try exact postcodes_io_name match first (most reliable)
        for council in councils:
            if council.get("postcodes_io_name") == local_authority_name:
                return council

        # Try exact code match
        for council in councils:
            if council.get("code") == la_code:
                return council

        # Try normalized name match
        for council in councils:
            council_normalized = _normalize_name(council.get("name", ""))
            if council_normalized == la_normalized:
                return council

        # Try partial match (contains) - fallback
        for council in councils:
            council_normalized = _normalize_name(council.get("name", ""))
            if la_normalized in council_normalized or council_normalized in la_normalized:
                return council

        return None

    def council_for_postcode(
        self, postcode: str, *, include_raw: bool = False
    ) -> Dict[str, Any]:
        """Look up the planning council for a UK postcode.

        Returns:
            Dict with postcode info and matched council (or None if not in database).
            When include_raw=True, includes full postcodes.io data under 'postcode_data'.
        """
        # Look up postcode
        la_info = self.postcode_client.get_local_authority(
            postcode, include_raw=include_raw
        )
        if not la_info:
            return {
                "postcode": postcode,
                "error": "Postcode not found",
                "local_authority": None,
                "council": None,
            }

        local_authority_name = la_info.get("name")

        # Try to match to our councils database
        council = self._match_council(local_authority_name)

        result: Dict[str, Any] = {
            "postcode": la_info.get("postcode", postcode),
            "local_authority": {
                "name": local_authority_name,
                "code": la_info.get("code"),
                "region": la_info.get("region"),
                "country": la_info.get("country"),
            },
            "council": council,
            "council_found": council is not None,
        }
        if include_raw:
            result["postcode_data"] = la_info.get("raw")
        return result

    def get_council(self, code: str) -> Optional[Dict[str, Any]]:
        """Get a council by code."""
        for council in self._get_all_councils():
            if council.get("code") == code:
                return council
        return None

    def list_councils(self) -> Dict[str, Any]:
        """List all councils."""
        data = self._load_councils()
        return {
            "verified_count": len(data.get("councils", [])),
            "untested_count": len(data.get("untested", [])),
            "councils": data.get("councils", []),
            "untested": data.get("untested", []),
            "systems": data.get("systems", {}),
        }

    def search(self, postcode: str) -> Dict[str, Any]:
        """Search for planning applications by postcode.

        Returns the council info and search URLs. For Idox councils (most common),
        a direct search URL is provided. For other systems, instructions are given.

        Note: Actual scraping of search results requires residential IP.
        """
        # First, look up the council for this postcode
        council_result = self.council_for_postcode(postcode)

        if not council_result.get("council"):
            return {
                "postcode": council_result.get("postcode", postcode),
                "local_authority": council_result.get("local_authority"),
                "council_found": False,
                "error": "No planning portal found for this local authority",
                "search_urls": None,
            }

        council = council_result["council"]
        search_urls = _build_search_url(council, postcode)

        return {
            "postcode": council_result.get("postcode", postcode),
            "local_authority": council_result.get("local_authority"),
            "council_found": True,
            "council": {
                "name": council.get("name"),
                "code": council.get("code"),
                "system": council.get("system"),
                "status": council.get("status"),
            },
            "search_urls": search_urls,
            "note": "Planning portal scraping requires UK residential IP. Councils block datacenter IPs.",
        }
