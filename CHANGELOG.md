# Changelog

## v1.14.1 (2026-08-26) — EPC hotfix: legacy SAP scalar cost fields

**v1.14.0 returned HTTP 503 for every certificate on SAP-Schema-13.0, 14.0, 14.2 and 15.0.** Found by production dogfooding minutes after release:

```
503  "EPC service unavailable: heating_cost_current: expected {value, currency}, got int 267"
```

### Cause
The money shape is a property of the **schema**, not the field — an audit of all six cost fields across the eleven saved schema captures shows they move together:

| Schema | cost fields |
|---|---|
| RdSAP 17.0 / 17.1 / 18.0 / 19.0 / 20.0.0, SAP 16.0 / 16.2 | `{value, currency}` |
| **SAP 13.0 / 14.0 / 14.2 / 15.0** | **bare number** |

`EPCMoney.from_source` accepted only the object form and raised `EPCUpstreamShapeError`, which subclasses `EPCUpstreamError` and therefore surfaced as 503. That broke certificate lookup, exact-address search, comps enrichment, the report service and both MCP surfaces for those schemas. Area summaries were unaffected, as they fetch no certificate.

The evidence was present in the probe captures used to build the migration; the model was written without checking them.

### Fixed
- **Bare numbers are accepted.** The source model records that upstream stated no currency (`currency=None`, `currency_stated=False`) and does **not** rewrite the raw shape into a fabricated `{"currency": "GBP"}` object.
- **The v1 projection keeps the amount** and reads it as GBP — the same representation the retired v1 field used, on a register scoped to England and Wales — emitting **one aggregated warning per certificate** naming the inference. Not one per field: all six cost fields share a schema's shape, so per-field warnings would repeat the same sentence six times.
- **Malformed money is still rejected**: `bool` (checked explicitly, since `isinstance(True, int)` is `True` in Python), strings, lists, empty objects, missing `value`/`currency`, non-numeric values, and empty currency. A stated non-GBP currency still suppresses the legacy scalar with its existing warning.

### Tests
- Sanitised fixtures for all eleven observed schemas (`tests/fixtures/epc/`) — no real addresses, UPRNs or certificate numbers — pinning both shapes so an upstream change fails loudly.
- Regression coverage through certificate lookup, exact-address search, comps enrichment, the report service, REST, and both MCP surfaces, asserting the warning survives each without per-field spam.

## v1.14.0 (2026-08-25) — EPC restored on the GOV.UK Bearer API

Operational restoration after the retirement of `epc.opendatacommunities.org`.
**This does not claim that every historical EPC operation remains available** —
the replacement service exposes less in a search than the retired one did, and
the gaps are reported honestly rather than fabricated or hidden behind
per-certificate fan-out.

### Restored
- **Direct certificate retrieval** — `get_certificate(certificate_number)`; one upstream call (plus at most three cold codebook-table fetches).
- **Summary-native EPC search** — new `search_summaries()` returning `EPCSearchPage` (results, pagination, returned distinct count, unusable rows, duplicates removed, `complete`, warnings). One call, never any certificate fan-out.
- **Address-specific retrieval** — only when a unique candidate can be selected safely; one search plus one certificate.
- **Report and comps enrichment** — summary match first, then a single certificate fetch for the selected candidate, cached by certificate number.
- **Area count** and, when the bounded response demonstrably contains every matching summary, the area rating distribution.

### Configuration — Bearer token
- `EPC_API_TOKEN` is now required. Get one at https://get-energy-performance-data.communities.gov.uk/.
- `EPC_API_EMAIL` / `EPC_API_KEY` are **deprecated and unsupported**. They are parsed only to raise an actionable `EPCConfigurationError`; they are never used to make a request, and `is_configured()` is true only with a Bearer token. Scheduled for removal in the next breaking release.

### Deprecated / unsupported
- **`search_all_by_postcode()`** raises `EPCUnsupportedOperationError` and makes no request. Search now returns summaries with no energy score, and `EPCData.score` is a non-Optional `int` — every row would need its own certificate fetch or a fabricated `0`. Use `search_summaries()` then `get_certificate()`.
- **MCP `property_epc_search` / `epc_search` (full-row)** — replaced by `property_epc_summaries` / summary-native `epc_search`. The old tool raises with a message naming the replacement.

### Unavailable metrics (reported as `None`, never `{}` or `0`)
- `property_type_breakdown`, `floor_area_min`/`max`/`avg` — these exist only on full certificates.
- `rating_distribution` is an area-wide distribution **only** when the bounded response is complete; otherwise it is returned as a labelled sample with its sample size and `complete: false`.
- `certificates` on `/v1/epc/search-area` is `None` (not `[]`) when per-certificate detail is not returned.
- `lodgement_date`, `construction_age`, `floor_level` — no demonstrated equivalent in the new API (absent from all 11 observed schemas; no old-API capture exists to prove a `lodgement_date` mapping). Reported `None` with an explicit warning rather than guessed.

