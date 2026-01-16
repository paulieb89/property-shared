"""Basic SPARQL search examples."""

import sys
sys.path.insert(0, "..")

from ppd_client import PricePaidDataClient

client = PricePaidDataClient()

# Search by exact postcode
print("=== Exact postcode search ===")
results = client.sparql_search(postcode="DE12 6DZ", limit=5)
for r in results["results"]["bindings"]:
    print(f"£{int(r['pricePaid']['value']):,} - {r['postcode']['value']} - {r['transactionDate']['value']}")

print()

# Search by postcode district (all DE12)
print("=== District search (DE12) ===")
results = client.sparql_search(postcode_prefix="DE12", limit=5)
for r in results["results"]["bindings"]:
    print(f"£{int(r['pricePaid']['value']):,} - {r['postcode']['value']} - {r['transactionDate']['value']}")

print()

# Search by postcode sector (DE12 6)
print("=== Sector search (DE12 6) ===")
results = client.sparql_search(postcode_prefix="DE12 6", limit=5)
for r in results["results"]["bindings"]:
    print(f"£{int(r['pricePaid']['value']):,} - {r['postcode']['value']} - {r['transactionDate']['value']}")
