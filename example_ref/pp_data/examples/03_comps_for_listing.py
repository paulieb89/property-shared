"""Get comparable sales for a new property listing.

This is the main use case for estate agents - when you get a new listing,
find similar recent sales to help price it.
"""

import sys
import time
from urllib.error import HTTPError, URLError

sys.path.insert(0, "..")

from ppd_client import PricePaidDataClient


def with_retry(fn, retries=5, delay=3):
    """Retry a function on 503/network errors with exponential backoff."""
    for attempt in range(retries):
        try:
            return fn()
        except HTTPError as e:
            if e.code == 503 and attempt < retries - 1:
                wait = delay * (attempt + 1)  # 3, 6, 9, 12 seconds
                print(f"  (503 error, attempt {attempt + 1}/{retries}, retrying in {wait}s...)")
                time.sleep(wait)
                continue
            raise
        except URLError as e:
            if attempt < retries - 1:
                wait = delay * (attempt + 1)
                print(f"  (Network error, attempt {attempt + 1}/{retries}, retrying in {wait}s...)")
                time.sleep(wait)
                continue
            raise


client = PricePaidDataClient()

# Scenario: New listing at 14 High Street, Swadlincote, DE12 6DZ
# It's a detached house, client wants to know what similar properties sold for

print("=== Comps for new listing: DE12 6DZ (Detached) ===")
print()

comps = with_retry(lambda: client.get_comps_summary(
    postcode="DE12 6DZ",
    property_type="D",      # Detached
    months=24,              # Last 2 years
    limit=20,               # Up to 20 comps
    search_level="sector"   # DE12 6 area
))

# Summary stats
print(f"Found {comps['count']} comparable sales")
print(f"Median price: £{comps['median']:,}" if comps['median'] else "No data")
print(f"Mean price:   £{comps['mean']:,}" if comps['mean'] else "No data")
print(f"Range:        £{comps['min']:,} - £{comps['max']:,}" if comps['min'] else "No data")
print(f"Thin market:  {comps['thin_market']}")  # Warning if < 5 results
print()

# Recent transactions
print("Recent sales:")
for t in comps['transactions'][:10]:
    tenure = "Freehold" if t['estate_type'] == 'F' else "Leasehold"
    new = " (new build)" if t['new_build'] else ""
    print(f"  £{t['price']:,} - {t['postcode']} - {t['date']} - {tenure}{new}")

print()
print("---")
print()

# Try different search levels
print("=== Comparing search levels ===")
print()

for level in ["postcode", "sector", "district"]:
    comps = with_retry(lambda lvl=level: client.get_comps_summary(
        postcode="DE12 6DZ",
        property_type="D",
        months=24,
        search_level=lvl
    ))
    median_str = f"£{comps['median']:,}" if comps['median'] else "N/A"
    print(f"{level:12} -> {comps['count']:3} results, median {median_str}")
