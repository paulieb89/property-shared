"""Get an overview of multiple areas - useful for market reports."""

import sys
sys.path.insert(0, "..")

from ppd_client import PricePaidDataClient

client = PricePaidDataClient()

# Compare multiple postcode districts in South Derbyshire area
areas = ["DE11", "DE12", "DE65", "DE73"]

print("=== South Derbyshire Area Overview (Last 12 months) ===")
print()
print(f"{'District':<10} {'Count':>8} {'Median':>12} {'Mean':>12} {'Range':<25}")
print("-" * 70)

for district in areas:
    comps = client.get_comps_summary(
        postcode=f"{district} 1AA",  # Dummy postcode, we use district level
        months=12,
        limit=200,
        search_level="district"
    )

    if comps['count'] > 0:
        median = f"£{comps['median']:,}"
        mean = f"£{comps['mean']:,}"
        range_str = f"£{comps['min']:,} - £{comps['max']:,}"
    else:
        median = mean = "N/A"
        range_str = "No data"

    print(f"{district:<10} {comps['count']:>8} {median:>12} {mean:>12} {range_str:<25}")

print()
print()

# Break down by property type for one area
print("=== DE12 by Property Type (Last 24 months) ===")
print()

property_types = {
    "D": "Detached",
    "S": "Semi-detached",
    "T": "Terraced",
    "F": "Flat/Maisonette",
}

print(f"{'Type':<15} {'Count':>8} {'Median':>12} {'Mean':>12}")
print("-" * 50)

for code, name in property_types.items():
    comps = client.get_comps_summary(
        postcode="DE12 1AA",
        property_type=code,
        months=24,
        limit=200,
        search_level="district"
    )

    if comps['count'] > 0:
        median = f"£{comps['median']:,}"
        mean = f"£{comps['mean']:,}"
    else:
        median = mean = "N/A"

    print(f"{name:<15} {comps['count']:>8} {median:>12} {mean:>12}")
