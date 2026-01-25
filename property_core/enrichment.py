"""Comp enrichment: attach EPC floor-area data to PPD transactions.

Groups comparables by postcode, fetches EPC certificates in batch (one API call
per unique postcode), then fuzzy-matches addresses to attach floor_area and
derived price-per-sqft metrics.
"""

from __future__ import annotations

import asyncio
from statistics import median
from typing import Any, Dict, List, Optional

from property_core.epc_client import EPCClient
from property_core.models.ppd import PPDCompsResponse

# Conversion factor
_SQM_TO_SQFT = 10.7639


def _build_address(comp: Dict[str, Any]) -> str:
    """Build a matchable address string from PPD transaction fields."""
    parts: list[str] = []
    saon = comp.get("saon")
    paon = comp.get("paon")
    street = comp.get("street")
    if saon:
        parts.append(str(saon))
    if paon:
        parts.append(str(paon))
    if street:
        parts.append(str(street))
    return " ".join(parts)


async def enrich_comps_with_epc(
    comps: List[Dict[str, Any]],
    epc_client: Optional[EPCClient] = None,
    *,
    min_score: int = 30,
    max_concurrent: int = 5,
) -> List[Dict[str, Any]]:
    """Enrich PPD comparables with EPC data (floor area, rating, age).

    Groups comps by postcode, fetches all EPC certs per unique postcode
    (one API call each), then fuzzy-matches each comp's address to attach:
      - epc_floor_area_sqm / epc_floor_area_sqft
      - price_per_sqm / price_per_sqft
      - epc_rating / epc_score / epc_construction_age / epc_built_form
      - epc_match (full normalized cert dict)
      - epc_match_score (fuzzy confidence 0-100)

    Args:
        comps: List of PPD transaction dicts (must have postcode, paon, street, price).
        epc_client: Configured EPCClient instance. If None, creates one internally.
        min_score: Minimum fuzzy-match score to accept an EPC match.
        max_concurrent: Max concurrent EPC API calls (rate limiting).

    Returns:
        Same list of dicts with EPC fields added (None if no match found).
    """
    if epc_client is None:
        epc_client = EPCClient()
    if not epc_client.is_configured():
        return comps

    # Group comps by postcode
    postcode_groups: Dict[str, List[int]] = {}
    for idx, comp in enumerate(comps):
        pc = comp.get("postcode", "")
        if pc:
            postcode_groups.setdefault(pc, []).append(idx)

    # Fetch EPC certs per postcode with concurrency limit
    semaphore = asyncio.Semaphore(max_concurrent)
    postcode_certs: Dict[str, List[Dict[str, Any]]] = {}

    async def _fetch_postcode(postcode: str) -> None:
        async with semaphore:
            certs = await epc_client.search_all_by_postcode(postcode)
            postcode_certs[postcode] = certs

    await asyncio.gather(
        *[_fetch_postcode(pc) for pc in postcode_groups.keys()]
    )

    # Match each comp against its postcode's certs
    for postcode, indices in postcode_groups.items():
        certs = postcode_certs.get(postcode, [])
        if not certs:
            continue

        for idx in indices:
            comp = comps[idx]
            address = _build_address(comp)
            if not address:
                continue

            result = epc_client.match_address(certs, address, min_score=min_score)
            if result:
                match, match_score = result
                floor_sqm = match.get("floor_area")
                price = comp.get("price")

                comp["epc_match"] = match
                comp["epc_match_score"] = match_score
                comp["epc_floor_area_sqm"] = floor_sqm
                comp["epc_floor_area_sqft"] = (
                    round(floor_sqm * _SQM_TO_SQFT) if floor_sqm else None
                )
                comp["epc_rating"] = match.get("rating")
                comp["epc_score"] = match.get("score")
                comp["epc_construction_age"] = match.get("construction_age")
                comp["epc_built_form"] = match.get("built_form")

                if floor_sqm and price:
                    comp["price_per_sqm"] = round(price / floor_sqm)
                    comp["price_per_sqft"] = round(
                        price / (floor_sqm * _SQM_TO_SQFT)
                    )
                else:
                    comp["price_per_sqm"] = None
                    comp["price_per_sqft"] = None

    return comps


def compute_enriched_stats(comps: PPDCompsResponse) -> PPDCompsResponse:
    """Compute aggregate stats after EPC enrichment.

    Intended to be called after callers have applied enrichment to
    ``comps.transactions`` (price_per_sqft, epc_match, etc.).
    """
    prices_per_sqft = [
        t.price_per_sqft for t in comps.transactions if t.price_per_sqft is not None
    ]
    matched = sum(1 for t in comps.transactions if t.epc_match is not None)

    comps.median_price_per_sqft = int(median(prices_per_sqft)) if prices_per_sqft else None
    comps.epc_match_rate = (
        matched / len(comps.transactions) if comps.transactions else None
    )
    return comps
