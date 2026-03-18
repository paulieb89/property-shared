"""Block analysis service — find buildings with multiple flat sales.

Groups PPD transactions by building to identify blocks being sold off,
investor exits, and bulk-buy opportunities.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from property_core.models.block import BlockAnalysisResponse, BlockBuilding, BlockUnit
from property_core.ppd_service import PPDService


def analyze_blocks(
    postcode: str,
    months: int = 24,
    limit: int = 50,
    min_transactions: int = 2,
    search_level: str = "sector",
) -> BlockAnalysisResponse:
    """Find buildings with multiple flat sales in a postcode area.

    Args:
        postcode: UK postcode (e.g. "B1 1AA").
        months: Lookback period in months.
        limit: Target number of blocks to find (fetches 3x transactions).
        min_transactions: Minimum sales to qualify as an active block.
        search_level: Search granularity — "postcode", "sector", or "district".

    Returns:
        BlockAnalysisResponse with buildings sorted by transaction count.
    """
    service = PPDService()

    # Fetch more transactions than requested blocks to find groupings
    fetch_limit = min(limit * 3, 200)
    result = service.comps(
        postcode=postcode,
        months=months,
        limit=fetch_limit,
        search_level=search_level,
        property_type="F",  # Flats only
    )

    # Group transactions by building: (paon, street, postcode)
    buildings: dict[tuple, list] = defaultdict(list)
    for t in result.transactions:
        if not t.paon:
            continue
        key = (t.paon.upper(), (t.street or "").upper(), (t.postcode or "").upper())
        buildings[key].append(t)

    # Filter to buildings with enough transactions and build response
    blocks: list[BlockBuilding] = []
    for (paon, street, pc), txns in buildings.items():
        if len(txns) < min_transactions:
            continue

        prices = [t.price for t in txns if t.price is not None]
        dates = sorted(t.date for t in txns if t.date)
        new_builds = sum(1 for t in txns if t.new_build)

        date_range = None
        if dates:
            date_range = f"{dates[0]} to {dates[-1]}" if len(dates) > 1 else dates[0]

        blocks.append(BlockBuilding(
            building_name=txns[0].paon,
            street=txns[0].street,
            postcode=txns[0].postcode,
            transaction_count=len(txns),
            new_build_count=new_builds,
            avg_price=int(mean(prices)) if prices else None,
            min_price=min(prices) if prices else None,
            max_price=max(prices) if prices else None,
            total_value=sum(prices) if prices else None,
            date_range=date_range,
            transactions=[
                BlockUnit(
                    saon=t.saon,
                    price=t.price,
                    date=t.date,
                    new_build=t.new_build,
                )
                for t in txns
            ],
        ))

    # Sort by transaction count descending
    blocks.sort(key=lambda b: b.transaction_count, reverse=True)

    return BlockAnalysisResponse(
        postcode=postcode,
        search_level=search_level,
        months=months,
        blocks_found=len(blocks),
        blocks=blocks,
    )