### Scope and completeness limitations
- **England and Wales only.** Scotland, Northern Ireland and the Channel Islands return "no certificates found" — a coverage boundary, not evidence about a property.
- **Pagination is not a stable snapshot.** Upstream page traversal is page-size-dependent: in one measured 200-row comparison, 7 records (3.5%) were absent from the paged union and 7 positions duplicated, all sharing the boundary `registrationDate`. Responses therefore carry `complete`, `duplicates_removed` and `unusable_rows`, and no operation claims a complete harvest.
- **Ambiguous matches are refused.** Where the legacy matcher would accept a different house on the same street, or tie-break between flats by upstream row order, selection now raises `EPCAmbiguousMatchError` and fetches nothing. Enrichment leaves such comps un-enriched rather than attaching another property's certificate.

### Fixed after adversarial review
- **Unit agreement is enforced even when one candidate remains.** A lone `Flat 3` was returned for a `Flat 2` query — narrowing to a single row said nothing about whether that row was the right property.
- **A supplied UPRN that matches nothing no longer falls back to address text.** A UPRN miss is evidence of a miss, not licence to guess.
- **`epc_match_score` is no longer 100 for a unique selection.** 100 is reserved for identity evidence (UPRN or exact address); structured narrowing reported 80 and the new `epc_match_method` field named the evidence. (Superseded in round 5: the structured path was removed, so the only scores now emitted are 100.)
- **Complete REST failure taxonomy.** Upstream 403 surfaced as HTTP 500; upstream 400 would have surfaced as 503. Now: configuration 501, authentication 502, rate limit 429, invalid query 400, ambiguity 409, unsupported operation 410, outage 503, absence 404.
- **Unknown record counts are `null`, never `0`.** Missing `totalRecords` produced HTTP 200 with `count: 0`.
- **Codebook lookups are async.** A synchronous request inside the async certificate path blocked the event loop on every cold code.
- **Warnings reach every surface.** Compatibility, codebook, currency and no-source warnings were produced and then discarded by normal `get_certificate()` calls; `EPCData.warnings` now carries them through REST, MCP and CLI.
- CLI area mode, `EPC_API_TOKEN` in application settings, a `PropertyReportService(epc_token=...)` option, and the gated live tests were all still on the retired contract.

### Fixed after review round 3
- **Street agreement must be exact.** A single shared token was treated as agreement, so a query for "12 High Street" selected the sole candidate "12 High Road" at confidence 80. Street tokens must now match exactly; abbreviations ("Rd" vs "Road") are deliberately not equated, because inferring that equivalence is a guess.
- **A sole candidate is not identity evidence.** With no address and no UPRN, the one returned row was selected as `sole_candidate`. Selection now refuses regardless of how few candidates come back.
- **Unknown record counts no longer read as absence on any surface.** `property_app/tools.py`, `app/mcp/server.py` and the CLI each collapsed a missing `totalRecords` into "no EPC data". `0` now means genuinely none; `None` means unknown, with `complete: false` and warnings preserved.
- **Codebook tables are fetched concurrently under one bounded budget.** Three sequential 15s per-request timeouts could reach ~45s, exceeding the 30s MCP tool timeout and failing an entire certificate call for a cosmetic label. Overrunning the budget degrades to `labels=None` plus a warning.
- **A certificate without `schema_type` no longer triggers an unscoped codebook query.** An unscoped lookup returns one value per schema version, and taking the first would be a guess; labels are left unresolved with an explanatory warning.
- **`EPCData.from_api_row` no longer fabricates.** The retired kebab-case parser wrote `rating=""` and `score=0` for missing values (0 being a plausible band-G score). It now raises, is documented as deprecated, and a test pins that no production path calls it.
- Documentation told users to copy a `.env.example` that does not exist; the instructions now describe creating `.env` directly, and warn that `KEY=` sets an empty string rather than leaving a variable unset — the footgun that made the EPC live tests send an empty postcode.

### Fixed after review round 4
- **Building and unit identifiers are parsed and compared independently.** A pooled set of all numbers let a shared unit mask a conflicting building: "Flat 2, 24 Alexandra Road" selected "Flat 2, 99 Alexandra Road" because both contained "2". A matching unit can no longer compensate for a mismatched building, and vice versa.
- **Codebook fetches are single-flighted per `(code, schemaVersion)`.** Four concurrent cold certificates issued twelve requests — four each for `built_form`, `property_type` and `tenure`. Concurrent callers now share one in-flight fetch, protected with `asyncio.shield` so a caller hitting the warm budget cannot tear down the fetch others are awaiting. The regression test asserts exactly one request per table rather than elapsed time, which duplicate concurrent requests would have satisfied.
- Corrected stale descriptions in `CLAUDE.md` and `property_app/tools.py` that still described EPC enrichment as fetching every certificate per postcode in one call and fuzzy-matching, and area mode as returning all certificates.

