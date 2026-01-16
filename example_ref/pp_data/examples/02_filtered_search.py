"""Filtered search examples - by property type, price, date."""

import sys
sys.path.insert(0, "..")

from ppd_client import PricePaidDataClient

client = PricePaidDataClient()

# Detached houses only
print("=== Detached houses in DE12 ===")
results = client.sparql_search(
    postcode_prefix="DE12",
    property_type="D",
    limit=5
)
for r in results["results"]["bindings"]:
    print(f"£{int(r['pricePaid']['value']):,} - {r['postcode']['value']} - {r['transactionDate']['value']}")

print()

# Semi-detached in price range
print("=== Semi-detached £200k-£300k in DE11 ===")
results = client.sparql_search(
    postcode_prefix="DE11",
    property_type="S",
    min_price=200000,
    max_price=300000,
    limit=5
)
for r in results["results"]["bindings"]:
    print(f"£{int(r['pricePaid']['value']):,} - {r['postcode']['value']} - {r['transactionDate']['value']}")

print()

# Recent sales only (last 6 months)
print("=== Sales in last 6 months (DE65) ===")
from datetime import date, timedelta
six_months_ago = (date.today() - timedelta(days=180)).isoformat()

results = client.sparql_search(
    postcode_prefix="DE65",
    from_date=six_months_ago,
    limit=5
)
for r in results["results"]["bindings"]:
    print(f"£{int(r['pricePaid']['value']):,} - {r['postcode']['value']} - {r['transactionDate']['value']}")

print()

# Freehold only
print("=== Freehold properties in DE12 ===")
results = client.sparql_search(
    postcode_prefix="DE12",
    estate_type="F",  # F = freehold, L = leasehold
    limit=5
)
for r in results["results"]["bindings"]:
    print(f"£{int(r['pricePaid']['value']):,} - {r['postcode']['value']} - {r['transactionDate']['value']}")
