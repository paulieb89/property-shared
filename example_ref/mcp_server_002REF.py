"""
Property Investment Analyzer - MCP Server

Exposes property analysis tools via Model Context Protocol for use with
Claude and other LLM assistants.

Tools:
- analyze_end_value: Get £/sqft metrics for a postcode
- analyze_blocks: Find buildings with multiple flat sales
- search_planning: Planning applications and history
- search_safety: Building safety issues (cladding, EWS1)
- search_news: Recent news about building/area
- search_market: Market context and trends
- search_lettings: Rental market info
- search_company: Companies House lookup (freeholders, RMCs)
- quick_search: Custom web search
- analyze_rent_gap: Compare current rent to market
- scrape_listing: Extract data from listing URL (background task)
- calculate_yield: Gross/net rental yield
- calculate_psf: Price per square foot
- calculate_stamp_duty: UK SDLT calculator
- parse_postcode: Normalize and parse UK postcode

Usage:
    # Run directly
    uv run python mcp_server.py

    # Or with fastmcp CLI
    fastmcp run mcp_server.py

    # Add to Claude Desktop config (claude_desktop_config.json):
    {
        "mcpServers": {
            "property-analyzer": {
                "command": "uv",
                "args": ["run", "python", "/path/to/mcp_server.py"]
            }
        }
    }
"""

import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import anyio
import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

# Companies House API key (register free at https://developer.company-information.service.gov.uk/)
COMPANIES_HOUSE_API_KEY = os.getenv("COMPANIES_HOUSE_API_KEY", "")
# Set to "true" to use sandbox environment (for testing with invalid keys)
COMPANIES_HOUSE_SANDBOX = os.getenv("COMPANIES_HOUSE_SANDBOX", "").lower() in ("true", "1", "yes")

# Import analysis modules
from analysis import EndValueAnalyzer, BlockAnalyzer, derive_sector
from research import PropertyResearcher
from listings.vision_scraper import scrape_generic

# Initialize FastMCP server
mcp = FastMCP(
    name="Property Investment Analyzer",
    instructions="""
    Property investment analysis tools for UK real estate.

    Data & Research:
    - analyze_end_value: £/sqft metrics for a postcode sector
    - analyze_blocks: Find buildings with multiple flat sales
    - search_planning: Planning applications and history
    - search_safety: Building safety issues (cladding, EWS1)
    - search_news: Recent news about building/area
    - search_market: Sales market context
    - search_lettings: Rental market info
    - search_company: Companies House lookup (freeholders, RMCs, directors)
    - quick_search: Custom web search
    - analyze_rent_gap: Compare current rent to market rates
    - scrape_listing: Extract structured data from any listing URL (background task)

    Calculators:
    - calculate_yield: Rental yield from price and rent
    - calculate_psf: Price per square foot
    - calculate_stamp_duty: UK SDLT calculator
    - parse_postcode: Normalize UK postcode

    Property types: F=Flats, T=Terraced, S=Semi-detached, D=Detached

    Investment guidelines (flag these to the user):
    - Lease < 80 years: Mortgage difficulty, requires extension
    - Lease < 70 years: Most lenders won't lend
    - Service charge > £3/sqft/year: High for residential (£5 in prime London)
    - Ground rent > 0.1% of value OR >£250/yr (>£1k in London): Mortgage issues
    - Ground rent with doubling/escalation clause: Major red flag
    - EPC rating F or G: Illegal to let without improvements
    - Gross yield < 6%: Below typical BTL investor threshold (2025+)
    - Price > 15% above market £/sqft: Potentially overpriced
    - Price > 15% below market £/sqft: Investigate why (distressed/issues)
    - Thin market (< 10 transactions/year): Limited exit liquidity
    """,
)

# Initialize analyzers (shared instances)
end_value_analyzer = EndValueAnalyzer()
block_analyzer = BlockAnalyzer()
researcher = PropertyResearcher()


# -----------------------------------------------------------------------------
# Tools
# -----------------------------------------------------------------------------


