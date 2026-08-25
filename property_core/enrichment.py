"""Comp enrichment: attach EPC floor-area data to PPD transactions.

One summary search per distinct postcode, then a single certificate fetch for
each comp whose address uniquely identifies a candidate. Ambiguous comps are
left un-enriched rather than attached to a neighbouring property's certificate.
"""

from __future__ import annotations

import asyncio
import logging
from statistics import median
from typing import Any, Dict, List, Optional

from property_core.epc.errors import EPCAmbiguousMatchError
from property_core.epc.selection import select_candidate
from property_core.epc_client import EPCClient
from property_core.models.epc import EPCData
from property_core.models.ppd import PPDCompsResponse, PPDTransaction

_log = logging.getLogger(__name__)

# Conversion factor
_SQM_TO_SQFT = 10.7639


def _build_address(comp: PPDTransaction) -> str:
    """Build a matchable address string from PPD transaction fields."""
    parts: list[str] = []
    if comp.saon:
        parts.append(str(comp.saon))
    if comp.paon:
        parts.append(str(comp.paon))
    if comp.street:
        parts.append(str(comp.street))
    return " ".join(parts)


async def enrich_comps_with_epc(
    comps: List[PPDTransaction],
    epc_client: Optional[EPCClient] = None,
    *,
    min_score: int = 30,
    max_concurrent: int = 5,
) -> List[PPDTransaction]:
    """Enrich PPD comparables with EPC data (floor area, rating, age).

    Groups comps by postcode, fetches all EPC certs per unique postcode
    (one summary search each), selects a unique candidate per comp, then
    fetches only that certificate to attach:
      - epc_floor_area_sqm / epc_floor_area_sqft
      - price_per_sqm / price_per_sqft
      - epc_rating / epc_score / epc_construction_age / epc_built_form
      - epc_match (full normalized cert dict)
      - epc_match_score / epc_match_method (100 only for UPRN or exact address)

    Args:
        comps: List of PPDTransaction objects.
        epc_client: Configured EPCClient instance. If None, creates one internally.
        min_score: Retained for signature compatibility only; it has no effect.
            Selection accepts identity evidence alone (exact UPRN or exact
            normalized address), so there is no score to threshold.
        max_concurrent: Max concurrent EPC API calls (rate limiting).

    Returns:
        Same list of PPDTransaction objects with EPC fields populated (None if no match found).
    """
    if epc_client is None:
        epc_client = EPCClient()
    if not epc_client.is_configured():
        return comps

    # Group comps by postcode
    postcode_groups: Dict[str, List[int]] = {}
    for idx, comp in enumerate(comps):
        pc = comp.postcode or ""
        if pc:
            postcode_groups.setdefault(pc, []).append(idx)

    # One summary search per DISTINCT postcode. No certificate fan-out here:
    # details are fetched later, only for a uniquely selected candidate.
    semaphore = asyncio.Semaphore(max_concurrent)
    postcode_pages: Dict[str, Any] = {}

    async def _fetch_postcode(postcode: str) -> None:
        async with semaphore:
            postcode_pages[postcode] = await epc_client.search_summaries(postcode)

    # return_exceptions=True is load-bearing: EPC lookups now raise on upstream
    # failure, and enrichment is a best-effort augmentation of comps. Without
    # this, one failing postcode would discard every successfully-fetched
    # postcode in the batch AND propagate out of the comps request entirely.
    # Failed postcodes are simply left un-enriched.
    results = await asyncio.gather(
        *[_fetch_postcode(pc) for pc in postcode_groups.keys()],
        return_exceptions=True,
    )
    failed = [
        (pc, exc)
        for pc, exc in zip(postcode_groups.keys(), results)
        if isinstance(exc, BaseException)
    ]
    if failed:
        _log.warning(
            "EPC enrichment degraded: %d of %d postcodes could not be fetched (%s)",
            len(failed),
            len(postcode_groups),
            "; ".join(f"{pc}: {type(exc).__name__}" for pc, exc in failed[:3]),
        )

    # Select a unique candidate per comp from the summaries, then fetch ONLY
    # that certificate. Ambiguity leaves the comp un-enriched rather than
    # attaching a neighbouring property's EPC.
    cert_cache: Dict[str, Any] = {}
    ambiguous = 0

    for postcode, indices in postcode_groups.items():
        page = postcode_pages.get(postcode)
        rows = getattr(page, "results", None) or []
        if not rows:
            continue

        for idx in indices:
            comp = comps[idx]
            address = _build_address(comp)
            if not address:
                continue

            try:
                selected = select_candidate(rows, address=address)
            except EPCAmbiguousMatchError:
                ambiguous += 1
                continue

            cert_no = selected.row.certificate_number
            if cert_no not in cert_cache:
                try:
                    cert_cache[cert_no] = await epc_client.get_certificate(cert_no)
                except Exception as exc:  # noqa: BLE001 - best-effort augmentation
                    _log.warning("EPC certificate %s unavailable: %s", cert_no, exc)
                    cert_cache[cert_no] = None
            match = cert_cache[cert_no]
            if match is not None:
                # Always 100: selection accepts nothing but identity evidence.
                # Kept as a field read rather than a literal so a future
                # confidence tier cannot silently be reported as certainty.
                match_score = selected.confidence
                comp.epc_match_method = selected.method
                floor_sqm = match.floor_area
                price = comp.price

                comp.epc_match = match.model_dump()
                comp.epc_match_score = match_score
                comp.epc_floor_area_sqm = floor_sqm
                comp.epc_floor_area_sqft = (
                    round(floor_sqm * _SQM_TO_SQFT) if floor_sqm else None
                )
                comp.epc_rating = match.rating
                comp.epc_score = match.score
                comp.epc_construction_age = match.construction_age
                comp.epc_built_form = match.built_form

                if floor_sqm and price:
                    comp.price_per_sqm = round(price / floor_sqm)
                    comp.price_per_sqft = round(
                        price / (floor_sqm * _SQM_TO_SQFT)
                    )
                else:
                    comp.price_per_sqm = None
                    comp.price_per_sqft = None

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
        round(matched / len(comps.transactions) * 100) if comps.transactions else None
    )
    return comps
