"""Domain models for property_core."""

from property_core.models.epc import EPCData
from property_core.models.planning import (
    Council,
    CouncilSummary,
    LocalAuthority,
    SearchUrls,
)
from property_core.models.postcode import PostcodeResult
from property_core.models.ppd import (
    PPDCompsQuery,
    PPDCompsResponse,
    PPDTransaction,
    PPDTransactionRecord,
    SubjectProperty,
)
from property_core.models.report import (
    CurrentMarket,
    DataSource,
    EnergyPerformance,
    MarketAnalysis,
    PropertyReport,
    RentalAnalysis,
    SaleHistory,
    SaleRecord,
)
from property_core.models.rightmove import RightmoveListingDetail, RightmoveListing

__all__ = [
    "Council",
    "CouncilSummary",
    "CurrentMarket",
    "DataSource",
    "EPCData",
    "EnergyPerformance",
    "LocalAuthority",
    "MarketAnalysis",
    "PPDCompsQuery",
    "PPDCompsResponse",
    "PPDTransaction",
    "PPDTransactionRecord",
    "PostcodeResult",
    "PropertyReport",
    "RentalAnalysis",
    "RightmoveListing",
    "RightmoveListingDetail",
    "SaleHistory",
    "SaleRecord",
    "SearchUrls",
    "SubjectProperty",
]
