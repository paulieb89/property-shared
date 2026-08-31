"""Dump the raw address dict from a Rightmove PAGE_MODEL to check for UPRN.

Usage:
    uv run python scripts/rightmove_address_dump.py <property_url_or_id>

Example:
    uv run python scripts/rightmove_address_dump.py 123456789
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))

from property_core.rightmove_scraper import (
    DEFAULT_HEADERS,
    _extract_page_model,
    _normalize_property_url,
)
import requests


def dump(url_or_id: str) -> None:
    url = _normalize_property_url(url_or_id)
    print(f"Fetching: {url}\n")

    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=15)
    resp.raise_for_status()

    data = _extract_page_model(resp.text)

    address_info = data.get("address") or {}
    location = data.get("location") or {}

    print("=== address dict ===")
    print(json.dumps(address_info, indent=2, default=str))

    print("\n=== location dict ===")
    print(json.dumps(location, indent=2, default=str))

    # Also scan top-level keys for anything UPRN-shaped
    print("\n=== top-level propertyData keys ===")
    print(list(data.keys()))

    print("\n=== UPRN scan (any key containing 'uprn') ===")
    def find_uprn(obj: object, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else k
                if "uprn" in k.lower():
                    print(f"  {p}: {v!r}")
                find_uprn(v, p)
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:5]):  # cap list scan to first 5 items
                find_uprn(v, f"{path}[{i}]")

    find_uprn(data)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    dump(sys.argv[1])
