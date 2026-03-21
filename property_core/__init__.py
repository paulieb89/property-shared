"""Pure-Python core library for property tooling.

This package contains reusable domain logic with minimal assumptions (no FastAPI,
no database/redis). The API service in `app/` wraps this package.
"""

from property_core.address_matching import match_epc_address
from property_core.block_service import analyze_blocks
from property_core.interpret import (
    classify_data_quality,
    classify_price_position,
    classify_yield,
    estimate_value_range,
    generate_insights,
)
from property_core.companies_house_client import CompaniesHouseClient
from property_core.epc_client import EPCClient
from property_core.enrichment import compute_enriched_stats, enrich_comps_with_epc
from property_core.models.block import BlockAnalysisResponse, BlockBuilding
from property_core.models.companies_house import CompanyRecord, CompanySearchResult
from property_core.models.epc import EPCData
from property_core.models.postcode import PostcodeResult
from property_core.models.ppd import PPDCompsResponse, PPDTransaction, PPDTransactionRecord
from property_core.models.report import PropertyReport, RentalAnalysis, YieldAnalysis
from property_core.models.rightmove import RightmoveListing, RightmoveListingDetail
from property_core.planning_service import PlanningService
from property_core.postcode_client import PostcodeClient
from property_core.ppd_client import PricePaidDataClient
from property_core.ppd_service import PPDService
from property_core.rental_service import analyze_rentals
from property_core.report_service import PropertyReportService
from property_core.stamp_duty import StampDutyResult, calculate_stamp_duty
from property_core.yield_service import calculate_yield
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listing, fetch_listings

__all__ = [
    # Services
    "CompaniesHouseClient",
    "EPCClient",
    "PlanningService",
    "PostcodeClient",
    "PPDService",
    "PricePaidDataClient",
    "PropertyReportService",
    "RightmoveLocationAPI",
    # Functions
    "analyze_blocks",
    "analyze_rentals",
    "calculate_stamp_duty",
    "calculate_yield",
    "classify_data_quality",
    "classify_price_position",
    "classify_yield",
    "compute_enriched_stats",
    "enrich_comps_with_epc",
    "estimate_value_range",
    "fetch_listing",
    "fetch_listings",
    "generate_insights",
    "match_epc_address",
    # Models
    "BlockAnalysisResponse",
    "BlockBuilding",
    "CompanyRecord",
    "CompanySearchResult",
    "EPCData",
    "PostcodeResult",
    "PPDCompsResponse",
    "PPDTransaction",
    "PPDTransactionRecord",
    "PropertyReport",
    "RentalAnalysis",
    "RightmoveListing",
    "RightmoveListingDetail",
    "StampDutyResult",
    "YieldAnalysis",
]