### Fixed after review round 5 — the structured matcher is removed, not repaired
Four rounds each repaired a specific way partial evidence could look sufficient, and each round a new one appeared: a shared street token, a shared unit masking a different building, a block number read as a building number, an ordinal street name reduced to its street type. Round 5 reproduced two more on `6f8fd3b` — `"Flat 2, Block 3, 24 Alexandra Road"` selected `"Flat 2, Block 3, 99 Alexandra Road"`, and `"10 1st Avenue"` selected `"10 2nd Avenue"`, both at confidence 80. Enumerating counter-examples was not converging, so the acceptance path itself is gone.

- **Selection accepts identity evidence only.** Exactly two rules: an exact UPRN match, or exact normalized full-address equality. Everything else raises `EPCAmbiguousMatchError`. Normalization covers case, punctuation and whitespace only — it preserves component order and never equates abbreviations, because that is an inference rather than a formatting difference. The helpers that produced every defect above (`_building`, `_unit`, `_street_words`, `_numbers`) are deleted, and a test pins their absence so the path cannot be reintroduced piecemeal.
- **Confidence is invariant-tested, not example-tested.** `tests/test_epc_selection_invariants.py` asserts the property rather than a list of known-bad addresses: mutating *any* component of a four-part address (unit, block, building number, ordinal street, street type, street name) must refuse; dropping, reordering or adding a component must refuse; case and punctuation differences must still match. This is what the previous rounds' example-by-example tests could not do — each passed while the next counter-example was still live.
- **One codebook attempt is one failure.** Four concurrent waiters shared a single failed HTTP request, but each waiter incremented the failure counter, so one upstream attempt recorded four failures and tripped the breaker. Fetch, cache write and failure accounting now all live in the shared loader task; waiters only consume its result. A cancelled waiter can neither tear down the shared fetch nor double-count, and a loader that fails after every waiter has gone no longer surfaces an unretrieved task exception.

#### Measured cost of the stricter selector
Measured on 12 live EPC summary searches over the 12 most-populated postcodes of a cached 400-transaction PPD capture (Birmingham B1) — 210 PPD cases against 1,063 real EPC rows, no upstream failures and no empty results:

| Selector | Matches | Rate |
|---|---|---|
| Structured (pre-round-5) | 66 / 210 | 31.4% |
| Identity-only (shipped) | 8 / 210 | 3.8% |

Every one of the 58 lost matches differs by exactly one token — PPD writes `FLAT n` where EPC writes `Apartment n` — with all numeric components identical, and none of them had a designator-swapped rival certificate in the same postcode. This is a real and large reduction in enrichment coverage, and it is not hidden: an un-enriched comp reports no EPC fields rather than another property's certificate.

### One bounded normalization, added on that evidence
A **leading** `Flat <n>` / `Apartment <n>` designator is canonicalized to a single token, and nothing else changes: every remaining token, its order, and the unit identifier must still match exactly. Matches found this way report `epc_match_method: "address_designator_normalized"`, distinct from literal `exact_address`.

Deliberate limits, each pinned by a test:
- `Flat 2` ↔ `Apartment 2` matches; `Flat 2` ↔ `Apartment 3` does not, and neither does `Flat 2` ↔ `Apartment 2a`.
- A shared unit cannot excuse a different building, street, or an added/reordered component.
- `apt` is **not** a synonym — it has not been observed in the register, and unobserved synonyms are guesses.
- The rewrite is anchored: `"Apartment Road"`, `"The Apartment, 24 High Street"` and `"24 Apartment 2 Road"` are untouched, because no unit follows or the designator is not leading.
- Abbreviations are still not equated (`Rd` ≠ `Road`).

It fails **safe**, which is the property the structured matcher never had: canonicalization can only make two addresses *collide*, and a collision is refused as ambiguous rather than tie-broken. Candidates are gathered on the canonical form first for exactly this reason — selecting on literal equality first would let one row win while a designator-variant duplicate sat unexamined beside it. Two tests cover that ordering; both failed against the first implementation, which had the passes the other way round.

Measured against the same cached corpus, zero network calls: **66/210 (31.4%)**, restoring the full structured-matcher rate, with all 66 selecting the *same certificate* the structured matcher had chosen — 8 via literal equality, 58 via the designator rule, 0 divergences, 0 canonical collisions. Corpus caveat: 12 city-centre postcodes dominated by apartment blocks are not a national sample.

