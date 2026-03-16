"""Pure-Python core library for property tooling.

This package contains reusable domain logic with minimal assumptions (no FastAPI,
no database/redis). The API service in `app/` wraps this package.
"""

from property_core.address_matching import match_epc_address
from property_core.epc_client import EPCClient
from property_core.enrichment import compute_enriched_stats, enrich_comps_with_epc
from property_core.models.postcode import PostcodeResult
from property_core.planning_service import PlanningService
from property_core.postcode_client import PostcodeClient
from property_core.ppd_client import PricePaidDataClient
from property_core.ppd_service import PPDService
from property_core.rental_service import analyze_rentals
from property_core.report_service import PropertyReportService
from property_core.yield_service import calculate_yield
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listing, fetch_listings

__all__ = [
    "EPCClient",
    "PlanningService",
    "PostcodeClient",
    "PostcodeResult",
    "PPDService",
    "PricePaidDataClient",
    "PropertyReportService",
    "RightmoveLocationAPI",
    "analyze_rentals",
    "calculate_yield",
    "compute_enriched_stats",
    "enrich_comps_with_epc",
    "fetch_listing",
    "fetch_listings",
    "match_epc_address",
]
