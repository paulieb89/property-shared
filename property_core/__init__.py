"""Pure-Python core library for property tooling.

This package contains reusable domain logic with minimal assumptions (no FastAPI,
no database/redis). The API service in `app/` wraps this package.
"""

from property_core.epc_client import EPCClient
from property_core.enrichment import enrich_comps_with_epc
from property_core.planning_service import PlanningService
from property_core.postcode_client import PostcodeClient
from property_core.ppd_client import PricePaidDataClient
from property_core.ppd_service import PPDService
from property_core.report_service import PropertyReportService
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listing, fetch_listings

__all__ = [
    "EPCClient",
    "PlanningService",
    "PostcodeClient",
    "PPDService",
    "PricePaidDataClient",
    "PropertyReportService",
    "RightmoveLocationAPI",
    "enrich_comps_with_epc",
    "fetch_listing",
    "fetch_listings",
]