@mcp.tool
async def analyze_end_value(
    postcode: str,
    property_type: str = "F",
    months: int = 12,
    limit: int = 30,
    exclude_new_builds: bool = False,
) -> dict:
    """
    Calculate £/sqft metrics for a postcode sector.

    Combines Land Registry sales with EPC floor areas to derive price per
    square foot - essential for estimating Gross Development Value (GDV).

    Args:
        postcode: UK postcode (e.g., "B1 1AA"). Searches at sector level.
        property_type: F=Flats, T=Terraced, S=Semi-detached, D=Detached
        months: Lookback period in months (default 12)
        limit: Maximum transactions to analyze (default 30)
        exclude_new_builds: Filter out new build sales if True

    Returns:
        Dict with median_price_per_sqft, absorption_rate, transaction_count,
        epc_match_rate, thin_market flag, and sample transactions.
    """
    result = await end_value_analyzer.analyze(
        postcode=postcode,
        months=months,
        limit=limit,
        property_type=property_type,
        exclude_new_builds=exclude_new_builds,
    )

    # Convert to dict, limiting transactions for response size
    return {
        "postcode_sector": result.postcode_sector,
        "property_type": result.property_type,
        "months_searched": result.months_searched,
        "transaction_count": result.transaction_count,
        "with_area_count": result.with_area_count,
        "new_build_count": result.new_build_count,
        "epc_match_rate": result.epc_match_rate,
        "absorption_rate": result.absorption_rate,
        "thin_market": result.thin_market,
        "median_price_per_sqft": result.median_price_per_sqft,
        "mean_price_per_sqft": result.mean_price_per_sqft,
        "min_price_per_sqft": result.min_price_per_sqft,
        "max_price_per_sqft": result.max_price_per_sqft,
        "median_price": result.median_price,
        "sample_transactions": [
            {
                "price": t.price,
                "address": t.address,
                "postcode": t.postcode,
                "floor_area_sqm": t.floor_area_sqm,
                "price_per_sqft": t.price_per_sqft,
                "date": t.date,
                "new_build": t.new_build,
            }
            for t in result.transactions[:10]
        ],
    }


@mcp.tool
def analyze_blocks(
    postcode: str,
    months: int = 24,
    limit: int = 50,
    min_transactions: int = 2,
) -> dict:
    """
    Find buildings with multiple flat sales - useful for block buyers.

    Identifies buildings where multiple units have sold recently, indicating:
    - Blocks being sold off (investor exit)
    - Opportunities to buy multiple units
    - Active buildings worth investigating

    Args:
        postcode: UK postcode (searches at sector level)
        months: Lookback period in months (default 24)
        limit: Maximum transactions to fetch (default 50)
        min_transactions: Minimum sales to qualify as active block (default 2)

    Returns:
        Dict with list of blocks, each containing building name, transaction
        count, price range, and recent sales.
    """
    blocks = block_analyzer.analyze_blocks(
        postcode=postcode,
        months=months,
        limit=limit,
        min_transactions=min_transactions,
    )

    return {
        "postcode_sector": derive_sector(postcode),
        "blocks_found": len(blocks),
        "blocks": [
            {
                "building_name": b.building_name,
                "street": b.street,
                "postcode": b.postcode,
                "transaction_count": b.transaction_count,
                "new_build_count": b.new_build_count,
                "avg_price": b.avg_price,
                "min_price": b.min_price,
                "max_price": b.max_price,
                "total_value": b.total_value,
                "date_range": b.date_range,
                "recent_sales": [
                    {
                        "unit": t.unit,
                        "price": t.price,
                        "date": t.date,
                    }
                    for t in b.transactions[:5]
                ],
            }
            for b in blocks[:15]
        ],
    }


@mcp.tool
def search_planning(
    building: str,
    postcode: str,
) -> str:
    """
    Search for planning applications and development history.

    Args:
        building: Building name or address (e.g., "The Cube, 200 Wharfside Street")
        postcode: UK postcode (e.g., "B1 1PR")

    Returns:
        Planning summary text with applications, permissions, nearby developments.
    """
    try:
        return researcher.search_planning(building, postcode)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool
def search_safety(
    building: str,
    postcode: str,
) -> str:
    """
    Search for building safety issues.

    Looks for cladding remediation, fire safety concerns, EWS1 status,
    waking watch costs, and related legal cases.

    Args:
        building: Building name or address
        postcode: UK postcode

    Returns:
        Safety summary text with any known issues.
    """
    try:
        return researcher.search_safety(building, postcode)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool
def search_news(
    building: str,
    postcode: str,
) -> str:
    """
    Search for recent news about a building or area.

    Looks for property news, sales, regeneration projects,
    and anything affecting property values.

    Args:
        building: Building name or address
        postcode: UK postcode

    Returns:
        News summary text with recent developments.
    """
    try:
        return researcher.search_news(building, postcode)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool
def search_lettings(
    postcode: str,
    property_type: str = "flat",
) -> dict:
    """
    Search for rental listings and lettings market in an area.

    Searches for current rental prices, supply/demand, and comparison
    to nearby areas. Uses full postcode for local search.

    Args:
        postcode: Full UK postcode (e.g., "B1 1AA")
        property_type: Type description (flat, house, room)

    Returns:
        Dict with lettings_summary text.
    """
    try:
        summary = researcher.search_lettings(postcode, property_type)
    except Exception as e:
        summary = f"Error: {e}"

    return {
        "postcode": postcode,
        "property_type": property_type,
        "lettings_summary": summary,
    }


@mcp.tool
def search_market(
    postcode: str,
    property_type: str = "flat",
) -> dict:
    """
    Get market context and trends for an area.

    Searches for recent market information including:
    - Price trends
    - Rental yields
    - Supply and demand
    - Major developments
    - Comparison to regional averages

    Args:
        postcode: UK postcode (searches at sector level)
        property_type: Type description (flat, house, commercial)

    Returns:
        Dict with market_summary text.
    """
    try:
        summary = researcher.search_market(postcode, property_type)
    except Exception as e:
        summary = f"Error: {e}"

    return {
        "postcode_sector": derive_sector(postcode),
        "property_type": property_type,
        "market_summary": summary,
    }


@mcp.tool
def quick_search(query: str) -> dict:
    """
    Run a custom property-related web search.

    Use for one-off queries that don't fit other tools, such as:
    - "What is the service charge at [building]?"
    - "Who manages [building name]?"
    - "Recent auction results in [area]"

    Args:
        query: Free-form search query

    Returns:
        Dict with search_result text.
    """
    try:
        result = researcher.quick_search(query)
    except Exception as e:
        result = f"Error: {e}"

    return {
        "query": query,
        "search_result": result,
    }