### Compatibility
- v1 `EPCData` fields, types and meanings are unchanged; `lmk_key`/`certificate_hash` carry the certificate number; the MCP `epc_certificate` tool still accepts `lmk_key`.
- Coded upstream integers (`built_form`, `property_type`, `tenure`) are resolved to labels via a cached codebook, or reported `None` with a warning — never an integer in a field whose contract is a human-readable string.
- Cost fields project to the legacy integer scalar only when the currency is GBP; otherwise `None` plus a warning naming the currency. The structured `{value, currency}` is available additively.

## v1.13.1 (2026-08-24) — EPC honest-failure hotfix

### Fixed
- **EPC lookups reported service outages as "no certificate exists".** The API host hardcoded in `EPCClient.BASE_URL` (`epc.opendatacommunities.org`) has been retired and now 301-redirects. Because every failure was caught by a broad `except (httpx.HTTPError, KeyError, ValueError)` and converted to `None`/`[]`, the deployed product answered `404 "No EPC certificate found"` for **every postcode in England and Wales**, and `/v1/epc/search-area` returned **HTTP 200 with `count: 0`** — an outage rendered as valid data. MCP tools returned `null` with `isError: false` alongside docstrings telling the model "Returns None if no certificates exist", so an LLM would state that a property has no EPC.

  EPC lookups now raise `EPCUpstreamError` when the service cannot be consulted — non-success status (redirects included), transport failure, unparseable body, an unrecognised response envelope, or missing credentials. A reachable upstream holding no certificate still returns `None`/`[]`, so genuine absence is unchanged. REST maps the error to **503** (never 404, never an empty 200); MCP tools surface it as a tool error rather than a null result; tool docstrings no longer instruct consumers to infer absence.

  This is a stop-the-bleeding fix: it stops the system asserting a falsehood. **It does not restore EPC data** — the replacement GOV.UK API uses different auth, envelope, field casing and identifiers, and migrating to it is tracked separately.
- `enrich_comps_with_epc()` used `asyncio.gather` without `return_exceptions=True`. With EPC lookups now raising, a single failing postcode would have discarded every successfully-fetched postcode in the batch and propagated out of the whole comps request. Failed postcodes are now left un-enriched and logged; successful ones survive.

## v1.13.0 (2026-08-24) — security hotfix

### Security
- **Server-Side Request Forgery (SSRF) in the Rightmove fetch paths — fixed.** `fetch_listing()` passed any string beginning with `http` straight to the HTTP client with no host or scheme validation, and `fetch_listings()` accepted an arbitrary search URL. Both were reachable from unauthenticated surfaces (the `rightmove_listing` MCP tool, `GET /v1/rightmove/listings`, and `GET /v1/rightmove/listing/{id}`), giving an unauthenticated caller a server-side fetch primitive against internal addresses (verified against cloud-metadata, localhost, and userinfo-trick targets). URLs are now validated against an exact host allowlist (`property_core/url_safety.py`): https only, no userinfo, default port only, no suffix or substring host matching. Redirects are resolved and re-validated per hop instead of being followed automatically, and responses are size-capped.
- **`/img` proxy host check bypass (MCP app) — fixed.** The proxy validated with `url.startswith("https://media.rightmove.co.uk")`, which lookalike hosts (`…co.uk.evil.example`) and userinfo tricks (`…co.uk@evil.example`) both defeat. It now validates with httpx's own URL parser — the same parser that issues the request, so the two cannot disagree about the host — and follows redirects manually with per-hop re-validation. The response is streamed with a running byte cap (a buffered `get()` materialises the whole body before any size check, so the cap would not have protected the 512MB VM), non-image `Content-Type`s are refused rather than echoed back on our own origin, and `X-Content-Type-Options: nosniff` is set.

### Breaking Changes
- **REST** — `GET /v1/rightmove/listings` no longer accepts `search_url`. It now takes the same structured filters as `/v1/rightmove/search-url` (`postcode`, `property_type`, `building_type`, `min_price`, `max_price`, `min_bedrooms`, `max_bedrooms`, `radius`, `sort_by`) and builds the Rightmove URL server-side. `postcode` is required.
- **REST** — `GET /v1/rightmove/listing/{property_id}` now constrains `property_id` to 1–12 digits at the routing layer; non-numeric values return 422 instead of being fetched.
- **MCP** — the `rightmove_listing` tool parameter is renamed `property_url_or_id` → `property_id` and accepts the numeric Rightmove ID only.
- **CLI** — `property-cli rightmove listings` now takes a postcode plus filters instead of a raw search URL (e.g. `property-cli rightmove listings "SW1A 1AA" --property-type sale --radius 0.25`). `property-cli rightmove listing` takes the numeric ID only.
- **Library (source-compatible)** — `fetch_listing()` still accepts both a numeric ID **and** a canonical Rightmove listing URL (`https://www.rightmove.co.uk/properties/<id>`), and keeps its original parameter name `property_url_or_id`, so both positional and keyword callers (`fetch_listing(property_url_or_id=...)`) are unaffected. The difference is that a URL is now used *only* to extract the numeric ID: it is host/scheme-validated, the ID is parsed out, and the fetched URL is rebuilt internally — the caller's URL is never requested. Anything else (another host, a userinfo or lookalike-host trick, a non-listing path such as `/redirect?to=…`, a non-https scheme or non-default port) raises `ValueError`/`UnsafeURLError` before any request. New helper `extract_property_id()` is exported for callers that want to normalise a reference themselves.
- **Library** — `fetch_listings(search_url)` still takes a URL but validates it against the Rightmove host allowlist, raising `UnsafeURLError`. Build search URLs with `RightmoveLocationAPI.build_search_url()`.

