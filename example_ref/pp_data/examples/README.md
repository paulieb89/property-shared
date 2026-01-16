# PPD Client Examples

Run from this directory:

```bash
cd examples
uv run python 01_basic_search.py
```

## Examples

| File | Description |
|------|-------------|
| `01_basic_search.py` | Basic SPARQL searches - exact postcode, district, sector |
| `02_filtered_search.py` | Filter by property type, price range, date, tenure |
| `03_comps_for_listing.py` | Get comparable sales for a new listing (main use case) |
| `04_area_overview.py` | Market overview across multiple areas |
| `05_transaction_details.py` | Look up full details for a specific transaction |

## Property Type Codes

| Code | Type |
|------|------|
| D | Detached |
| S | Semi-detached |
| T | Terraced |
| F | Flat/Maisonette |
| O | Other |

## Estate Type Codes

| Code | Type |
|------|------|
| F | Freehold |
| L | Leasehold |

## Search Levels

| Level | Example | Use Case |
|-------|---------|----------|
| `postcode` | Exact "DE12 6DZ" | Specific street |
| `sector` | "DE12 6" | ~3,000 addresses, good for comps |
| `district` | "DE12" | ~30,000 addresses, area stats |

## Notes

- The Land Registry SPARQL endpoint can be slow/flaky - expect occasional 503 errors
- Keep limits reasonable (< 200) for SPARQL queries
- For bulk data, use the CSV download methods instead
