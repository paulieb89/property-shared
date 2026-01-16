# HM Land Registry Price Paid Data wrapper

Small helper around the public Price Paid Data (PPD) feeds and linked data API so projects can fetch files or query a handful of transactions without re-learning the endpoints.

## What’s here
- `ppd_client.py`: download helper, linked-data fetchers, and a light SPARQL query helper.
- No external dependencies; uses Python 3 stdlib HTTP clients.

## Download endpoints
All CSV/TXT files live on the S3-backed `prod2.publicdata.landregistry.gov.uk` host.
- Complete dataset: `pp-complete.csv` (~5GB) or `pp-complete.txt`
- Yearly: `pp-YYYY.csv|txt` (2018–2023 also have `-part1` / `-part2` variants)
- Change-only monthly refresh: `pp-monthly-update-new-version.csv` (add/change/delete records since the last release)

The client builds the URLs for you:
```python
from ppd_client import PricePaidDataClient

client = PricePaidDataClient()
client.download_to_file(client.year_url(2024), "data/pp-2024.csv")
client.download_to_file(client.monthly_change_url(), "data/pp-monthly-update.csv")
# Huge file – only grab if you really need it
# client.download_to_file(client.complete_url(), "data/pp-complete.csv")
```

## Linked data helpers
Look up a specific transaction or address without pulling whole CSVs:
```python
txn = client.get_transaction_record("702EF0D1-AB60-4A1B-A2A1-C127E1EDE547")
address_uri = txn["result"]["primaryTopic"]["propertyAddress"]
address = client.get_address(address_uri)
print(address["result"]["primaryTopic"]["postcode"])
```

## SPARQL search (small slices only)
The public SPARQL endpoint can return small filtered sets; keep limits tiny because broad queries are slow.
```python
# Exact postcode search
rows = client.sparql_search(postcode="DE12 6DZ", limit=5)

# Sector search (DE12 6) or district search (DE12)
rows = client.sparql_search(postcode_prefix="DE12 6", limit=10)

for binding in rows["results"]["bindings"]:
    print(binding["transactionDate"]["value"], binding["pricePaid"]["value"])
    # Address fields included: paon, saon, street, town, county
```

Filter parameters map to the published codes:
- Property type `D/S/T/F/O` → detached / semi-detached / terraced / flat-maisonette / other
- Estate type `F/L` → freehold / leasehold
- Transaction category `A/B` → standard / additional price paid
- Record status (change file) `A/C/D` → add / change / delete

## Comparable sales helper
For estate agents pricing new listings - get recent sales with stats:
```python
comps = client.get_comps_summary(
    postcode="DE12 6DZ",
    property_type="D",      # Detached only
    months=24,              # Last 2 years
    limit=20,
    search_level="sector"   # "postcode", "sector" (DE12 6), or "district" (DE12)
)
print(f"Median: £{comps['median']:,}")  # £372,500
print(f"Count: {comps['count']}")        # 20
print(f"Thin market: {comps['thin_market']}")  # True if < 5 results
```

## Examples
See `examples/` directory for complete usage examples:
- `01_basic_search.py` - Exact postcode, district, and sector searches
- `02_filtered_search.py` - Filter by property type, price, date, tenure
- `03_comps_for_listing.py` - Get comps for a new listing (main use case)
- `04_area_overview.py` - Market overview across multiple areas
- `05_transaction_details.py` - Full transaction and address details

Run with: `cd examples && uv run python 01_basic_search.py`

## Column order (CSV/TXT downloads)
The raw files ship without headers; columns are always in this order:
1. Transaction unique identifier
2. Price
3. Date of transfer (YYYY-MM-DD)
4. Postcode
5. Property type (D, S, T, F, O)
6. Old/New flag (Y = new build, N = existing)
7. Duration / tenure (F = freehold, L = leasehold, etc.)
8. PAON (building number/name)
9. SAON (unit/flat name)
10. Street
11. Locality
12. Town/City
13. District
14. County
15. PPD category type (A = standard, B = additional)
16. Record status (A, C, D) — monthly change file only

Notes:
- The two most recent months are incomplete because of registration lag.
- Category B (additional price paid) is available from Oct 2013 onward.
- Monthly change files include additions/changes/deletions and must be merged into your stored copy.