@mcp.tool
def search_company(query: str) -> dict:
    """
    Search Companies House for company information.

    Useful for finding:
    - Freeholder/management company details
    - Company status (active, dissolved, etc.)
    - Directors and registered address
    - Company type (RMC, property company, etc.)

    Args:
        query: Company name or number (e.g., "Melbourne Road Management" or "09333116")

    Returns:
        Dict with company details from Companies House.
    """
    if not COMPANIES_HOUSE_API_KEY:
        return {"error": "COMPANIES_HOUSE_API_KEY not configured"}

    # Use sandbox for testing, live for production
    if COMPANIES_HOUSE_SANDBOX:
        base_url = "https://api-sandbox.company-information.service.gov.uk"
    else:
        base_url = "https://api.company-information.service.gov.uk"
    auth = (COMPANIES_HOUSE_API_KEY, "")  # API key as username, empty password

    try:
        # Check if query looks like a company number (8 digits, may have leading zeros)
        is_company_number = (
            query.isdigit() or
            (len(query) == 8 and query[:2].isalpha()) or  # e.g., "SC123456"
            (len(query) <= 8 and query.lstrip("0").isdigit())  # e.g., "09333116"
        )

        if is_company_number and len(query) <= 8:
            # Direct company lookup by number
            company_number = query.upper().zfill(8)  # Pad to 8 chars
            response = httpx.get(f"{base_url}/company/{company_number}", auth=auth, timeout=10)

            if response.status_code == 404:
                return {"query": query, "error": "Company not found"}
            response.raise_for_status()

            company = response.json()

            # Also fetch officers (directors)
            officers_response = httpx.get(
                f"{base_url}/company/{company_number}/officers", auth=auth, timeout=10
            )
            officers = []
            if officers_response.status_code == 200:
                officers_data = officers_response.json()
                officers = [
                    {
                        "name": o.get("name"),
                        "role": o.get("officer_role"),
                        "appointed": o.get("appointed_on"),
                    }
                    for o in officers_data.get("items", [])[:5]  # Limit to 5
                ]

            result = {
                "query": query,
                "company_number": company.get("company_number"),
                "company_name": company.get("company_name"),
                "company_status": company.get("company_status"),
                "company_type": company.get("type"),
                "date_of_creation": company.get("date_of_creation"),
                "registered_office": company.get("registered_office_address"),
                "sic_codes": company.get("sic_codes", []),
                "officers": officers,
            }
            if COMPANIES_HOUSE_SANDBOX:
                result["_sandbox"] = True
            return result
        else:
            # Search by company name
            response = httpx.get(
                f"{base_url}/search/companies",
                params={"q": query, "items_per_page": 5},
                auth=auth,
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            results = [
                {
                    "company_number": item.get("company_number"),
                    "company_name": item.get("title"),
                    "company_status": item.get("company_status"),
                    "company_type": item.get("company_type"),
                    "date_of_creation": item.get("date_of_creation"),
                    "address_snippet": item.get("address_snippet"),
                }
                for item in data.get("items", [])
            ]

            result = {
                "query": query,
                "total_results": data.get("total_results", 0),
                "companies": results,
            }
            if COMPANIES_HOUSE_SANDBOX:
                result["_sandbox"] = True
            return result

    except httpx.HTTPStatusError as e:
        return {"query": query, "error": f"API error: {e.response.status_code}"}
    except Exception as e:
        return {"query": query, "error": str(e)}


@mcp.tool
def analyze_rent_gap(
    postcode: str,
    current_rent_pcm: int,
    num_units: int = 1,
    property_type: str = "flat",
) -> dict:
    """
    Compare current rent to market rates and calculate potential upside.

    Identifies under-rented properties where rent increases could improve yield.

    Args:
        postcode: UK postcode for market comparison
        current_rent_pcm: Current rent per calendar month per unit in £
        num_units: Number of units (for multi-unit properties)
        property_type: Type for market search (flat, house, room)

    Returns:
        Dict with market rent estimate, gap percentage, and annual upside.
    """
    # Get market lettings data
    try:
        lettings_summary = researcher.search_lettings(postcode, property_type)
    except Exception as e:
        return {"error": f"Could not fetch market data: {e}"}

    # Current figures
    current_annual = current_rent_pcm * 12 * num_units

    return {
        "postcode": postcode,
        "property_type": property_type,
        "num_units": num_units,
        "current_rent_pcm": current_rent_pcm,
        "current_annual_total": current_annual,
        "market_research": lettings_summary,
        "analysis_note": "Compare current_rent_pcm to market rents in the research above. "
                        "If current rent is below market, calculate: "
                        "(market_pcm - current_pcm) × 12 × num_units = annual_upside",
    }


@mcp.tool(task=True)
async def scrape_listing(url: str) -> dict:
    """
    Scrape a property listing URL and extract structured data.

    Uses Playwright + OpenAI Vision to capture screenshots and parse any
    property listing site. Runs as background task - returns task ID immediately.

    Supports: Rightmove, OnTheMarket, Zoopla, Allsop auctions, and most other
    property listing sites.

    Args:
        url: Property listing URL

    Returns:
        Structured property data including price, size, tenure, EPC,
        accommodation details, tenancy info, and more.
    """
    # Generate output dir from URL
    output_name = url.split("/")[-1].split("?")[0] or "listing"
    output_dir = Path(f"./output/{output_name}")

    # Run sync Playwright in thread pool to avoid blocking
    result = await anyio.to_thread.run_sync(scrape_generic, url, output_dir)

    return result


# -----------------------------------------------------------------------------
# Atomic Calculators
# -----------------------------------------------------------------------------


@mcp.tool
def calculate_yield(
    price: int,
    annual_rent: int,
    annual_costs: int = 0,
) -> dict:
    """
    Calculate rental yield for a property.

    Args:
        price: Purchase price in £
        annual_rent: Annual rental income in £
        annual_costs: Annual costs (service charge, ground rent, etc.) in £

    Returns:
        Dict with gross_yield and net_yield as percentages.
    """
    gross = round((annual_rent / price) * 100, 2) if price > 0 else 0
    net = round(((annual_rent - annual_costs) / price) * 100, 2) if price > 0 else 0
    return {
        "gross_yield": gross,
        "net_yield": net,
        "annual_rent": annual_rent,
        "annual_costs": annual_costs,
        "net_income": annual_rent - annual_costs,
    }


@mcp.tool
def calculate_psf(
    price: int,
    size_sqft: int | None = None,
    size_sqm: int | None = None,
) -> dict:
    """
    Calculate price per square foot.

    Args:
        price: Price in £
        size_sqft: Size in square feet (provide this OR size_sqm)
        size_sqm: Size in square metres (converted to sqft if provided)

    Returns:
        Dict with price_per_sqft and size_sqft.
    """
    if size_sqm and not size_sqft:
        size_sqft = int(size_sqm * 10.764)

    if not size_sqft or size_sqft <= 0:
        return {"error": "Size required (size_sqft or size_sqm)"}

    psf = round(price / size_sqft, 2)
    return {
        "price_per_sqft": psf,
        "size_sqft": size_sqft,
        "price": price,
    }


@mcp.tool
def calculate_stamp_duty(
    price: int,
    additional_property: bool = True,
    first_time_buyer: bool = False,
    non_resident: bool = False,
) -> dict:
    """
    Calculate UK Stamp Duty Land Tax (SDLT) for residential property.

    Args:
        price: Purchase price in £
        additional_property: True if buying additional property (5% surcharge)
        first_time_buyer: True for first-time buyer relief (up to £300k nil rate)
        non_resident: True if buyer not UK resident (+2% surcharge)

    Returns:
        Dict with total SDLT, effective rate, and breakdown by band.
    """
    # SDLT bands (April 2025 onwards)
    bands = [
        (125_000, 0),      # 0% up to £125k
        (250_000, 2),      # 2% £125k-£250k
        (925_000, 5),      # 5% £250k-£925k
        (1_500_000, 10),   # 10% £925k-£1.5m
        (float('inf'), 12) # 12% above £1.5m
    ]

    # First-time buyer bands (properties up to £500k)
    ftb_bands = [
        (300_000, 0),      # 0% up to £300k
        (500_000, 5),      # 5% £300k-£500k
    ]

    # Calculate surcharges
    surcharge = 0
    if additional_property:
        surcharge += 5  # Increased from 3% to 5% (Oct 2024)
    if non_resident:
        surcharge += 2  # Non-UK resident surcharge

    # Use FTB bands if eligible (not available with additional property)
    if first_time_buyer and price <= 500_000 and not additional_property:
        bands = ftb_bands

    total_sdlt = 0
    breakdown = []
    remaining = price
    prev_threshold = 0

    for threshold, rate in bands:
        if remaining <= 0:
            break

        band_amount = min(remaining, threshold - prev_threshold)
        effective_rate = rate + surcharge
        band_tax = band_amount * (effective_rate / 100)

        if band_amount > 0:
            breakdown.append({
                "band": f"£{prev_threshold:,} - £{int(threshold):,}" if threshold != float('inf') else f"Above £{prev_threshold:,}",
                "amount": band_amount,
                "rate": effective_rate,
                "tax": round(band_tax, 2),
            })

        total_sdlt += band_tax
        remaining -= band_amount
        prev_threshold = threshold

    effective_rate = round((total_sdlt / price) * 100, 2) if price > 0 else 0

    return {
        "total_sdlt": round(total_sdlt, 2),
        "effective_rate": effective_rate,
        "price": price,
        "additional_property": additional_property,
        "first_time_buyer": first_time_buyer,
        "non_resident": non_resident,
        "surcharges_applied": surcharge,
        "breakdown": breakdown,
    }


@mcp.tool
def parse_postcode(postcode: str) -> dict:
    """
    Parse and normalize a UK postcode.

    Args:
        postcode: UK postcode in any format (e.g., "b11aa", "B1 1AA", "b1  1aa")

    Returns:
        Dict with normalized full postcode, sector, and outward code.
    """
    # Normalize: uppercase, strip, collapse spaces
    pc = postcode.upper().strip()
    pc = " ".join(pc.split())  # Collapse multiple spaces

    # Ensure single space before inward code (last 3 chars)
    if " " not in pc and len(pc) >= 5:
        pc = pc[:-3] + " " + pc[-3:]

    parts = pc.split()
    if len(parts) != 2:
        return {"error": f"Invalid postcode format: {postcode}"}

    outward = parts[0]
    inward = parts[1]
    sector = f"{outward} {inward[0]}"

    return {
        "full": pc,
        "outward": outward,
        "inward": inward,
        "sector": sector,
        "input": postcode,
    }


# -----------------------------------------------------------------------------
# Resources
# -----------------------------------------------------------------------------


@mcp.resource("property://help")
def get_help() -> str:
    """Overview of available property analysis tools."""
    return """
# Property Investment Analyzer

## Data & Research Tools

### analyze_end_value
Calculate £/sqft metrics for a postcode. Essential for GDV estimates.
- Example: analyze_end_value(postcode="B1 1AA", property_type="F", months=12)

### analyze_blocks
Find buildings with multiple flat sales (block buying opportunities).
- Example: analyze_blocks(postcode="B1 1AA", months=24, min_transactions=2)

### search_planning / search_safety / search_news
Research a specific building or area.
- Example: search_planning(building="The Cube", postcode="B1 1PR")

### search_market / search_lettings
Get market context for sales or rentals.
- Example: search_market(postcode="B1 1AA", property_type="flat")

### search_company
Look up companies on Companies House (freeholders, management companies, RMCs).
- Example: search_company(query="Melbourne Road Management Company")
- Returns: company status, directors, registered address, type
- Set COMPANIES_HOUSE_SANDBOX=true for testing (limited data)

### quick_search
Custom web search for property-related queries.
- Example: quick_search(query="service charge The Cube Birmingham")

### analyze_rent_gap
Compare current rent to market rates for value-add opportunities.
- Example: analyze_rent_gap(postcode="LE67 2AA", current_rent_pcm=575, num_units=7)
- Returns: market research + framework to calculate rent uplift potential

### scrape_listing
Extract structured data from any property listing URL using vision AI.
- Example: scrape_listing(url="https://www.rightmove.co.uk/properties/123456789")
- Runs as background task (returns task ID immediately)
- Supports: Rightmove, OnTheMarket, Zoopla, auction sites, etc.
- Returns: price, size, tenure, EPC, accommodation, tenancy details

## Calculators

### calculate_yield
Calculate gross/net rental yield.
- Example: calculate_yield(price=150000, annual_rent=9600, annual_costs=1200)

### calculate_psf
Calculate price per square foot.
- Example: calculate_psf(price=150000, size_sqft=500)

### calculate_stamp_duty
Calculate UK SDLT with surcharges (April 2025 rates).
- additional_property: +5% surcharge (investors, BTL, second homes)
- non_resident: +2% surcharge (overseas buyers)
- Example: calculate_stamp_duty(price=550000, additional_property=True, non_resident=False)

### parse_postcode
Normalize and parse UK postcode.
- Example: parse_postcode("b1 1aa") -> {full: "B1 1AA", sector: "B1 1"}

## Property Types
F=Flats, T=Terraced, S=Semi-detached, D=Detached

## Investment Red Flags
- Lease < 80 years: Mortgage issues
- Service charge > £3/sqft/year: High (£5 prime London)
- Ground rent > 0.1% of value: Lender issues
- Ground rent with doubling clause: Major red flag
- EPC rating F/G: Illegal to let
- Gross yield < 6%: Below BTL threshold (2025+)
"""


@mcp.resource("property://sectors/{postcode}")
def get_sector_info(postcode: str) -> str:
    """Get sector derivation for a postcode."""
    sector = derive_sector(postcode)
    return f"Postcode: {postcode}\nSector: {sector}\n\nSearches are performed at sector level (outward code + first inward digit)."


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
