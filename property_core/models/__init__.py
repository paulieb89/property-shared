"""Domain models for property_core."""

from property_core.models.epc import EPCData
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
    "CurrentMarket",
    "DataSource",
    "EPCData",
    "EnergyPerformance",
    "MarketAnalysis",
    "PPDCompsQuery",
    "PPDCompsResponse",
    "PPDTransaction",
    "PPDTransactionRecord",
    "PropertyReport",
    "RentalAnalysis",
    "RightmoveListing",
    "RightmoveListingDetail",
    "SaleHistory",
    "SaleRecord",
    "SubjectProperty",
]
