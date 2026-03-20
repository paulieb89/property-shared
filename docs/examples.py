"""Property Core — Real examples with expected output.

Run any section:
    uv run python docs/examples.py                    # all examples
    uv run python docs/examples.py ppd                # just PPD
    uv run python docs/examples.py rightmove           # just Rightmove
    uv run python docs/examples.py rental              # just rental analysis
    uv run python docs/examples.py yield               # just yield analysis
    uv run python docs/examples.py postcode            # just postcode lookup
    uv run python docs/examples.py planning            # just planning council
    uv run python docs/examples.py stamp-duty          # just stamp duty
    uv run python docs/examples.py blocks              # just block analyzer
    uv run python docs/examples.py companies           # just companies house
    uv run python docs/examples.py api                 # HTTP API (curl examples)

Real output from NG1 1GF (Nottingham city centre), captured 2026-03-18.
"""

from __future__ import annotations

import asyncio
import sys


# ---------------------------------------------------------------------------
# 1. PPD Comparable Sales
# ---------------------------------------------------------------------------
def example_ppd_comps():
    """
    Find comparable sales around a postcode.

    >>> from property_core import PPDService
    >>> ppd = PPDService()
    >>> result = ppd.comps(postcode="NG1 1GF", months=24, limit=5)
    >>> result.count
    5
    >>> result.median
    160000
    >>> result.thin_market
    False

    Real output:
        Count: 5
        Median: £160,000
        Mean: £138,000
        Range: £55,000 - £210,000
        P25/P75: £72,500 / £192,500

        2025-12-05  £160,000  THE ESTABLISHMENT, 3 BROADWAY, NG1 1PR  (F)
        2025-12-04  £210,000  1A HOLLOWSTONE, NG1 1JH  (F)
        2025-11-27  £55,000   THE ICE HOUSE BELWARD STREET, NG1 1JW  (F)
    """
    from property_core import PPDService

    ppd = PPDService()
    result = ppd.comps(postcode="NG1 1GF", months=24, limit=5)

    print("=== PPD Comparable Sales ===")
    print(f"Count: {result.count}")
    print(f"Median: £{result.median:,}")
    print(f"Mean: £{result.mean:,}")
    print(f"Range: £{result.min:,} - £{result.max:,}")
    print(f"P25/P75: £{result.percentile_25:,} / £{result.percentile_75:,}")
    print(f"Thin market: {result.thin_market}")
    print()
    for t in result.transactions[:3]:
        print(f"  {t.date}  £{t.price:,}  {t.paon} {t.street}, {t.postcode}  ({t.property_type})")


# ---------------------------------------------------------------------------
# 2. PPD Comps with Address Match (subject property)
# ---------------------------------------------------------------------------
def example_ppd_comps_with_address():
    """
    Pass an address to identify the subject property within comps.

    >>> result = ppd.comps(postcode="NG1 1GF", months=24, limit=10, address="3 Broadway")
    >>> result.subject_property is not None
    True
    >>> result.subject_property.address
    'THE ESTABLISHMENT, 3 BROADWAY'
    >>> result.subject_vs_median_pct  # % above/below median
    7.6

    Real output:
        Subject: THE ESTABLISHMENT, 3 BROADWAY
        Last sale: £160,000 on 2025-12-05
        vs Median: +7.6%
        Percentile: 54th
    """
    from property_core import PPDService

    ppd = PPDService()
    result = ppd.comps(postcode="NG1 1GF", months=24, limit=10, address="3 Broadway")

    print("=== PPD Comps with Address Match ===")
    print(f"Count: {result.count}")
    print(f"Median: £{result.median:,}")
    if result.subject_property:
        sp = result.subject_property
        print(f"Subject: {sp.address}")
        if sp.last_sale:
            print(f"  Last sale: £{sp.last_sale.price:,} on {sp.last_sale.date}")
        print(f"  Transactions: {sp.transaction_count}")
        if result.subject_vs_median_pct is not None:
            print(f"  vs Median: {result.subject_vs_median_pct:+.1f}%")
        if result.subject_price_percentile is not None:
            print(f"  Percentile: {result.subject_price_percentile}th")
    else:
        print("Subject: not found in results")


