# Phase 3 Plan — API Refinements & User-Centric Endpoints

Goal: Make the API more intuitive for real-world use cases. Users typically work with **specific addresses**, not just postcodes. Align CLI parity with API and add cross-service aggregation.

## Current State (Post Phase 2)

**Working endpoints:**
- PPD: `/comps`, `/transactions`, `/address-search`, `/transaction/{id}`, `/download-url`
- EPC: `/search`
- Rightmove: `/search-url`, `/listings`
- Planning: `/scrape`, `/probe`, `/councils`, `/council/{code}`
- Meta: `/health`, `/integrations`

**Deployment constraints:**
- PPD, EPC, Rightmove: Work from cloud/datacenter
- Planning: Residential IP only (UK councils block datacenters)

## Issues Identified

### 1. CLI vs API Gaps
| Endpoint | API | CLI | Status |
|----------|-----|-----|--------|
| `ppd address-search` | ✅ | ❌ | Missing |
| `ppd download-url` | ✅ | ❌ | Missing |

### 2. Address-First Design Missing
Users think in addresses ("10 Downing Street, SW1A 2AA"), not postcodes. Current API requires:
- EPC: postcode required, address is just a filter
- PPD comps: postcode only, no address context
- Planning: exact URL required, no postcode search

### 3. No Cross-Service Aggregation
No way to get "all data for this property" in one call.

## Phase 3A: Quick Wins (CLI Parity)

### 3A.1 Add `ppd address-search` CLI command
```bash
property-cli ppd address-search --postcode SW1A --street "Downing Street" --paon 10
```

### 3A.2 Add `ppd download-url` CLI command
```bash
property-cli ppd download-url --kind monthly --year 2024 --month 6
```

## Phase 3B: Address Context for Comps

### Current
```
GET /v1/ppd/comps?postcode=SW1A+2AA&months=24
```
Returns generic area comps with no context about the subject property.

### Proposed
```
GET /v1/ppd/comps?postcode=SW1A+2AA&address=10+Downing+Street&months=24
```
Returns:
```json
{
  "query": { ... },
  "subject_property": {
    "address": "10 Downing Street, SW1A 2AA",
    "last_sale": { "price": 1200000, "date": "2015-03-01" },
    "transaction_history": [ ... ]
  },
  "comps": [ ... ],
  "stats": { "median": 850000, "mean": 920000, ... }
}
```

**Implementation:**
1. Add optional `address` param to `/ppd/comps`
2. If provided, search PPD for that specific address
3. Include `subject_property` in response with full transaction history
4. Filter comps to exclude subject property transactions

## Phase 3C: EPC Direct Lookup

### 3C.1 Certificate by hash
```
GET /v1/epc/certificate/{certificate_hash}
```
Direct lookup when user has the certificate reference.

### 3C.2 Flexible address input
Parse "10 Downing Street, SW1A 2AA" into components:
```
GET /v1/epc/search?q=10+Downing+Street,+SW1A+2AA
```
Internally splits into postcode + address filter.

## Phase 3D: Planning Search by Location

### Current
Must know exact council URL:
```
POST /v1/planning/scrape { "url": "https://westminster.gov.uk/planning/app/12345" }
```

### Proposed
Search by postcode (uses council lookup):
```
GET /v1/planning/search?postcode=SW1A+2AA&radius_km=0.5&days=90
```
Returns:
```json
{
  "council": { "name": "Westminster", "code": "westminster", "system": "idox" },
  "applications": [
    { "reference": "24/00123/FUL", "address": "12 Downing St", "status": "Pending", "url": "..." },
    { "reference": "24/00089/LBC", "address": "8 Downing St", "status": "Approved", "url": "..." }
  ],
  "note": "Scraped from council search page. Use /scrape for full details."
}
```

**Implementation:**
1. Map postcode to council (use existing `planning_councils.json` or postcode API)
2. Scrape council's search results page (not individual apps)
3. Return list of applications with basic info + URLs for deep scrape

**Constraint:** Only works from residential IP (same as scrape).

## Phase 3E: Unified Property Endpoint

Single endpoint aggregating all services:
```
GET /v1/property?postcode=SW1A+2AA&address=10+Downing+Street
```

Returns:
```json
{
  "address": {
    "formatted": "10 Downing Street, London, SW1A 2AA",
    "postcode": "SW1A 2AA",
    "street": "Downing Street",
    "paon": "10",
    "town": "London"
  },
  "epc": {
    "available": true,
    "rating": "D",
    "score": 54,
    "potential_rating": "C",
    "inspection_date": "2020-03-15",
    "certificate_hash": "abc123..."
  },
  "ppd": {
    "available": true,
    "transaction_count": 3,
    "last_sale": { "price": 1200000, "date": "2015-03-01" },
    "transactions": [ ... ]
  },
  "comps": {
    "count": 12,
    "median": 950000,
    "search_level": "sector"
  },
  "rightmove": {
    "currently_listed": false,
    "last_check": "2024-01-21T10:00:00Z"
  },
  "planning": {
    "council": "westminster",
    "recent_applications": 0,
    "note": "Planning search requires residential IP"
  }
}
```

**Implementation:**
1. Parse and normalize address input
2. Call EPC, PPD, Rightmove in parallel
3. Planning: return council info only (search requires residential IP)
4. Handle partial failures gracefully (return available data)

## Phase 3F: Postcode-to-Council Mapping

Enable planning search without knowing the council:
```
GET /v1/planning/council-for-postcode?postcode=SW1A+2AA
```
Returns:
```json
{
  "postcode": "SW1A 2AA",
  "council": {
    "name": "City of Westminster",
    "code": "westminster",
    "system": "idox",
    "planning_url": "https://idoxpa.westminster.gov.uk/online-applications/",
    "status": "verified"
  }
}
```

**Implementation options:**
1. Use gov.uk postcode lookup API (free, reliable)
2. Build local postcode-to-council mapping table
3. Hybrid: cache results from gov.uk API

## Implementation Order

| Phase | Effort | Dependencies | Priority |
|-------|--------|--------------|----------|
| 3A: CLI parity | 1 day | None | P1 - Do first |
| 3B: Comps with address | 1 day | None | P1 - High value |
| 3C: EPC direct lookup | 0.5 day | None | P2 |
| 3F: Postcode-to-council | 1 day | None | P2 - Enables 3D |
| 3D: Planning search | 2 days | 3F | P2 |
| 3E: Unified property | 2-3 days | 3B, 3C | P3 - Capstone |

## API Versioning Note

All new endpoints go under `/v1/`. Breaking changes to existing endpoints:
- Add new optional params (backward compatible)
- New response fields are additive (backward compatible)
- If breaking change needed, add `/v2/` endpoint and deprecate old

## Success Criteria

- [x] CLI has full parity with API
- [x] User can search PPD comps with subject property context
- [x] User can look up EPC by certificate hash
- [ ] User can find planning apps by postcode (residential IP)
- [ ] User can get all property data in one call

## Out of Scope (Phase 4+)

- Authentication / API keys
- Rate limiting / quotas
- Caching layer (Redis)
- Webhook notifications for planning updates
- Historical price trends / charts
- PyPI package publication
- Desktop GUI / Electron app
