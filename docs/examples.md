# Property Core — Examples

Copy-paste examples for using `property_core` as a library and the HTTP API.
Real output captured from NG1 1GF (Nottingham city centre).

---

## PPD Comparable Sales

```python
from property_core import PPDService

ppd = PPDService()
result = ppd.comps(postcode="NG1 1GF", months=24, limit=5)

print(result.count)          # 5
print(result.median)         # 160000
print(result.mean)           # 138000
print(result.min)            # 55000
print(result.max)            # 210000
print(result.percentile_25)  # 72500
print(result.percentile_75)  # 192500
print(result.thin_market)    # False

for t in result.transactions:
    print(t.date, t.price, t.paon, t.street, t.postcode, t.property_type)
```

Output:
```
Count: 5
Median: £160,000
Mean: £138,000
Range: £55,000 - £210,000
P25/P75: £72,500 / £192,500

2025-12-05  £160,000  THE ESTABLISHMENT, 3 BROADWAY, NG1 1PR  (F)
2025-12-04  £210,000  1A HOLLOWSTONE, NG1 1JH  (F)
2025-11-27  £55,000   THE ICE HOUSE BELWARD STREET, NG1 1JW  (F)
```

---

## PPD Comps with Address Match

Pass `address` to identify the subject property within comps and get relative stats.

```python
result = ppd.comps(postcode="NG1 1GF", months=24, limit=10, address="3 Broadway")

sp = result.subject_property
print(sp.address)                    # THE ESTABLISHMENT, 3 BROADWAY
print(sp.last_sale.price)            # 160000
print(sp.last_sale.date)             # 2025-12-05
print(sp.transaction_count)          # 1
print(result.subject_vs_median_pct)  # 7.6 (% above median)
print(result.subject_price_percentile)  # 54
```

---

## PPD Transaction Search

```python
ppd = PPDService()
txns = ppd.search_transactions(postcode="NG1 1GF", postcode_prefix=None, limit=5)

print(txns["count"])  # 1
for t in txns["results"]:
    print(t.date, t.price, t.paon, t.street, t.postcode)
```

Output:
```
2021-04-19  £1,350,000  BIOCITY NOTTINGHAM PENNYFOOT STREET, NG1 1GF
```

---

## Rightmove Sale Listings

```python
from property_core import RightmoveLocationAPI, fetch_listings

rm = RightmoveLocationAPI()
url = rm.build_search_url("NG1 1GF", property_type="sale", radius=0.5)
listings = fetch_listings(url, max_pages=1)

print(len(listings))  # 25

for l in listings:
    print(l.price, l.bedrooms, l.property_type, l.address)
    print(l.agent_name, l.listing_status, l.first_visible_date)
```

Output:
```
25 listings found
£112,000   2bed flat — Huntingdon Street, Nottingham, NG1
£1,100,000 5bed terraced house — Kirk House, Ristes Place, Nottingham
£475,000   6bed block of apartments — St Stephens Road, Sneinton
```

---

## Rightmove Rental Listings

```python
url = rm.build_search_url("NG1 1GF", property_type="rent", radius=0.5)
listings = fetch_listings(url, max_pages=1)

for l in listings:
    print(l.price, l.price_frequency, l.bedrooms, l.address)
```

Output:
```
£1,330 monthly  2bed — Crocus Street, Nottingham, NG2
£872   monthly  2bed — Short Stairs, The Gatehouse, NG1
£495   weekly   5bed — Flat 2 1 Barker Gate, Nottingham
```

---

## Rightmove Listing Detail

Pass a listing ID (string) from search results to get full details.

```python
from property_core import fetch_listing

detail = fetch_listing(str(listings[0].id))

print(detail.address)          # Queens Road, Nottingham, NG2
print(detail.price)            # 100000
print(detail.property_type)    # Flat
print(detail.bedrooms)         # 1
print(detail.bathrooms)        # 1
print(detail.display_size)     # Ask agent
print(detail.tenure_type)      # LEASEHOLD
print(detail.council_tax_band) # B
print(detail.key_features)     # ['Third Floor Flat', 'Double Bedroom', ...]

for s in detail.nearest_stations:
    print(s["name"], s["distance"])
    # Nottingham Station  0.2
    # Station St Tram Stop  0.2
```

---

## Rental Analysis (async)

