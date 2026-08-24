"""Measure token cost of EPC response shapes to inform the property_epc_search design.

Tests four candidate response shapes against a real postcode:
  1. current_summary   — existing area-mode (aggregated stats, no individual certs)
  2. full_list         — all certs, all fields, exclude_none=True
  3. slim_list         — all certs, key fields only (address/rating/floor_area/type/date/key)
  4. slim_list_capped  — slim_list capped at N certs

Run:
    uv run --env-file .env --extra dev python scripts/measure_epc_tokens.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from typing import Any

import tiktoken

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from property_core.epc_client import EPCClient
from property_core.models.epc import EPCData

# ----- postcodes to test (range of density) --------------------------------

POSTCODES = [
    "SW1A 1AA",   # dense central London
    "NG1 1AA",    # Nottingham city centre
    "M1 1AE",     # Manchester
]

CAPS = [10, 15, 20]

# Fields to keep for slim representation
SLIM_FIELDS = {"address", "rating", "floor_area", "property_type", "inspection_date", "lmk_key"}

# ---------------------------------------------------------------------------

enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(obj: Any) -> int:
    return len(enc.encode(json.dumps(obj, default=str)))


def _slim(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _slim(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_slim(i) for i in obj]
    return obj


def build_current_summary(postcode: str, certs: list[EPCData]) -> dict:
    """Mirrors the current area-mode response in app/mcp/server.py."""
    ratings = Counter(c.rating for c in certs if c.rating)
    types = Counter(c.property_type for c in certs if c.property_type)
    areas = [c.floor_area for c in certs if c.floor_area]
    return _slim({
        "postcode": postcode,
        "summary": {
            "count": len(certs),
            "rating_distribution": dict(sorted(ratings.items())),
            "property_type_breakdown": dict(sorted(types.items())),
            "floor_area_min": min(areas) if areas else None,
            "floor_area_max": max(areas) if areas else None,
            "floor_area_avg": round(sum(areas) / len(areas), 1) if areas else None,
        },
        "note": "Call property_epc again with a specific address for individual property details.",
    })


def build_full_list(certs: list[EPCData]) -> list[dict]:
    return _slim([c.model_dump(mode="json", exclude_none=True) for c in certs])


def build_slim_list(certs: list[EPCData], cap: int | None = None) -> list[dict]:
    subset = certs[:cap] if cap else certs
    result = []
    for c in subset:
        row = {k: v for k, v in c.model_dump(mode="json", exclude_none=True).items()
               if k in SLIM_FIELDS}
        result.append(row)
    return result


async def measure_postcode(postcode: str) -> None:
    client = EPCClient()
    if not client.is_configured():
        print(f"  [SKIP] EPC credentials not configured — set EPC_API_EMAIL / EPC_API_KEY")
        return

    print(f"\nFetching EPC certs for {postcode}...")
    certs = await client.search_all_by_postcode(postcode)
    if not certs:
        print(f"  No certs found for {postcode}")
        return

    print(f"  {len(certs)} certs returned from API")
    print()

    # ---- shape 1: current summary ----
    summary = build_current_summary(postcode, certs)
    t_summary = count_tokens(summary)
    print(f"  [1] current_summary        : {t_summary:>5} tokens")

    # ---- shape 2: full list (all fields) ----
    full = build_full_list(certs)
    t_full = count_tokens(full)
    print(f"  [2] full_list ({len(certs):>2} certs)   : {t_full:>5} tokens  ({t_full // len(certs)} tokens/cert avg)")

    # ---- shape 3: slim list (key fields, all certs) ----
    slim_all = build_slim_list(certs)
    t_slim_all = count_tokens(slim_all)
    print(f"  [3] slim_list ({len(certs):>2} certs)   : {t_slim_all:>5} tokens  ({t_slim_all // len(certs)} tokens/cert avg)")

    # ---- shape 4: slim list, capped ----
    for cap in CAPS:
        if cap >= len(certs):
            continue
        slim_cap = build_slim_list(certs, cap=cap)
        t_cap = count_tokens(slim_cap)
        print(f"  [4] slim_list (cap={cap:>2})      : {t_cap:>5} tokens")

    # ---- sample slim record ----
    print()
    print(f"  Sample slim record (first cert):")
    print(f"  {json.dumps(build_slim_list(certs[:1])[0], default=str)}")

    # ---- unique streets ----
    streets = set()
    for c in certs:
        if c.address:
            parts = c.address.split(",")
            street = ",".join(parts[1:]).strip() if len(parts) > 1 else parts[0].strip()
            streets.add(street)
    print(f"\n  Unique streets in postcode: {len(streets)}")
    for s in sorted(streets)[:5]:
        print(f"    - {s}")
    if len(streets) > 5:
        print(f"    ... and {len(streets) - 5} more")


async def main() -> None:
    print("=" * 60)
    print("EPC Response Shape Token Cost Comparison")
    print(f"Slim fields: {sorted(SLIM_FIELDS)}")
    print("=" * 60)

    for postcode in POSTCODES:
        print(f"\n{'='*60}")
        print(f"Postcode: {postcode}")
        print(f"{'='*60}")
        await measure_postcode(postcode)

    print("\n\nConclusion guide:")
    print("  < 200 tokens → safe to return full slim list always")
    print("  200–500 tokens → slim list with cap ~15 is reasonable")
    print("  > 500 tokens → cap tightly or add street filter")


if __name__ == "__main__":
    asyncio.run(main())
