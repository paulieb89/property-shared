"""Property Report Service - aggregates multiple data sources into a comprehensive report.

Async service. Wraps sync calls (PPDService, Rightmove) in asyncio.to_thread().
Uses core clients directly (no FastAPI dependencies).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime
from statistics import median as stat_median
from typing import Any, Dict, List, Optional

from property_core.address_matching import parse_address
from property_core.epc_client import EPCClient
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
from property_core.ppd_service import PPDService
from property_core.rental_service import _calculate_yield, analyze_rentals
from property_core.rightmove_location import RightmoveLocationAPI
from property_core.rightmove_scraper import fetch_listings




def _get_postcode_sector(postcode: str) -> str:
    """Extract sector from postcode (e.g., 'SW1A 1' from 'SW1A 1AA')."""
    parts = postcode.split()
    if len(parts) == 2:
        return f"{parts[0]} {parts[1][0]}"
    return postcode


class PropertyReportService:
    """Generates comprehensive property reports by aggregating multiple data sources.

    Async service. Constructor takes optional config with env-var fallbacks.
    """

    def __init__(
        self,
        ppd_service: Optional[PPDService] = None,
        epc_client: Optional[EPCClient] = None,
        rightmove_location: Optional[RightmoveLocationAPI] = None,
        *,
        epc_email: Optional[str] = None,
        epc_api_key: Optional[str] = None,
        rightmove_delay: float = 0.6,
    ):
        self.ppd = ppd_service or PPDService()
        self.epc = epc_client or EPCClient(
            email=epc_email or os.environ.get("EPC_API_EMAIL"),
            api_key=epc_api_key or os.environ.get("EPC_API_KEY"),
        )
        self.rightmove = rightmove_location or RightmoveLocationAPI(
            rate_limit_delay=rightmove_delay,
        )
        self._rightmove_delay = rightmove_delay

    async def generate_report(
        self,
        address_query: str,
        *,
        include_rentals: bool = True,
        include_sales_market: bool = True,
        ppd_months: int = 24,
        search_radius: float = 0.5,
    ) -> PropertyReport:
        """Generate a comprehensive property report.

        Data aggregation orchestrator combining PPD, EPC, Rightmove, and rental
        data. Returns structured data only — no interpretation labels or insight
        text. Use property_core.interpret helpers for presentation.

        Args:
            address_query: Combined address, e.g., "10 Downing Street, SW1A 2AA"
            include_rentals: Include rental market analysis
            include_sales_market: Include current sales market
            ppd_months: Lookback period for PPD comparables
            search_radius: Radius in miles for Rightmove searches

        Returns:
            PropertyReport with all available data
        """
        # Parse address
        postcode, street_address = parse_address(address_query)
        if not postcode:
            raise ValueError(
                f"Could not parse postcode from: {address_query}. "
                "Use format: '10 Downing Street, SW1A 2AA'"
            )

        report_id = str(uuid.uuid4())[:8]
        sources: List[DataSource] = []

        # Fetch data in parallel where possible
        ppd_task = asyncio.create_task(
            self._fetch_ppd_data(postcode, street_address, ppd_months)
        )
        epc_task = asyncio.create_task(
            self._fetch_epc_data(postcode, street_address)
        )

        # Wait for core data
        ppd_result = await ppd_task
        epc_result = await epc_task

        # Process PPD results
        sale_history = None
        market_analysis = None
        if ppd_result["success"]:
            sale_history = ppd_result.get("sale_history")
            market_analysis = ppd_result.get("market_analysis")
            sources.append(DataSource(
                name="Land Registry PPD",
                available=True,
                records_found=ppd_result.get("transaction_count", 0),
            ))
        else:
            sources.append(DataSource(
                name="Land Registry PPD",
                available=False,
                error=ppd_result.get("error"),
            ))

        # Process EPC results
        energy_performance = None
        if epc_result["success"]:
            energy_performance = epc_result.get("energy_performance")
            sources.append(DataSource(
                name="EPC Register",
                available=True,
                records_found=1 if energy_performance else 0,
            ))
        else:
            sources.append(DataSource(
                name="EPC Register",
                available=epc_result.get("configured", False),
                error=epc_result.get("error"),
            ))

        # Fetch Rightmove data (if requested)
        rental_analysis = None
        current_market = None

        if include_rentals or include_sales_market:
            rightmove_tasks = []
            if include_rentals:
                rightmove_tasks.append(
                    ("rentals", self._fetch_rental_data(postcode, search_radius))
                )
            if include_sales_market:
                rightmove_tasks.append(
                    ("sales", self._fetch_sales_market(postcode, search_radius))
                )

            for name, task in rightmove_tasks:
                result = await task
                if name == "rentals":
                    if result["success"]:
                        rental_analysis = result.get("rental_analysis")
                        sources.append(DataSource(
                            name="Rightmove Rentals",
                            available=True,
                            records_found=result.get("listing_count", 0),
                        ))
                        # Calculate yield if we have sale price
                        if rental_analysis and sale_history and sale_history.last_sale:
                            _calculate_yield(
                                rental_analysis, sale_history.last_sale.price
                            )
                    else:
                        sources.append(DataSource(
                            name="Rightmove Rentals",
                            available=False,
                            error=result.get("error"),
                        ))
                elif name == "sales":
                    if result["success"]:
                        current_market = result.get("current_market")
                        sources.append(DataSource(
                            name="Rightmove Sales",
                            available=True,
                            records_found=result.get("listing_count", 0),
                        ))
                    else:
                        sources.append(DataSource(
                            name="Rightmove Sales",
                            available=False,
                            error=result.get("error"),
                        ))

        return PropertyReport(
            report_id=report_id,
            generated_at=datetime.utcnow(),
            query_address=street_address or "",
            query_postcode=postcode,
            sale_history=sale_history,
            market_analysis=market_analysis,
            energy_performance=energy_performance,
            rental_analysis=rental_analysis,
            current_market=current_market,
            sources=sources,
        )

    async def _fetch_ppd_data(
        self, postcode: str, address: Optional[str], months: int,
    ) -> Dict[str, Any]:
        """Fetch PPD data (runs sync code in thread)."""
        try:
            result = await asyncio.to_thread(
                self.ppd.comps,
                postcode=postcode,
                property_type=None,
                months=months,
                limit=50,
                search_level="sector",
                address=address,
            )

            sale_history = None
            if result.subject_property:
                sp = result.subject_property
                sale_history = SaleHistory(
                    address=sp.address,
                    transactions=[
                        SaleRecord(
                            price=t.price,
                            date=t.date,
                            property_type=t.property_type,
                            new_build=t.new_build,
                        )
                        for t in sp.transaction_history
                    ],
                    last_sale=(
                        SaleRecord(
                            price=sp.last_sale.price,
                            date=sp.last_sale.date,
                            property_type=sp.last_sale.property_type,
                            new_build=sp.last_sale.new_build,
                        )
                        if sp.last_sale
                        else None
                    ),
                    total_transactions=sp.transaction_count,
                )

            market_analysis = MarketAnalysis(
                postcode_sector=_get_postcode_sector(postcode),
                search_radius="sector",
                period_months=months,
                transaction_count=result.count,
                median_price=result.median,
                mean_price=result.mean,
                min_price=result.min,
                max_price=result.max,
                thin_market=result.thin_market,
            )

            # Calculate price vs median (raw number only)
            if sale_history and sale_history.last_sale and market_analysis.median_price:
                last_price = sale_history.last_sale.price
                median_price = market_analysis.median_price
                diff_pct = ((last_price - median_price) / median_price) * 100
                market_analysis.price_difference_pct = round(diff_pct, 1)

            return {
                "success": True,
                "sale_history": sale_history,
                "market_analysis": market_analysis,
                "transaction_count": result.count,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _fetch_epc_data(
        self, postcode: str, address: Optional[str]
    ) -> Dict[str, Any]:
        """Fetch EPC data."""
        if not self.epc.is_configured():
            return {
                "success": False,
                "configured": False,
                "error": "EPC service not configured",
            }

        try:
            result = await self.epc.search_by_postcode(postcode, address=address)
            if not result:
                return {
                    "success": False,
                    "configured": True,
                    "error": "No EPC found",
                }

            total_cost = None
            heating = result.heating_cost_current
            hot_water = result.hot_water_cost_current
            lighting = result.lighting_cost_current
            if heating or hot_water or lighting:
                total_cost = (heating or 0) + (hot_water or 0) + (lighting or 0)

            potential_savings = None
            if heating and result.heating_cost_potential:
                potential_savings = heating - result.heating_cost_potential

            energy = EnergyPerformance(
                rating=result.rating or "?",
                score=result.score or 0,
                potential_rating=result.potential_rating,
                potential_score=result.potential_score,
                floor_area_sqm=result.floor_area,
                property_type=result.property_type,
                construction_age=result.construction_age,
                heating_cost=heating,
                hot_water_cost=hot_water,
                lighting_cost=lighting,
                total_annual_cost=total_cost,
                potential_heating_cost=result.heating_cost_potential,
                potential_savings=potential_savings,
                inspection_date=result.inspection_date,
                certificate_hash=result.lmk_key,
            )

            return {"success": True, "energy_performance": energy}
        except Exception as e:
            return {"success": False, "configured": True, "error": str(e)}

    async def _fetch_rental_data(
        self, postcode: str, radius: float
    ) -> Dict[str, Any]:
        """Fetch rental market data using the standalone rental analysis module."""
        try:
            rental = await analyze_rentals(
                postcode,
                radius=radius,
                rightmove_delay=self._rightmove_delay,
                rightmove_location=self.rightmove,
            )
            return {
                "success": True,
                "listing_count": rental.rental_listings_count,
                "rental_analysis": rental,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _fetch_sales_market(
        self, postcode: str, radius: float
    ) -> Dict[str, Any]:
        """Fetch current sales market from Rightmove (sync, wrapped in thread)."""
        try:
            url = await asyncio.to_thread(
                self.rightmove.build_search_url,
                postcode,
                property_type="sale",
                radius=radius,
            )
            listings = await asyncio.to_thread(
                fetch_listings,
                url,
                max_pages=1,
                rate_limit_seconds=self._rightmove_delay,
            )

            if not listings:
                return {
                    "success": True,
                    "listing_count": 0,
                    "current_market": CurrentMarket(
                        search_radius_miles=radius,
                        for_sale_count=0,
                    ),
                }

            prices = [l.price for l in listings if l.price and l.price > 0]
            if not prices:
                return {
                    "success": True,
                    "listing_count": len(listings),
                    "current_market": CurrentMarket(
                        search_radius_miles=radius,
                        for_sale_count=len(listings),
                    ),
                }

            prices.sort()
            median_val = int(stat_median(prices)) if prices else None
            avg = int(sum(prices) / len(prices)) if prices else None

            market = CurrentMarket(
                search_radius_miles=radius,
                for_sale_count=len(listings),
                average_asking_price=avg,
                median_asking_price=median_val,
                asking_range_low=min(prices) if prices else None,
                asking_range_high=max(prices) if prices else None,
            )

            return {
                "success": True,
                "listing_count": len(listings),
                "current_market": market,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