# ---------------------------------------------------------------------------
# 3. PPD Transaction Search
# ---------------------------------------------------------------------------
def example_ppd_transactions():
    """
    Search individual transactions by postcode.

    >>> ppd = PPDService()
    >>> txns = ppd.search_transactions(postcode="NG1 1GF", postcode_prefix=None, limit=3)
    >>> txns["count"]
    1

    Real output:
        1 transaction(s) found
        2021-04-19  £1,350,000  BIOCITY NOTTINGHAM PENNYFOOT STREET, NG1 1GF  (O/F)
    """
    from property_core import PPDService

    ppd = PPDService()
    txns = ppd.search_transactions(postcode="NG1 1GF", postcode_prefix=None, limit=5)
    results = txns["results"]

    print(f"=== PPD Transactions ({txns['count']} found) ===")
    for t in results:
        print(f"  {t.date}  £{t.price:,}  {t.paon} {t.street}, {t.postcode}  ({t.property_type}/{t.estate_type})")


# ---------------------------------------------------------------------------
# 4. Rightmove Sale Listings
# ---------------------------------------------------------------------------
def example_rightmove_sales():
    """
    Search Rightmove for sale listings near a postcode.

    >>> from property_core import RightmoveLocationAPI, fetch_listings
    >>> rm = RightmoveLocationAPI()
    >>> url = rm.build_search_url("NG1 1GF", property_type="sale", radius=0.5)
    >>> listings = fetch_listings(url, max_pages=1)
    >>> len(listings)
    25

    Real output:
        25 listings found
        £112,000  2bed flat — Huntingdon Street, Nottingham, NG1
        £1,100,000  5bed terraced house — Kirk House, Ristes Place, Nottingham
        £475,000  6bed block of apartments — St Stephens Road, Sneinton
    """
    from property_core import RightmoveLocationAPI, fetch_listings

    rm = RightmoveLocationAPI()
    url = rm.build_search_url("NG1 1GF", property_type="sale", radius=0.5)
    print(f"Search URL: {url}")
    print()

    listings = fetch_listings(url, max_pages=1)
    print(f"=== Rightmove Sale Listings ({len(listings)} found) ===")
    for l in listings[:5]:
        price = f"£{l.price:,}" if l.price else "POA"
        print(f"  {price}  {l.bedrooms}bed {l.property_type or ''}")
        print(f"    {l.address}")
        print(f"    {l.agent_name} | Listed: {l.first_visible_date}")


# ---------------------------------------------------------------------------
# 5. Rightmove Rental Listings
# ---------------------------------------------------------------------------
def example_rightmove_rentals():
    """
    Search Rightmove for rental listings.

    >>> url = rm.build_search_url("NG1 1GF", property_type="rent", radius=0.5)
    >>> listings = fetch_listings(url, max_pages=1)
    >>> len(listings)
    25

    Real output:
        £1,330/mo  2bed apartment — Crocus Street, Nottingham, NG2
        £872/mo    2bed flat — Short Stairs, The Gatehouse, NG1
        £495/wk    5bed apartment — Flat 2 1 Barker Gate, Nottingham
    """
    from property_core import RightmoveLocationAPI, fetch_listings

    rm = RightmoveLocationAPI()
    url = rm.build_search_url("NG1 1GF", property_type="rent", radius=0.5)
    listings = fetch_listings(url, max_pages=1)

    print(f"=== Rightmove Rental Listings ({len(listings)} found) ===")
    for l in listings[:5]:
        price = f"£{l.price:,}" if l.price else "POA"
        freq = l.price_frequency or "pcm"
        print(f"  {price} {freq}  {l.bedrooms}bed {l.property_type or ''}")
        print(f"    {l.address}")
        print(f"    {l.agent_name} | Status: {l.listing_status}")