IQR-filtered rental stats for an area. Handles weekly-to-monthly conversion automatically.

```python
import asyncio
from property_core import analyze_rentals

rental = asyncio.run(analyze_rentals("NG1 1GF", radius=0.5))

print(rental.rental_listings_count)  # 25
print(rental.median_rent_monthly)    # 1025
print(rental.average_rent_monthly)   # 1178
print(rental.rent_range_low)         # 350
print(rental.rent_range_high)        # 1470
```

---

## Yield Analysis (async)

Combines PPD median sale price with Rightmove median rent to calculate gross yield.

```python
from property_core import calculate_yield

y = asyncio.run(calculate_yield("NG1 1GF", months=24, radius=0.5))

print(y.postcode)            # NG1 1GF
print(y.median_sale_price)   # 148750
print(y.sale_count)          # 50
print(y.median_monthly_rent) # 1000
print(y.rental_count)        # 25
print(y.gross_yield_pct)     # 8.07
print(y.thin_market)         # False

# Interpret helpers (opt-in labels — core returns raw numbers only)
from property_core import classify_yield, classify_data_quality
print(classify_yield(y.gross_yield_pct))                      # strong
print(classify_data_quality(y.sale_count, y.rental_count))    # good
```

---

## Postcode Lookup

```python
from property_core import PostcodeClient

pc = PostcodeClient()
result = pc.lookup("SW1A 2AA")

print(result.postcode)        # SW1A 2AA
print(result.admin_district)  # Westminster
print(result.region)          # London
print(result.country)         # England
print(result.latitude)        # 51.503541
print(result.longitude)       # -0.12767
print(result.rural_urban)     # Urban: Nearer to a major town or city
```

---

## Planning Council Lookup

Find the planning portal for any UK postcode (99 verified councils).

```python
from property_core import PlanningService

ps = PlanningService()
result = ps.council_for_postcode("NG1 1GF")

c = result["council"]
print(c["name"])      # Nottingham
print(c["code"])      # nottingham
print(c["system"])    # idox
print(c["base_url"])  # http://publicaccess.nottinghamcity.gov.uk/online-applications/
print(c["status"])    # verified

la = result["local_authority"]
print(la["region"])   # East Midlands
```

---

## Address Parsing

```python
from property_core.address_matching import parse_address

parse_address("10 Downing Street, SW1A 2AA")   # ('SW1A 2AA', '10 Downing Street')
parse_address("Flat 3, 42 Baker Street, NW1 6XE")  # ('NW1 6XE', 'Flat 3, 42 Baker Street')
parse_address("SW1A2AA")                        # ('SW1A 2AA', None)
parse_address("not a postcode")                 # (None, None)
```

---

## HTTP API

Start the server:

```bash
uv run property-api                         # production
uv run uvicorn app.main:app --reload        # dev mode
```

### PPD Comps

```bash
curl "http://localhost:8000/api/v1/ppd/comps?postcode=NG1+1GF&months=24&limit=5"
```

### PPD Comps with Address Match

```bash
curl "http://localhost:8000/api/v1/ppd/comps?postcode=NG1+1GF&address=3+Broadway&months=24"
```

### PPD Comps with EPC Enrichment

```bash
curl "http://localhost:8000/api/v1/ppd/comps?postcode=NG1+1GF&enrich_epc=true"
```

### PPD Transactions

```bash
curl "http://localhost:8000/api/v1/ppd/transactions?postcode=NG1+1GF&limit=5"
```

### Rightmove Search URL

```bash
curl "http://localhost:8000/api/v1/rightmove/search-url?postcode=NG1+1GF&property_type=sale&radius=0.5"
```

### EPC Search (combined address query)

```bash
curl "http://localhost:8000/api/v1/epc/search?q=10+Downing+Street,+SW1A+2AA"
```

### EPC Certificate by Key

```bash
curl "http://localhost:8000/api/v1/epc/certificate/{lmk_key}"
```

### Planning Council

```bash
curl "http://localhost:8000/api/v1/planning/council-for-postcode?postcode=NG1+1GF"
```

### Property Report (full multi-source)

```bash
curl -X POST "http://localhost:8000/api/v1/property/report" \
  -H "Content-Type: application/json" \
  -d '{"address": "3 Broadway, NG1 1GF"}'
```

### Health Check

```bash
curl "http://localhost:8000/api/v1/health"
```
