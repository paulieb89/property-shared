"""Domain models for Property Reports."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class SaleRecord(BaseModel):
    """A single property transaction."""
    price: int
    date: str
    property_type: Optional[str] = None
    new_build: Optional[bool] = None


class SaleHistory(BaseModel):
    """Sale history for the subject property."""
    address: str
    transactions: List[SaleRecord] = Field(default_factory=list)
    last_sale: Optional[SaleRecord] = None
    total_transactions: int = 0


class MarketAnalysis(BaseModel):
    """Area market analysis from comparable sales."""
    postcode_sector: str  # e.g., "SW1A 1"
    search_radius: str  # "postcode", "sector", "district"
    period_months: int
    transaction_count: int
    median_price: Optional[int] = None
    mean_price: Optional[int] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    thin_market: bool = False
    price_vs_median: Optional[str] = None  # "above", "below", "at"
    price_difference_pct: Optional[float] = None


class EnergyPerformance(BaseModel):
    """EPC data for the property."""
    rating: str  # A-G
    score: int  # 1-100
    potential_rating: Optional[str] = None
    potential_score: Optional[int] = None
    floor_area_sqm: Optional[float] = None
    property_type: Optional[str] = None
    construction_age: Optional[str] = None
    # Annual costs
    heating_cost: Optional[int] = None
    hot_water_cost: Optional[int] = None
    lighting_cost: Optional[int] = None
    total_annual_cost: Optional[int] = None
    # Potential savings
    potential_heating_cost: Optional[int] = None
    potential_savings: Optional[int] = None
    # Certificate info
    inspection_date: Optional[str] = None
    certificate_hash: Optional[str] = None


class RentalAnalysis(BaseModel):
    """Rental market analysis for yield calculation."""
    search_radius_miles: float
    rental_listings_count: int
    average_rent_monthly: Optional[int] = None
    median_rent_monthly: Optional[int] = None
    rent_range_low: Optional[int] = None
    rent_range_high: Optional[int] = None
    # Yield calculation (if sale price known)
    estimated_annual_rent: Optional[int] = None
    gross_yield_pct: Optional[float] = None
    yield_assessment: Optional[str] = None  # "strong", "average", "weak"


class YieldAnalysis(BaseModel):
    """Combined sale + rental yield analysis for a postcode."""
    postcode: str
    median_sale_price: Optional[int] = None
    sale_count: int = 0
    median_monthly_rent: Optional[int] = None
    rental_count: int = 0
    gross_yield_pct: Optional[float] = None
    yield_assessment: Optional[str] = None  # "strong", "average", "weak"
    data_quality: Optional[str] = None
    thin_market: bool = True


class CurrentMarket(BaseModel):
    """Current sales market snapshot."""
    search_radius_miles: float
    for_sale_count: int
    average_asking_price: Optional[int] = None
    median_asking_price: Optional[int] = None
    asking_range_low: Optional[int] = None
    asking_range_high: Optional[int] = None


class DataSource(BaseModel):
    """Information about a data source used."""
    name: str
    available: bool
    error: Optional[str] = None
    records_found: int = 0


class PropertyReport(BaseModel):
    """Complete property intelligence report."""
    # Report metadata
    report_id: str
    generated_at: datetime
    query_address: str
    query_postcode: str

    # Core sections
    sale_history: Optional[SaleHistory] = None
    market_analysis: Optional[MarketAnalysis] = None
    energy_performance: Optional[EnergyPerformance] = None
    rental_analysis: Optional[RentalAnalysis] = None
    current_market: Optional[CurrentMarket] = None

    # Summary insights
    estimated_value_low: Optional[int] = None
    estimated_value_high: Optional[int] = None
    key_insights: List[str] = Field(default_factory=list)

    # Data source status
    sources: List[DataSource] = Field(default_factory=list)

    # Disclaimers
    disclaimer: str = (
        "This report is for informational purposes only and should not be "
        "relied upon as a formal valuation. Data is sourced from public records "
        "and may contain inaccuracies. Consult a qualified surveyor or valuer "
        "for professional advice."
    )
