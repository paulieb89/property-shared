# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a lightweight Python wrapper for HM Land Registry Price Paid Data (PPD) APIs. It provides:
- CSV/TXT download helpers for bulk data from S3
- Linked Data API access for individual transaction/address lookups
- SPARQL search for filtered queries

**No external dependencies** - uses Python 3 stdlib only (urllib, json, pathlib, dataclasses).

## Running the Code

No build or install required. Import directly:
```python
from ppd_client import PricePaidDataClient
client = PricePaidDataClient()
```

Type checking:
```bash
mypy ppd_client.py
```

## Architecture

Single module `ppd_client.py` with one dataclass `PricePaidDataClient` that wraps three distinct APIs:

1. **S3 Downloads** (`complete_url`, `year_url`, `monthly_change_url`, `download_to_file`)
   - Files at `prod2.publicdata.landregistry.gov.uk` S3 bucket
   - Years 2018-2023 have `-part1`/`-part2` variants

2. **Linked Data** (`get_transaction_record`, `get_address`)
   - JSON endpoints at `landregistry.data.gov.uk/data/ppi/`
   - Transaction IDs are UUIDs, addresses can be URIs or IDs

3. **SPARQL** (`sparql_search`)
   - Endpoint at `landregistry.data.gov.uk/landregistry/sparql`
   - `postcode` for exact match (uses VALUES clause), `postcode_prefix` for sector/district (uses STRSTARTS)
   - Returns full address: paon, saon, street, town, county
   - Uses URI mappings for property type (D/S/T/F/O), estate type (F/L), transaction category (A/B), record status (A/C/D)

4. **Comps Helper** (`get_comps_summary`)
   - Main use case for estate agents pricing listings
   - Searches by postcode/sector/district, filters by property type client-side
   - Returns median, mean, min, max, transaction list, thin_market flag

## Examples

See `examples/` directory for usage patterns. Run with:
```bash
cd examples && uv run python 03_comps_for_listing.py
```

## Data Format

Downloaded CSV/TXT files have no headers. Column order:
1. Transaction ID, 2. Price, 3. Date, 4. Postcode, 5. Property type, 6. Old/New, 7. Tenure, 8-14. Address fields, 15. PPD category, 16. Record status (monthly only)