# ---------------------------------------------------------------------------
# 6. Rightmove Listing Detail
# ---------------------------------------------------------------------------
def example_rightmove_detail():
    """
    Get full details for a specific listing (from search results).

    >>> from property_core import fetch_listing
    >>> detail = fetch_listing("173352479")
    >>> detail.address
    "Queens Road, Nottingham, NG2"
    >>> detail.tenure_type
    "LEASEHOLD"

    Real output:
        Address: Queens Road, Nottingham, NG2
        Price: £100,000
        Type: Flat | Beds: 1 | Baths: 1
        Size: Ask agent
        Tenure: LEASEHOLD | Council Tax: B
        Station: Nottingham Station (0.2 mi)
        Features: Third Floor Flat, Double Bedroom, Modern Fitted Kitchen
    """
    from property_core import RightmoveLocationAPI, fetch_listing, fetch_listings

    # Get a valid listing ID from search
    rm = RightmoveLocationAPI()
    url = rm.build_search_url("NG1 1GF", property_type="sale", radius=0.5)
    listings = fetch_listings(url, max_pages=1)
    if not listings:
        print("No listings found")
        return

    lid = str(listings[0].id)
    detail = fetch_listing(lid)

    print("=== Listing Detail ===")
    print(f"Address: {detail.address}")
    print(f"Price: £{detail.price:,}" if detail.price else "Price: POA")
    print(f"Type: {detail.property_type} | Beds: {detail.bedrooms} | Baths: {detail.bathrooms}")
    print(f"Size: {detail.display_size}")
    print(f"Tenure: {detail.tenure_type} | Council Tax: {detail.council_tax_band}")
    if detail.nearest_stations:
        for s in detail.nearest_stations[:2]:
            print(f"  Station: {s['name']} ({s['distance']} mi)")
    if detail.key_features:
        print(f"Features: {', '.join(detail.key_features[:4])}")


# ---------------------------------------------------------------------------
# 7. Rental Analysis (async)
# ---------------------------------------------------------------------------
def example_rental_analysis():
    """
    Analyze rental market around a postcode (IQR-filtered stats).

    >>> import asyncio
    >>> from property_core import analyze_rentals
    >>> rental = asyncio.run(analyze_rentals("NG1 1GF", radius=0.5))
    >>> rental.median_rent_monthly
    1025
    >>> rental.rental_listings_count
    25

    Real output:
        Listings: 25
        Median rent: £1,025/mo
        Average rent: £1,178/mo
        Range: £350 - £1,470 (IQR-filtered)
    """
    from property_core import analyze_rentals

    async def _run():
        rental = await analyze_rentals("NG1 1GF", radius=0.5)
        print("=== Rental Analysis ===")
        print(f"Listings: {rental.rental_listings_count}")
        if rental.median_rent_monthly:
            print(f"Median rent: £{rental.median_rent_monthly:,}/mo")
        if rental.average_rent_monthly:
            print(f"Average rent: £{rental.average_rent_monthly:,}/mo")
        if rental.rent_range_low and rental.rent_range_high:
            print(f"Range: £{rental.rent_range_low:,} - £{rental.rent_range_high:,} (IQR-filtered)")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 8. Yield Analysis (async)
# ---------------------------------------------------------------------------
def example_yield_analysis():
    """
    Calculate gross rental yield: PPD median sale price vs Rightmove median rent.

    >>> from property_core import calculate_yield
    >>> y = asyncio.run(calculate_yield("NG1 1GF", months=24, radius=0.5))
    >>> y.gross_yield_pct
    8.07
    >>> y.yield_assessment
    'strong'
    >>> y.data_quality
    'good'

    Real output:
        Postcode: NG1 1GF
        Median sale price: £148,750
        Sale count: 50
        Median monthly rent: £1,000
        Rental count: 25
        Gross yield: 8.07%
        Assessment: strong
        Data quality: good
    """
    from property_core import calculate_yield

    async def _run():
        y = await calculate_yield("NG1 1GF", months=24, radius=0.5)
        print("=== Yield Analysis ===")
        print(f"Postcode: {y.postcode}")
        if y.median_sale_price:
            print(f"Median sale price: £{y.median_sale_price:,}")
        print(f"Sale count: {y.sale_count}")
        if y.median_monthly_rent:
            print(f"Median monthly rent: £{y.median_monthly_rent:,}")
        print(f"Rental count: {y.rental_count}")
        if y.gross_yield_pct:
            print(f"Gross yield: {y.gross_yield_pct}%")
        if y.yield_assessment:
            print(f"Assessment: {y.yield_assessment}")
        print(f"Data quality: {y.data_quality}")
        print(f"Thin market: {y.thin_market}")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 9. Postcode Lookup