**Upgrade note for downstream servers** (`property-descriptions-mcp`, `uk-property-mcp`): no code change is required to keep working on this release — a Rightmove listing URL passed to `fetch_listing()` is still accepted. Only non-Rightmove or non-listing URLs, which previously would have been fetched server-side, now raise.

### Fixed
- `property-cli rightmove listing` passed `include_raw=` to `fetch_listing()`, which has never accepted that parameter — the core-mode branch raised `TypeError` on every invocation. `--include-raw` now works as documented.
- `tests/test_mcp_server_epc.py` still imported `get_epc_certificate`, renamed to `epc_certificate` in v1.12.0 — two tests had been failing since that rename.
- **Incorrect EPC/MEES regulatory guidance.** Both MCP servers stated, in the `epc-ratings://reference` resource *and* in the `investment_analysis` prompt, that EPC band C has been required for new tenancies since April 2025 and that existing tenancies must comply by 2028. Verified against gov.uk: the current legal minimum for privately rented domestic property in England and Wales is band **E** (since 1 April 2020, subject to exemptions), and the proposed band C standard has a single compliance date of **1 October 2030** for all tenancies — an earlier date for new tenancies was explicitly ruled out, and the standard is not yet in force. Because this text reached users through a resource and a prompt, it could distort an analysis with no tool call involved.
- `PPDService.search_transactions(record_status=...)` / `PricePaidDataClient.sparql_search(record_status=...)` raised `AttributeError` on the first returned row. SPARQL search returns `PPDTransaction`, which has no `record_status` field — that field belongs to `PPDTransactionRecord`, built only by the Linked Data `get_transaction_record()` lookup. The parameter now raises `UnsupportedRecordStatusFilterError` (a `ValueError`) immediately, before any query is issued, pointing callers at `transaction_record()`. `GET /v1/ppd/transactions?record_status=...` returns 422 instead of a misleading 502. Real SPARQL-level record-status filtering is deliberately deferred until the triple shape is verified against the live Land Registry ontology.

### Developer Experience
- `pyproject.toml` now sets `testpaths = ["tests"]`, and `scripts/epc_token_test.py` is renamed to `scripts/measure_epc_tokens.py`. Pytest's default `*_test.py` glob was matching that script, so a bare `pytest` from the repo root would import and execute a live-network measurement script during collection.
- Documented test commands in `CLAUDE.md` and `GUIDELINES.md` were missing `--extra api`, so they could not collect `test_http_metrics.py` or `test_mcp_server.py`. All four extras (`dev`, `api`, `apps`, `cli`) are now documented.

## v1.12.0 (2026-05-17)

### Added
- `property_epc_search(postcode)` — browse all EPC certificates at a postcode as a slim list (address, rating, floor\_area, property\_type, floor\_level, habitable\_rooms, inspection\_date, lmk\_key). Designed for Rightmove listings where the house number is not shown.
- `epc_certificate(lmk_key)` — direct EPC certificate lookup by lmk\_key, faster than address-based lookup as it skips fuzzy matching. Available on both MCP servers (`property-shared.fly.dev/mcp` and `propertydata.fly.dev/mcp`).
- `RightmoveListingDetail.floor_area_sqm` / `floor_area_sqft` — numeric floor area extracted from the Rightmove `sizings` array. Key discriminator for EPC cross-referencing without address matching.

### Fixed
- `address_matching.extract_number` — now strips `FLAT N,` / `APARTMENT N,` / `UNIT N,` prefixes before extracting the building number, preventing flat EPC certs from scoring near-zero against no-house-number targets.
- `address_matching.extract_street` — now takes 3 words instead of 2, including directional qualifiers (North, South, East, West). Eliminates wrong-street false positives (e.g. "Cavendish Crescent North" vs "Cavendish Crescent South" previously both mapped to "cavendish crescent").
- `address_matching.match_epc_address` — raises minimum match threshold from 30 → 50 when the target address has no house number, since word-overlap alone is insufficient to discriminate between properties on the same street.

