"""Look up full details for a specific transaction.

Shows how SPARQL results now include address fields directly,
plus how to use the Linked Data API for additional details.
"""

import sys
sys.path.insert(0, "..")

from ppd_client import PricePaidDataClient

client = PricePaidDataClient()

# First, find a transaction
print("=== Finding a recent transaction ===")
results = client.sparql_search(postcode_prefix="DE12", limit=1)

if not results["results"]["bindings"]:
    print("No results found")
    sys.exit(1)

first = results["results"]["bindings"][0]
tx_id = first["transactionId"]["value"]

print(f"Transaction ID: {tx_id}")
print(f"Price: £{int(first['pricePaid']['value']):,}")
print(f"Date: {first['transactionDate']['value']}")
print(f"Postcode: {first['postcode']['value']}")
print()

# Address fields are now included in SPARQL results
print("=== Address (from SPARQL) ===")
print(f"PAON: {first.get('paon', {}).get('value', 'N/A')}")
print(f"SAON: {first.get('saon', {}).get('value', 'N/A')}")
print(f"Street: {first.get('street', {}).get('value', 'N/A')}")
print(f"Town: {first.get('town', {}).get('value', 'N/A')}")
print(f"County: {first.get('county', {}).get('value', 'N/A')}")
print()

# Get full transaction record from Linked Data API
print("=== Full Transaction Record (Linked Data API) ===")
try:
    record = client.get_transaction_record(tx_id)
    topic = record.get("result", {}).get("primaryTopic", {})

    price = topic.get('pricePaid')
    print(f"Price paid: £{price:,}" if isinstance(price, int) else f"Price paid: {price}")
    print(f"Transaction date: {topic.get('transactionDate', 'N/A')}")
    print(f"New build: {topic.get('newBuild', 'N/A')}")

    # Property type from Linked Data
    prop_type = topic.get('propertyType', {})
    if isinstance(prop_type, dict):
        print(f"Property type: {prop_type.get('label', 'N/A')}")

except Exception as e:
    print(f"Could not fetch transaction details: {e}")