# ---------------------------------------------------------------------------
def example_postcode():
    """
    Look up postcode metadata via postcodes.io.

    >>> from property_core import PostcodeClient
    >>> pc = PostcodeClient()
    >>> result = pc.lookup("SW1A 2AA")
    >>> result.admin_district
    'Westminster'
    >>> result.region
    'London'

    Real output:
        Postcode: SW1A 2AA
        District: Westminster
        Region: London
        Country: England
        Lat/Lon: 51.503541, -0.12767
        Rural/Urban: Urban: Nearer to a major town or city
    """
    from property_core import PostcodeClient

    pc = PostcodeClient()
    result = pc.lookup("SW1A 2AA")

    print("=== Postcode Lookup ===")
    print(f"Postcode: {result.postcode}")
    print(f"District: {result.admin_district}")
    print(f"County: {result.admin_county}")
    print(f"Region: {result.region}")
    print(f"Country: {result.country}")
    print(f"Lat/Lon: {result.latitude}, {result.longitude}")
    print(f"Rural/Urban: {result.rural_urban}")


# ---------------------------------------------------------------------------
# 10. Planning Council Lookup
# ---------------------------------------------------------------------------
def example_planning():
    """
    Find the planning portal for a postcode.

    >>> from property_core import PlanningService
    >>> ps = PlanningService()
    >>> result = ps.council_for_postcode("NG1 1GF")
    >>> result["council"]["name"]
    'Nottingham'
    >>> result["council"]["system"]
    'idox'

    Real output:
        Council: Nottingham
        Code: nottingham
        System: idox
        Portal: http://publicaccess.nottinghamcity.gov.uk/online-applications/
        Region: East Midlands
        Status: verified
    """
    from property_core import PlanningService

    ps = PlanningService()
    result = ps.council_for_postcode("NG1 1GF")

    c = result["council"]
    la = result["local_authority"]
    print("=== Planning Council ===")
    print(f"Council: {c['name']}")
    print(f"Code: {c['code']}")
    print(f"System: {c['system']}")
    print(f"Portal: {c['base_url']}")
    print(f"Region: {la['region']}")
    print(f"Status: {c['status']}")


# ---------------------------------------------------------------------------
# 11. Address Parsing
# ---------------------------------------------------------------------------
def example_address_parsing():
    """
    Parse combined address strings into (postcode, street).

    >>> from property_core.address_matching import parse_address
    >>> parse_address("10 Downing Street, SW1A 2AA")
    ('SW1A 2AA', '10 Downing Street')
    >>> parse_address("SW1A2AA")
    ('SW1A 2AA', None)
    >>> parse_address("not a postcode")
    (None, None)
    """
    from property_core.address_matching import parse_address

    examples = [
        "10 Downing Street, SW1A 2AA",
        "Flat 3, 42 Baker Street, NW1 6XE",
        "SW1A2AA",
        "not a postcode",
    ]
    print("=== Address Parsing ===")
    for q in examples:
        postcode, address = parse_address(q)
        print(f"  {q!r:50s} -> postcode={postcode}, address={address}")