## v1.11.0 (2026-05-12)

### Breaking Changes
- Removed `property_report` MCP tool from `property-shared.fly.dev/mcp` and from `propertydata.fly.dev/mcp`. Also removed `get_property_data` from `propertydata.fly.dev/mcp`. Both were multi-source composition tools that hid which input produced which output and were prone to data-quality bugs (e.g. the v1.10.x yield calc was silently dividing current rent by a historical sale price).
- Replaced by a `full_property_analysis` MCP **prompt** on both servers. The prompt instructs the LLM to call the underlying primitive tools (`property_comps`/`search_comps`, `property_yield`/`get_yield`, `property_epc`/`epc_lookup`, `rightmove_search`) explicitly and synthesise. Every input is now visible in the LLM's working text.
- REST `POST /v1/property/report` and CLI `property-cli report generate` are unchanged — they call `PropertyReportService` directly without going through MCP.
- Downstream consumers (`uk-property-mcp`, `property-descriptions-mcp`): if they exposed `property_report` as a tool, that registration needs to be removed on their next release.

### Added — MCP Resources (non-breaking)
- `councils://list` — full UK planning portal registry (99 councils) as a queryable resource. LLMs can read this once instead of repeatedly calling `planning_search` for individual lookups.
- `council://{code}` — single-council profile by code/slug.
- `sdlt-bands://current` — April 2025 UK Stamp Duty Land Tax band schedule, including additional-property + non-resident surcharges and first-time buyer relief. LLMs can cite the bands directly without forcing a `stamp_duty` calculator call.
- `epc-ratings://reference` — A–G EPC band definitions, SAP score ranges, and regulatory context (April 2025 rental minimum of band C). Grounds LLM EPC explanations in canonical data rather than training-data recall. **⚠️ Correction: the regulatory claim shipped in this release was wrong — the current minimum is band E, and band C is proposed for 1 October 2030. Fixed in v1.13.0 above; this line is left as-published for history.**

### Removed — dev utilities
- `component_test` and `image_test` MCP tools removed from `propertydata.fly.dev/mcp`. These were internal dev artifacts that polluted the production tool selection surface.

### Added — MCP Prompts (non-breaking)
- `full_property_analysis` — replaces the removed `property_report` / `get_property_data` tools.
- `area_comparison` — multi-postcode comparison workflow (compares 2-3 postcodes on price, yield, market depth).
- `investment_analysis` — single-property buy-to-let evaluation (yield, SDLT, EPC compliance, key risks).

## v1.10.0 (2026-05-12)

### Breaking Changes
- REST API `/v1/ppd/comps` now defaults `auto_escalate=true`. Previously the REST API was the odd one out —  All three interfaces now behave identically: thin markets auto-widen from postcode→sector→district, with the `escalated_from`/`escalated_to` fields in the response indicating any widening that occurred. Pass `auto_escalate=false` to opt out.
- `PPDService.comps()` now defaults `transaction_category="A"` (standard residential sales). Category-B rows (bulk transfers, non-standard conveyances) are excluded unless callers explicitly opt back in via `transaction_category=None`. This fixes data-parity with the production `prop` MCP server.
- `PPDService.comps()` `property_type=None` no longer means "no filter" — it now restricts results to the residential set (F+D+S+T). Pass the new sentinel `property_type="ALL"` for the unfiltered Land Registry firehose (including commercial/other). Specific codes (`"F"`/`"D"`/`"S"`/`"T"`/`"O"`) continue to filter to a single type.
- `PPDService.comps()` now accepts `filter_outliers: bool = False`. When set to `True`, a 1.5×IQR filter is applied to prices — outliers are dropped from BOTH the computed stats and the returned `transactions` list, so the response is internally consistent. Needs ≥4 prices, otherwise no-op.
- The three new defaults and the `"ALL"` sentinel are exposed across all consumer interfaces — REST `/v1/ppd/comps`, MCP `property_comps`, MCP app `search_comps`/`comps_dashboard`, and CLI `property-cli ppd comps` (with `--transaction-category`, `--property-type`, `--filter-outliers`/`--no-filter-outliers`). CLI accepts `--transaction-category all` as the firehose escape hatch.

## v1.4.0 (2026-03-28)

### New Features
- **`property_type` filter on yield and report** — `calculate_yield()`, `generate_report()`, and all consumers (MCP `property_yield`/`property_report`, API `/v1/analysis/yield`/`/v1/property/report`, CLI `analysis yield`/`report generate`) now accept `property_type` (F/D/S/T) to filter comparable sales. Prevents skewed figures in mixed-stock areas.
- **`sort_by` on Rightmove search** — `build_search_url()` and all consumers (MCP `rightmove_search`, API `/v1/rightmove/search-url`, CLI `rightmove search-url`) now accept `sort_by`: `newest`, `oldest`, `price_low`, `price_high`, `most_reduced`.

