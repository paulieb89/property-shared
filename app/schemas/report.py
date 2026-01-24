"""API schemas for Property Reports.

All report models live in property_core.models.report.
PropertyReport is both the domain model and the API response.
"""

# Re-export all report models from core
from property_core.models.report import (  # noqa: F401
    CurrentMarket,
    DataSource,
    EnergyPerformance,
    MarketAnalysis,
    PropertyReport,
    RentalAnalysis,
    SaleHistory,
    SaleRecord,
)