# ---------------------------------------------------------------------------
# 12. Stamp Duty Calculator
# ---------------------------------------------------------------------------
def example_stamp_duty():
    """
    Calculate UK Stamp Duty Land Tax (April 2025 bands).

    >>> from property_core import calculate_stamp_duty
    >>> r = calculate_stamp_duty(price=300000, additional_property=True)
    >>> r.total_sdlt
    19500.0
    >>> r.effective_rate
    6.5

    Real output:
        Price: £300,000
        Total SDLT: £19,500
        Effective rate: 6.50%
        Surcharges: 5.0%
        Breakdown:
          £0 - £125,000 @ 5.0% = £6,250
          £125,000 - £250,000 @ 7.0% = £8,750
          £250,000 - £300,000 @ 10.0% = £4,500 (remaining)
    """
    from property_core import calculate_stamp_duty

    r = calculate_stamp_duty(price=300000, additional_property=True)
    print("=== Stamp Duty Calculator ===")
    print(f"Price: £{r.price:,}")
    print(f"Total SDLT: £{r.total_sdlt:,.0f}")
    print(f"Effective rate: {r.effective_rate:.2f}%")
    print(f"Surcharges: {r.surcharges_applied}%")
    print(f"Additional property: {r.additional_property}")
    print(f"First-time buyer: {r.first_time_buyer}")
    print("Breakdown:")
    for b in r.breakdown:
        print(f"  {b.rate}% on £{b.amount:,.0f} = £{b.tax:,.0f}")


# ---------------------------------------------------------------------------
# 13. Block Analyzer
# ---------------------------------------------------------------------------
def example_block_analyzer():
    """
    Find flat buildings with multiple sales (investor exits, bulk-buy opportunities).

    >>> from property_core import analyze_blocks
    >>> result = analyze_blocks(postcode="B1 1AA", months=24, min_transactions=2)
    >>> result.blocks_found
    5

    Real output (varies):
        Postcode: B1 1AA (sector, 24 months)
        Blocks found: 5
        ESSEX STREET, B5 4TR: 3 sales, £100,000-£155,000
        GRANVILLE STREET, B1 2LJ: 2 sales, £90,000-£120,000
    """
    from property_core import analyze_blocks

    result = analyze_blocks(postcode="B1 1AA", months=24, min_transactions=2)
    print("=== Block Analyzer ===")
    print(f"Postcode: {result.postcode} ({result.search_level}, {result.months} months)")
    print(f"Blocks found: {result.blocks_found}")
    for b in result.blocks[:5]:
        name = b.building_name or ""
        street = b.street or ""
        label = f"{name} {street}".strip()
        prices = ""
        if b.min_price and b.max_price:
            prices = f", £{b.min_price:,}-£{b.max_price:,}"
        print(f"  {label}: {b.transaction_count} sales{prices}")


# ---------------------------------------------------------------------------
# 14. Companies House
# ---------------------------------------------------------------------------
def example_companies_house():
    """
    Search Companies House (requires COMPANIES_HOUSE_API_KEY).

    >>> from property_core import CompaniesHouseClient
    >>> ch = CompaniesHouseClient()
    >>> result = ch.search("Tesco", items_per_page=3)
    >>> len(result.companies) > 0
    True
    >>> result.companies[0].company_name
    'TESCO PLC'

    Real output:
        3 results for "Tesco"
        00445790: TESCO PLC (active) — TESCO HOUSE SHIRE PARK KESTREL WAY, WELWYN GARDEN CITY
        SC634498: TESCO UNDERWRITING LIMITED (active)
        07720508: BOOKER TESCO HOLDINGS LIMITED (active)
    """
    from property_core import CompaniesHouseClient

    ch = CompaniesHouseClient()
    if not ch.is_configured():
        print("=== Companies House ===")
        print("  SKIPPED: COMPANIES_HOUSE_API_KEY not set")
        return

    result = ch.search("Tesco", items_per_page=3)
    print(f'=== Companies House ({len(result.companies)} results for "Tesco") ===')
    for c in result.companies:
        status = c.company_status or "unknown"
        addr = c.registered_office_address or ""
        print(f"  {c.company_number}: {c.company_name} ({status})")
        if addr:
            print(f"    {addr}")