### Fixed
- MCP tool descriptions no longer imply analytical inference — "deal analysis" → "data pull", "yield estimate" → "yield calculation", dropped "market assessment" and "refurb potential"
- `rightmove_listing` MCP tool docstring now shows both URL and numeric ID formats are accepted

## v1.3.1 (2026-03-21)

### Fixed
- Merged `form_search()` into `sparql_search()` — fixes SPARQL 503 errors on address-based searches by using a single unified query path
- Fixed `docs/examples.md` and `docs/examples.py` to use `classify_yield()` / `classify_data_quality()` from interpret module instead of removed model attributes

### Developer Experience
- Wired `GUIDELINES.md` into `CLAUDE.md` via `@` import — architecture docs now load automatically every session
- Added 5 path-specific `.claude/rules/` files — context-appropriate guidance loads when touching `property_core/`, `mcp_server/`, `app/api/`, `property_cli/`, or `tests/`
- Added 3 workflow skills: `/add-data-source`, `/add-mcp-tool`, `/add-endpoint`
- Added `openaiDeveloperDocs` and `property-shared` HTTP MCP server entries to `.mcp.json`

## v1.3.0 (2026-03-21)

### Breaking Changes
- `yield_assessment` and `data_quality` fields on `YieldAnalysis` are no longer populated by `calculate_yield()` — they default to `None`. Use `property_core.interpret.classify_yield()` and `classify_data_quality()` instead.
- `yield_assessment` field on `RentalAnalysis` is no longer populated by `analyze_rentals()` — use `classify_yield()` on `gross_yield_pct`.
- `key_insights`, `estimated_value_low`, `estimated_value_high` fields on `PropertyReport` are no longer populated by `generate_report()` — use `generate_insights()` and `estimate_value_range()`.
- `price_vs_median` field on `MarketAnalysis` is no longer populated — `price_difference_pct` (raw number) is still computed. Use `classify_price_position()` for the label.
- `YieldAnalysis.data_quality` type changed from `str` (default `"insufficient"`) to `Optional[str]` (default `None`).
- `PropertyReportService.generate_report()` no longer accepts `value_range_pct` or `price_vs_median_pct` parameters.

### New Features
- **`property_core.interpret` module** — opt-in interpretation helpers: `classify_yield()`, `classify_data_quality()`, `classify_price_position()`, `estimate_value_range()`, `generate_insights()`. All exported from `property_core`.
- `PPDService.comps()` now accepts `thin_market_threshold` parameter (default 5) — previously hard-coded.

### Design
- **property_core returns numbers, consumers interpret them.** Services no longer generate assessment labels, quality judgments, insight text, or estimated value ranges. All raw data (yield %, counts, price difference %) is still returned. Consumers (MCP server, CLI) call interpret helpers for presentation.

## v1.2.0 (2026-03-21)

### Breaking Changes
- `calculate_stamp_duty()` default `additional_property` changed from `True` to `False` — callers that relied on the investor default must now pass `additional_property=True` explicitly
- `PPDService.comps()` default `auto_escalate` changed from `True` to `False` — callers that relied on auto-escalation must pass `auto_escalate=True` explicitly

### Configurable Defaults
- `calculate_yield()`: new `strong_yield_pct`, `average_yield_pct`, `min_comps_good` parameters for customizing yield assessment thresholds
- `analyze_rentals()`: new `filter_outliers` parameter (default True) to control IQR filtering on rent range, plus `strong_yield_pct` and `average_yield_pct` for yield thresholds
- `analyze_blocks()`: new `property_type` parameter (default "F") — pass `None` to search all property types
- `PropertyReportService.generate_report()`: new `value_range_pct` (default 15.0) and `price_vs_median_pct` (default 5.0) parameters for configurable interpretation thresholds

### New Features
- API: `GET /v1/analysis/yield` and `GET /v1/analysis/rental` endpoints
- API: `auto_escalate` query parameter on `GET /v1/ppd/comps`
- CLI: `property-cli analysis yield` and `property-cli analysis rental` commands
- CLI: PPD commands now use `PPDService` instead of raw `PricePaidDataClient` for consistent guardrails

### Fixed
- Model exports: `YieldAnalysis` now exported from `property_core.models`
- Top-level model imports: `PPDTransaction`, `EPCData`, `RightmoveListing`, `PropertyReport`, `BlockAnalysisResponse`, `CompanyRecord`, and more available directly from `property_core`
- API stamp duty default now matches core library default (`additional_property=False`)
- CLI stamp duty default now matches core library default (`--no-additional` by default)

