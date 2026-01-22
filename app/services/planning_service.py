"""Service wrapper for planning-related operations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from property_core.postcode_client import PostcodeClient


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
        """Try to match a local authority name to our councils database."""
        if not local_authority_name:
            return None

        councils = self._get_all_councils()
        la_normalized = _normalize_name(local_authority_name)
        la_code = _name_to_code(local_authority_name)

        # Try exact code match first
        for council in councils:
            if council.get("code") == la_code:
                return council

        # Try normalized name match
        for council in councils:
            council_normalized = _normalize_name(council.get("name", ""))
            if council_normalized == la_normalized:
                return council

        # Try partial match (contains)
        for council in councils:
            council_normalized = _normalize_name(council.get("name", ""))
            if la_normalized in council_normalized or council_normalized in la_normalized:
                return council

        return None

    def council_for_postcode(self, postcode: str) -> Dict[str, Any]:
        """Look up the planning council for a UK postcode.

        Returns:
            Dict with postcode info and matched council (or None if not in database).
        """
        # Look up postcode
        la_info = self.postcode_client.get_local_authority(postcode)
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

        return {
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