# ---------------------------------------------------------------------------
# 15. HTTP API Examples (curl)
# ---------------------------------------------------------------------------
def example_api():
    """
    HTTP API examples (requires running server: uv run property-api).

    Start the server:
        uv run property-api                         # production
        uv run uvicorn app.main:app --reload        # dev mode

    PPD Comps:
        curl "http://localhost:8000/api/v1/ppd/comps?postcode=NG1+1GF&months=24&limit=5"

        {
          "query": {"postcode": "NG1 1GF", "months": 24, "limit": 5},
          "count": 5,
          "median": 160000,
          "mean": 138000,
          "min": 55000,
          "max": 210000,
          "percentile_25": 72500,
          "percentile_75": 192500,
          "thin_market": false,
          "transactions": [...]
        }

    PPD Comps with Address Match:
        curl "http://localhost:8000/api/v1/ppd/comps?postcode=NG1+1GF&address=3+Broadway&months=24"

    PPD Comps with EPC Enrichment:
        curl "http://localhost:8000/api/v1/ppd/comps?postcode=NG1+1GF&enrich_epc=true"

    PPD Transactions:
        curl "http://localhost:8000/api/v1/ppd/transactions?postcode=NG1+1GF&limit=5"

    Rightmove Search URL:
        curl "http://localhost:8000/api/v1/rightmove/search-url?postcode=NG1+1GF&property_type=sale&radius=0.5"

    Rightmove Listings:
        curl "http://localhost:8000/api/v1/rightmove/listings?search_url=https://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=POSTCODE%255E1694339&radius=0.5"

    EPC Search:
        curl "http://localhost:8000/api/v1/epc/search?q=10+Downing+Street,+SW1A+2AA"

    EPC Certificate:
        curl "http://localhost:8000/api/v1/epc/certificate/{lmk_key}"

    Planning Council:
        curl "http://localhost:8000/api/v1/planning/council-for-postcode?postcode=NG1+1GF"

    Property Report (full multi-source):
        curl -X POST "http://localhost:8000/api/v1/property/report" \\
          -H "Content-Type: application/json" \\
          -d '{"address": "3 Broadway, NG1 1GF"}'

    Health Check:
        curl "http://localhost:8000/api/v1/health"
    """
    print("=== HTTP API Examples ===")
    print("Start the server:")
    print("  uv run property-api")
    print()
    print("PPD Comps:")
    print('  curl "http://localhost:8000/api/v1/ppd/comps?postcode=NG1+1GF&months=24&limit=5"')
    print()
    print("Rightmove Listings:")
    print('  curl "http://localhost:8000/api/v1/rightmove/search-url?postcode=NG1+1GF&property_type=sale"')
    print()
    print("EPC Search:")
    print('  curl "http://localhost:8000/api/v1/epc/search?q=10+Downing+Street,+SW1A+2AA"')
    print()
    print("Property Report:")
    print('  curl -X POST "http://localhost:8000/api/v1/property/report" \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"address": "3 Broadway, NG1 1GF"}\'')
    print()
    print("See docstring for full endpoint list.")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
EXAMPLES = {
    "ppd": [example_ppd_comps, example_ppd_comps_with_address, example_ppd_transactions],
    "rightmove": [example_rightmove_sales, example_rightmove_rentals, example_rightmove_detail],
    "rental": [example_rental_analysis],
    "yield": [example_yield_analysis],
    "postcode": [example_postcode],
    "planning": [example_planning],
    "address": [example_address_parsing],
    "stamp-duty": [example_stamp_duty],
    "blocks": [example_block_analyzer],
    "companies": [example_companies_house],
    "api": [example_api],
}

ALL_EXAMPLES = [
    example_ppd_comps,
    example_ppd_comps_with_address,
    example_ppd_transactions,
    example_postcode,
    example_address_parsing,
    example_rightmove_sales,
    example_rightmove_rentals,
    example_rightmove_detail,
    example_rental_analysis,
    example_yield_analysis,
    example_planning,
    example_stamp_duty,
    example_block_analyzer,
    example_companies_house,
    example_api,
]


def main():
    args = sys.argv[1:]
    if not args:
        targets = ALL_EXAMPLES
    else:
        targets = []
        for arg in args:
            if arg in EXAMPLES:
                targets.extend(EXAMPLES[arg])
            else:
                print(f"Unknown example: {arg}")
                print(f"Available: {', '.join(EXAMPLES.keys())}")
                sys.exit(1)

    for fn in targets:
        print()
        try:
            fn()
        except Exception as e:
            print(f"  ERROR: {e}")
        print()
        print("-" * 60)


if __name__ == "__main__":
    main()