### Removed
- `app/services/` wrapper layer — API routers now import directly from `property_core` (same pattern as MCP server and CLI). Removed `epc_service.py`, `rightmove_service.py`, and `app/utils/polite.py`

### Documentation
- Rewrote GUIDELINES.md to match actual code conventions (file naming, architecture, design principles)
- Updated CLAUDE.md: removed `app/services/` from architecture, fixed `raw` field description (transport models only), added new CLI commands and API endpoints, updated library import examples

## v1.1.2 (2026-03-20)

### Documentation
- Updated USER_GUIDE.md with accurate code examples — fixed broken method names, signatures, and imports
- Added Stamp Duty, Block Analyzer, Companies House, and MCP Server documentation sections
- Added runnable examples in docs/examples.py for all new features
- Removed stale UKHPI/location slice notes

## v1.1.1 (2026-03-19)

### MCP Server
- Rewrote MCP server with FastMCP v3 (`fastmcp>=3.0.0`) — expanded from 7 investor-focused tools to 12 covering full property_shared data surface
- New tools: `ppd_transactions`, `rightmove_search`, `rightmove_listing`, `planning_search`, `rental_analysis`
- Fixed ToolResult content for Claude.ai compatibility — `_slim()` + `_content()` helpers put full JSON data in `content[]` so all LLM hosts see the data, not just summary lines

### Bug Fixes
- Fixed Rightmove listing field mapping: `floor_area_sqft` → `display_size`, `tenure` → `tenure_type`
- Moved URI-based SPARQL filters (property_type, estate_type, etc.) to client-side post-fetch in ppd_client.py — fixes 503 timeouts from Land Registry endpoint

## v1.1.0 (2026-03-18)

### New Features
- **Stamp Duty Calculator**: `calculate_stamp_duty()` — April 2025 SDLT bands with additional property (+5%), non-resident (+2%), and first-time buyer relief. API: `GET /v1/calculators/stamp-duty`, CLI: `property-cli calc stamp-duty`
- **Block Analyzer**: `analyze_blocks()` — groups PPD flat transactions by building to find blocks with multiple unit sales (investor exits, bulk-buy opportunities). API: `GET /v1/ppd/blocks`, CLI: `property-cli ppd blocks`
- **Companies House Client**: `CompaniesHouseClient` — search by name or lookup by company number, returns typed models with officers. API: `GET /v1/companies/search`, `GET /v1/companies/{number}`, CLI: `property-cli companies search`

### MCP Server
- Added `stamp_duty` and `property_blocks` tools

## v1.0.0 (2026-03-18)

First public release. Full-featured UK property data library + API.

### Core Library (`property_core`)
- **PPD (Price Paid Data)**: Land Registry transactions via SPARQL + Linked Data API with typed Pydantic models, address search, comps with area stats (median, percentiles, subject property comparison)
- **EPC**: Energy Performance Certificate lookup (async), enrichment pipeline for PPD comps with fuzzy address matching — adds floor area, price/sqft, EPC rating to transactions
- **Rightmove**: Listings scraper with search URL builder, individual listing detail (tenure, floorplans, station distances), rental analysis with IQR outlier filtering
- **Planning**: Council matching for 98 verified UK councils (6 system types), vision-guided Playwright + OpenAI scraper for planning applications
- **Yield Analysis**: PPD sales + Rightmove rentals → gross yield with market assessment
- **Property Reports**: Multi-source aggregation (PPD + EPC + Rightmove) → structured report with key insights, estimated value range, energy performance, rental analysis
- **Postcode**: postcodes.io lookup → typed PostcodeResult model
- **Typed throughout**: All transport clients and domain services return Pydantic v2 models with `raw` field carrying original source data

### API (`app`)
- FastAPI service with versioned routers (`/v1/`)
- Endpoints: health, meta, PPD (transactions, comps, address-search, download-url), EPC search, Rightmove (search-url, listings, listing detail), property report
- Async threading for sync scrapers, in-memory rate limiting for Rightmove
- Demo UI at `/demo`
- Deployed on Fly.io (LHR region)

### CLI (`property_cli`)
- Typer CLI with dual mode: core direct (fast, no server) or API mode (`--api-url`)
- Commands: meta, ppd (comps, search, transaction), epc search, rightmove (search-url, listings, listing), report generate

### MCP Server (`mcp_server`)
- FastMCP server exposing `property_comps` and `property_yield` tools
- Svelte UI for interactive dashboards (BOUCH design system)
- Model Context Sync for AI host state management
- Compatible with Claude.ai and ChatGPT MCP hosts

### Infrastructure
- Published to PyPI as `property-shared`
- Hatch build system with wheel/sdist
- `.dockerignore` and build excludes for clean images
- Fly.io deployment with auto-stop machines
