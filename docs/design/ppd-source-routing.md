# PPD source-routing and implementation specification (rev 5 — FROZEN)

**Status:** **FROZEN.** Accepted. No further architecture work. Changes to this
document require a new decision round, not an edit in passing.

**Implementation status.** Implemented by **PR 1**: this specification, the
provenance and transport-evidence models, the protocol-neutral exception types,
the optional `snapshot` dependency declaration, and the disabled
`PPD_SNAPSHOT_ENABLED` flag. PR 1 changes no observable behaviour.

**Still unimplemented:** the snapshot adapter, the boot runtime (streaming fetch,
verification, hardened extraction, atomic activation, locking, readiness,
retention), source routing and coverage handling, the existence probe, response
wiring of the provenance block, the build pipeline, and every rollout stage.
No PPD response carries provenance yet, and no request is served from a snapshot.

**Governing rule:** this specification governs PRs 1–4; **no implementation PR
may land before the specification that governs it.**

**Basis:** Phase 2 (contract prototype) and Phase 3 (full-history validation),
both local-only. `PricePaidDataClient.sparql_search` remains patched in a lab
harness; no production adapter or boot lifecycle exists.

**Revision 5** derives `source_exhausted` as a tri-state property, models
completeness evidence explicitly as `completeness_basis`, and re-scopes the PR 1
optional-dependency tests. **Revision 4** incorporated decisions O1–O6 and all rev-2/rev-3 corrections, plus
four blocking correctness corrections: `sample_complete` requires positive
evidence (never inference from counts), exhaustion evidence must come from the
transport layer rather than the post-filter list, DuckDB import isolation must be
process-isolated, and the attribution literal is pinned independently in test.

---

## 1. Snapshot scope

### 1.1 Window — 11 year-partitions

`PPDService.comps` computes `from_date = date.today() - timedelta(days=months * 30)`
(`property_core/ppd_service.py:262`). At the public 120-month ceiling
(`app/api/v1/ppd.py:171`) that is 3,600 days = **9.86 years measured from today**,
not from a year boundary:

| Request date | `from_date` | Partition required |
|---|---|---|
| 2026-01-01 | 2016-02-23 | **2016** |
| 2026-07-01 | 2016-08-22 | **2016** |
| 2026-12-31 | 2017-02-21 | 2017 |

Ten calendar-year partitions would silently under-serve a legal 120-month request
for most of the year. **The snapshot retains the last 11 calendar-year partitions.**

| Partitions | Years | Size | Download @100 Mbit/s |
|---|---|---|---|
| 10 | 2017–2026 | 193 MiB | 16.2 s |
| **11** | **2016–2026** | **214 MiB** | **18.0 s** |
| 12 | 2015–2026 | 244 MiB | 20.4 s |

18.0 s transfer leaves ~12 s inside the 30 s readiness target; Phase 3 measured
extract+probe at 2.0 s on a 4.4x larger bundle.

The published guarantee is **`from_date >= coverage_from`**, never "10 years".

### 1.2 Layout — year-only

One Parquet file per year partition (**11 files**). Year+area is rejected on
measured grounds at full history:

| | year+area | **year-only** |
|---|---|---|
| Files | 4,998 | **32** |
| First scan (metadata) | 1,138 ms | **22 ms** |
| RSS after scan | 118.2 MB | **57.8 MB** |
| p95 district filtered | 617 ms | **66 ms** |
| Size | 956 MiB | 1,166 MiB (+22%) |

The adapter filters on `postcode`/`sector`/`outcode` and never on `area`, so
year+area delivers no pruning while charging 4,998 files of metadata. +22% bytes
accepted for the latency and RSS wins.

### 1.3 Provisional recent periods

HMLR publishes incrementally; recent months are incomplete on first publication,
and monthly A/C/D change records revise rows reaching back to 1995 (Phase 1).

The build records `provisional_from` — first day of the month `PROVISIONAL_MONTHS`
(default **3**) before `coverage_to`, published in the manifest, not inferred at
query time. Any response whose result window intersects
`[provisional_from, coverage_to]` sets `recent_period_provisional: true` and adds
a warning.

---

## 2. Historical contract

**G** guaranteed from snapshot · **E** exact-ID Linked Data · **O** permits dates
outside coverage · **A** ambiguous unbounded/latest.
Behaviours: **SNAPSHOT** · **LIVE** · **TYPED** (typed coverage error).
Per O6, **DEFER / future full-history service is removed** — it is not a current
product requirement and nothing here defers to it.

### 2.1 REST (`app/api/v1/`)

| Surface | Bounds today | Class | Behaviour |
|---|---|---|---|
| `GET /v1/ppd/comps` | `months le=120` | **G** | SNAPSHOT |
| `GET /v1/ppd/transactions` | arbitrary `from_date`/`to_date` | **O** | SNAPSHOT in range, **TYPED 422** below (§2.5) |
| `GET /v1/ppd/address-search` | no date params | **A** | **LIVE** (§2.6) |
| `GET /v1/ppd/transaction/{id}` | exact ID | **E** | **LIVE — Linked Data, always** |
| `GET /v1/ppd/blocks` | `months ge=1`, **no upper bound** | **A/O** | SNAPSHOT in range, **TYPED 422** below |
| `GET /v1/ppd/download-url` | URLs only, no rows | — | unaffected |
| `GET /v1/analysis/yield`, `/rental` | `months` | **G** | SNAPSHOT |
| `GET /v1/report/*` | `ppd_months` | **G** | SNAPSHOT |

### 2.2 Plain MCP (`app/mcp/server.py`)

| Tool | Bounds today | Class | Behaviour |
|---|---|---|---|
| `property_comps` | `months` | **G** | SNAPSHOT |
| `property_yield` | `months` | **G** | SNAPSHOT |
| `property_blocks` | `months` | **A/O** | SNAPSHOT / TYPED |
| `ppd_transactions` | `postcode`, `limit` — no dates | **A** | SNAPSHOT + existence probe (§2.4) |

### 2.3 MCP app and CLI

| Surface | Bounds today | Class | Behaviour |
|---|---|---|---|
| `search_comps`, `comps_dashboard` | `months le=60` | **G** | SNAPSHOT |
| `property_dashboard`, `yield_dashboard`, `get_yield` | `months` | **G** | SNAPSHOT |
| `property_blocks` (app) | `months le=120` | **G** | SNAPSHOT |
| `ppd_transactions` (app) | no dates | **A** | SNAPSHOT + existence probe |
| CLI `ppd comps` | `--months` | **G** | SNAPSHOT |
| CLI `ppd search` | no date flags | **A** | SNAPSHOT + existence probe |
| CLI `ppd address-search` | no dates | **A** | **LIVE** |
| CLI `ppd transaction` | exact ID | **E** | **LIVE — Linked Data** |
| CLI `ppd blocks` | `--months`, unbounded | **A/O** | SNAPSHOT / TYPED |
| CLI `ppd download-url` | URLs only | — | unaffected |
| CLI `analysis yield`/`rental`, `report generate` | `months` | **G** | SNAPSHOT |

Per **O5**, the `le=60` (app dashboard) / `le=120` (REST) inconsistency is **left
as-is**. The 11-partition snapshot covers both. Not in scope.

### 2.4 Bounded existence probe — decision O1

Neither `ppd_transactions` tool nor CLI `ppd search` accepts a date, so each
currently means "latest ever". Against a snapshot the same call means "latest
within coverage", and a postcode last sold in 2009 returns an empty list reading
as **"never sold"** — a confident false claim from an LLM-facing tool.

**Specification.**

* Serve from the snapshot. **No probe is issued when snapshot results are
  non-empty.**
* On **zero** snapshot rows, issue **one bounded existence probe**:
  * a `SELECT ... LIMIT 1` for a record with `date < coverage_from` at that
    postcode — **existence only, never `COUNT`**;
  * **3-second timeout**;
  * **no retries**;
  * result recorded as `older_records_exist: true | false | null`.
* **Probe failure, timeout or unavailability yields `null` — never `false`.**
  `false` is a positive assertion that nothing older exists and may only be set by
  a probe that actually completed.

| `older_records_exist` | Meaning | Warning |
|---|---|---|
| `false` | probe completed, nothing older exists | none — honest empty |
| `true` | records exist before `coverage_from` | `"no sales within coverage <from>..<to>; earlier records exist outside coverage"` |
| `null` | probe failed/timed out | `"coverage probe unavailable; cannot determine whether earlier records exist"` |

No response may state or imply "never sold" while `older_records_exist` is `null`.

### 2.5 Explicit out-of-coverage dates — decision O2

For surfaces taking explicit dates (`/v1/ppd/transactions`, `/v1/ppd/blocks` via
`months`, and CLI equivalents), evaluated in order:

1. Requested range inside coverage → SNAPSHOT, `source: "snapshot"`.
2. Range starts before `coverage_from` → **HTTP 422, typed, structured. Never a
   partial 200 that looks complete.**
3. No `from_date` → treated as `coverage_from`, with warning
   `"unbounded from_date narrowed to snapshot coverage"`.

```json
{ "error": "ppd_coverage_error",
  "detail": "requested range precedes snapshot coverage",
  "requested": { "from_date": "2004-01-01", "to_date": null },
  "available": { "coverage_from": "2016-01-01", "coverage_to": "2026-06-30" },
  "source_release": "v20260827T123230Z",
  "remedy": "set from_date >= 2016-01-01, or use GET /v1/ppd/transaction/{id} for a known transaction" }
```

Both requested and available ranges are **structured fields**, not prose. MCP
tools surface this as a tool error carrying the same typed payload; the CLI exits
non-zero and prints both ranges.

422 rather than 404: the request is unsatisfiable as stated, and the body carries
what is needed to reformulate it.

**This is a behavioural change** for any existing caller passing an old
`from_date`, which today receives a 200 from live SPARQL. Recorded in the
changelog plan (§8).

### 2.6 Address and subject-property history — no silent failure

`address_search` takes no dates; `_find_subject_property` (`ppd_service.py:403`)
queries with no date bound. Both mean "this property's history", frequently older
than 11 years.

* `address_search` (REST, CLI) → **LIVE**, `source: "sparql"`, unchanged.
* `_find_subject_property` inside `comps` → **LIVE**, unchanged. Comparables come
  from the snapshot; subject-property history must not be truncated to 11 years.
  Mixed-source response, declared per section (§3.4).

**The silent exception-to-None path is eliminated.** Today:

```python
except Exception:
    # Upstream failure — don't break the whole comps request
    return None
```

(`ppd_service.py:409-411`) makes "lookup failed" indistinguishable from "no
history". Replacement contract: `_find_subject_property` returns a result object
carrying an explicit outcome — `found` / `not_found` / `lookup_failed` — and
`comps` maps it:

| Outcome | `subject_property` | Warning |
|---|---|---|
| `found` | populated | — |
| `not_found` | `null` | none — genuinely no match |
| `lookup_failed` | `null` | `"subject property lookup unavailable; sale history not checked"` |

`comps` still succeeds in all three cases — the resilience the original `except`
provided is kept — but a failure is never reported as an absence.

---

## 2.7 Live-path correctness containment (PR 2)

These defects exist on the **live** path today. They are contained **before** any
snapshot work, are independently deployable, and are not caused by this design.

### 2.7.1 District outcode boundary — `B5` must not match `B50`

Prefix matching must be exact on the derived outcode/sector, never textual.
`B5` must never match `B50`. Verified structurally impossible in the snapshot
adapter (equality on `outcode`/`sector`); the live SPARQL path must carry the
same guarantee and the same test.

### 2.7.2 Allowlisted postcode-prefix validation

`postcode` and `postcode_prefix` are validated against an allowlisted UK
outcode/sector grammar before any upstream call. Malformed input →
**typed 422**, not a passthrough to SPARQL and not an empty 200.

### 2.7.3 Escalation requires transport-layer exhaustion evidence

`ppd_service.py:357` escalates on `response.thin_market`, and
`ppd_service.py:347` sets `thin_market = count < thin_market_threshold` where
`count = len(transactions)` **after `limit` was applied and after client-side
filtering**.

**`len(transactions) < limit` does not prove exhaustion.** On the live path the
upstream SPARQL window is bounded first, and filtering happens after it:
`sparql_search` applies URI-based filters client-side, and `comps` then applies
the residential type filter, subject-property removal, priceless-row removal and
optional IQR outlier filtering. A short final list is therefore equally
consistent with "the upstream window was truncated and most rows were discarded".
Inferring exhaustion from the post-filter list length is the same class of error
as inferring `sample_complete` from counts (§3.1.1).

**Evidence must be carried from the transport layer**, alongside the rows:

| Field | Meaning |
|---|---|
| `raw_bindings_returned` | rows the upstream actually returned, **before** any client-side filtering |
| `fetch_limit` | the limit sent upstream for that page |
| `source_exhausted` | **tri-state, derived — never settable** (see below) |

`source_exhausted` is a **derived property**, not a constructor field:

| Condition | Value |
|---|---|
| `raw_bindings_returned < fetch_limit` | **`True`** |
| `raw_bindings_returned >= fetch_limit` | `False` |
| either input absent | **`None`** (unknown) |

Constructor input must not be able to override it. **Unknown remains unknown**:
only `source_exhausted is True` may authorise escalation or support
`sample_complete=True`. `None` is never treated as `False` for permission
purposes and never as `True`.

**On the live source, escalation is DISABLED outright.** `fetch_limit` is derived
from the caller's presentation limit, so `source_exhausted` is itself
limit-dependent: the same data at `limit=4` and `limit=5` could yield different
evidence and therefore different geography. Evidence of that shape cannot
authorise widening. Live comps return the **requested, narrower** geography with
an explicit warning; some callers consequently see a narrower area than before,
because the previous widening was a page-size artefact rather than a market
judgement.

Snapshot routing may re-enable escalation in PR 4 using limit-independent
deterministic evidence, and only then would both of these need to hold:

1. `source_exhausted` **is `True`** (not `False`, not `None`); and
2. the **eligible matching count** (post-filter) is below `thin_market_threshold`.

**On the live source, and whenever `source_exhausted` is `false` or unknown:**

* **do not escalate;**
* **preserve the narrower geography;**
* **emit a completeness warning** — e.g. `"result may be incomplete: upstream
  window was not exhausted; thin-market assessment not performed"`;
* leave `sample_complete: false`.

### 2.7.4 Presentation limit must never determine geography

The caller's presentation `limit` is a page size. It must never widen
sector→district. With `limit=3` and `thin_market_threshold=5` the rev-3 rule
would still have misfired whenever filtering shrank a full upstream page.
`escalated_from`/`escalated_to` must reflect a real market judgement backed by
`source_exhausted: true`, never a page-size or filter artefact.

### 2.7.5 Correct the false `record_status` documentation; leave the filter disabled

The filter stays disabled — `UnsupportedRecordStatusFilterError` continues to
raise. Only the **documentation** is corrected where it misdescribes what the
parameter does or implies it may work. Behaviour is unchanged; the wording stops
being false.

### 2.7.6 Document and warn that offset pagination is incomplete and unstable

`offset` on `search_transactions` is not a stable cursor: the underlying ordering
is not guaranteed total across pages, so deep offsets can repeat or omit rows.
Specification: document this on every surface exposing `offset`, and emit a
warning when `offset > 0` stating that offset paging is not stable and may repeat
or omit rows. Keyset pagination is the correct mechanism (validated in Phase 2/3:
zero duplicates, zero omissions over 73,785 rows with 98 same-date ties) but
introducing it is **not** in this scope.

## 2.8 Exact-ID Linked Data taxonomy (PR 2)

`get_transaction_record` (`ppd_client.py:138`) →
`PPDTransactionRecord.from_linked_data` (`models/ppd.py:242`).

`models/ppd.py:249` does `primary = result.get("primaryTopic", {}) if isinstance(result, dict) else {}`,
then `models/ppd.py:270` calls `primary.get("propertyAddress")`. When upstream
returns `primaryTopic` as a **bare string** URI rather than an object, `primary`
is a `str` and that line raises **`AttributeError: 'str' object has no attribute
'get'`** — an internal error leaked to the caller for what is really "no record".

Required outcome taxonomy, mirroring §2.6:

| Upstream shape | Outcome | Surface behaviour |
|---|---|---|
| `primaryTopic` is an **object** | `found` | 200, record, `source: "linked_data"` |
| `primaryTopic` is a **bare string** | `not_found` | **404**, typed, no warning — genuinely absent |
| HTTP error, timeout, unparseable body | `lookup_failed` | **502** `upstream_unavailable`, typed, warning |

**`AttributeError` must never escape**, and **`lookup_failed` must never be
reported as `not_found`.** A failed lookup is not an absent record — the same
rule as the subject-property path (§2.6).

---

## 3. Honest response contract

### 3.1 Provenance block (additive, non-breaking)

| Field | Type | Meaning |
|---|---|---|
| `source` | `"snapshot"｜"linked_data"｜"sparql"` | where these rows came from |
| `source_release` | str｜null | snapshot version |
| `snapshot_imported_at` | ISO8601｜null | when the build ran |
| `coverage_from` / `coverage_to` | date｜null | inclusive data bounds |
| `freshness_days` | int｜null | `today - coverage_to` |
| `recent_period_provisional` | bool | window intersects the provisional tail |
| `older_records_exist` | bool｜null | §2.4; present only on empty results from dateless surfaces |
| `sample_count` | int | rows returned |
| `sample_limit` | int | limit applied |
| `sample_complete` | bool | **defaults `false`**; `true` only with a non-null `completeness_basis` (§3.1.1) |
| `completeness_basis` | enum｜null | `source_exhausted`｜`limit_plus_one`｜`explicit_adapter_exhaustion`｜null |
| `warnings` | list[str] | existing field, extended |

For `linked_data`/`sparql` responses the snapshot fields are `null`.

### 3.1.1 `sample_complete` requires positive evidence

**`sample_complete` is never inferred from `sample_count` and `sample_limit`.**
The rule `sample_count < sample_limit => complete` is **wrong and removed**: on
the live path the upstream window is bounded *before* client-side filtering, so a
short result set is equally consistent with "everything matched" and "the
upstream window was truncated and most rows were filtered out".

Contract:

* `sample_complete` **defaults to `false`.**
* It becomes `true` **only when the active adapter provides positive evidence**
  that every matching source row within the declared coverage and filter contract
  was examined.
* **Counts alone never establish completeness.** `sample_count < sample_limit` is
  not evidence of anything.
* The evidence is **modelled explicitly** as `completeness_basis`:
  `source_exhausted` | `limit_plus_one` | `explicit_adapter_exhaustion` | `None`.
  * `sample_complete=True` with `completeness_basis=None` **fails validation**.
  * `sample_complete=False` permits `completeness_basis=None`.
* **Snapshot adapter** may establish it via `limit_plus_one` or
  `explicit_adapter_exhaustion`; the live path may only via `source_exhausted`
  being `True`.
* **Live SPARQL generally leaves it `false`**, unless exhaustion is *explicitly
  observed* at the transport layer (§2.7.3).

`sample_count = 3` with `sample_limit = 5` may legitimately carry
`sample_complete: false`. That is the correct, honest answer when the adapter
cannot prove it saw everything.

Per the attribution directive, the provenance block carries **no licence text**.
Attribution lives in dataset metadata and docs (§6).

### 3.1.2 Provenance is constructed atomically

`PPDProvenance` is **frozen**. The completeness rule in §3.1.1 is a
*construction-time* check, so the block must not be mutable afterwards: without
freezing, `p.sample_complete = True` on an incomplete block silently produced the
exact state the model forbids, and serialised it.

`validate_assignment=True` is **deliberately not used**. Under Pydantic 2.12.5 an
after-validator can raise *during* assignment while the object retains the
invalid mutated value — worse than no check, because the error looks handled
while the corrupt state survives. Freezing rejects the write before it happens.

**The complete block, including its warnings, is immutable.** Freezing is
shallow, so `warnings` is a `tuple[str, ...]` rather than a list: a list field
would still permit `p.warnings.append(...)` to change what the block serialises
after validation. A list is accepted on input and normalised to a tuple, and the
field still serialises as a JSON array.

**Requirement for implementers.** Gather the counts, the completeness evidence
and the warnings first, then construct **one** validated block. Never build a
provenance block and refine it by assignment. A refined block is a *new*
validated construction.

`model_copy(update=...)` is a Pydantic escape hatch that bypasses validation by
design — it can produce and serialise a block `__init__` would reject. It is
**prohibited** for provenance. This is enforced by specification rather than by a
custom `BaseModel` override: adding one solely to protect trusted internal code
is not worth the surface area.

### 3.2 What an empty result means

**An empty result means: no matching rows exist within the stated coverage.** It
never encodes "outside the snapshot" or "the source failed."

| Situation | `count` | `source` | Transport | Distinguisher |
|---|---|---|---|---|
| No rows in coverage, none older | 0 | `snapshot` | 200 / ok | `older_records_exist: false`, no warning |
| No rows in coverage, older exist | 0 | `snapshot` | 200 / ok | `older_records_exist: true` + warning |
| No rows in coverage, probe failed | 0 | `snapshot` | 200 / ok | `older_records_exist: null` + warning |
| Requested dates precede coverage | — | — | **422** | `ppd_coverage_error` + structured ranges |
| No verified snapshot open | — | — | **503** | `snapshot_unavailable` |
| Snapshot serving, refresh failed | n | `snapshot` | 200 | `stale_source: true` + warning |
| Live upstream failed | — | — | **502** | `upstream_unavailable` |

MCP tools surface rows 4, 5 and 7 as **tool errors** carrying the typed code —
never as empty data. Verified end-to-end in Phase 2/3.

### 3.3 Tool description changes

Both `ppd_transactions` descriptions currently imply unbounded history and must
change. These strings are what an LLM routes on, so they are part of the contract.

`property_app/tools.py:557` — replace:

> Returns **every recorded transaction** at the postcode, unfiltered (includes
> category-B bulk transfers and commercial sales).

with:

> Returns **up to `limit` most recent transactions within snapshot coverage**
> (`coverage_from`–`coverage_to` in the response), unfiltered — includes
> category-B bulk transfers and commercial sales. Not a complete property
> history: check `older_records_exist` and `sample_complete`. For clean
> residential comparable sales, use `property_comps`.

`app/mcp/server.py:565` — replace `"""Raw Land Registry Price Paid transactions
for a postcode."""` with the same coverage-explicit wording.

Also review the plain server's `instructions` string, which describes
`ppd_transactions` as *"for specific property history"* — misleading under a
bounded snapshot.

### 3.4 Mixed-source responses

Top-level `source` describes the comparables; `subject_property` carries its own
nested provenance with `source: "sparql"`. Two sources are never presented under
one undifferentiated label.

---

## 4. Runtime design

**No hot refresh in v1. Activation occurs at process start only.**

### 4.1 Fetch
* `current.json` → manifest → schema validation; missing required key fails closed.
* Bundle **streamed** to a temp file in 1 MiB chunks, SHA-256 incremental. **The
  body is never held in memory** — verified at scale: a 945.5 MiB bundle booted at
  199.5 MB peak RSS.
* Limits: `MAX_BUNDLE_BYTES` **1 GiB** (~4.8x margin over 214 MiB); connect
  timeout 10 s; total download deadline 300 s; stall timeout 60 s. Any breach
  aborts and deletes the temp file.
* `Content-Length` mismatch = interrupted transfer, not a valid object.

### 4.2 Verify
Byte length **and** SHA-256 must both match, before extraction. Phase 3 proved
this rejects a well-formed decoy archive with different contents.

### 4.3 Extract (hardened)
Member-validating streaming extraction. Rejected: absolute paths, any `..`
component, symlinks, hardlinks, device/FIFO nodes, duplicate names, member count
over `MAX_MEMBERS` (**5,000**), per-member bytes over `MAX_MEMBER_BYTES`,
cumulative decompressed bytes over `MAX_TOTAL_BYTES` (**2 GiB**). Every resolved
path must stay inside staging. 10/10 attack classes rejected in Phase 3,
including a hostile archive whose **SHA-256 matched its manifest** — digest checks
cannot catch that.

### 4.4 Verified versioned directory and atomic activation
Extract to `staging/<version>.<rand>/`; probe (open DuckDB, `count(*)`, compare
rows and file count to manifest); write `.verified.json`; `os.replace()` into
`snapshots/<version>/`; atomically flip `CURRENT` via temp-file + `os.replace()`.
**Any failure leaves the previous verified snapshot serving, untouched** —
verified for corrupt manifest, corrupt bundle, digest mismatch, truncated
transfer and hostile archive.

The readiness probe counts Parquet files on the **filesystem**, never via
`count(DISTINCT filename)` (a Phase 3 defect: it scans every row).

### 4.5 States

| State | Readiness | Behaviour |
|---|---|---|
| `ready` | 200 | verified snapshot open, `stale_source: false` |
| `ready_stale` | 200 | serving verified cache, refresh failed, `stale_source: true` + warning |
| `unready` | 503 | no verified snapshot; typed `snapshot_unavailable` |

Startup with a cached snapshot matching the advertised manifest skips the download
(Phase 3: **0.81 s, 0 bytes**).

### 4.6 Process-safe single-flight
Exclusive `flock()` on `<cache>/.boot.lock` held across download → verify →
extract → activate. A worker that cannot acquire it **blocks** (bounded by
`LOCK_WAIT_SECONDS`, default 420 s), then re-reads `CURRENT` and activates from
cache with **no download**. Lock records PID + boot-id; a stale lock from a dead
process breaks after `LOCK_STALE_SECONDS` (default 900 s). Staging dirs are
per-attempt (`mkdtemp`) so a broken lock can never produce two writers on one
path. `flock` is advisory and per-host — correct for multiple workers in one
machine; it does not coordinate across machines, and one fetch per machine is
intended.

### 4.7 Cleanup
Retain **current and previous** verified versions; delete older after successful
activation (rollback becomes a `CURRENT` flip). Staging dirs and temp bundles
deleted on every exit path. Before download, require `bundle_bytes * 2.5` free
disk, else fail closed with a typed error.

### 4.8 Build-stage authorisation limits

The build pipeline stage may **build and validate an artifact locally only**.
**No upload, bucket creation, Fly secret, cloud resource or production mutation
is authorised.** Artifact distribution — where a bundle is hosted and how a
deployed app reaches it — remains a **separately approved decision** and is not
settled by this specification.

### 4.9 Release cadence and freshness — decision O3

* **Rebuild monthly, following each observed HMLR release.** Cadence follows the
  observed release, not the calendar.
* **Daily check** for a changed release: compare `ETag` / `Last-Modified` /
  `Content-Length` on `pp-complete.csv` against the values recorded in the current
  manifest. Cheap `HEAD`; no download unless changed.
* **Warn** when `freshness_days > 45` — surfaced in the provenance `warnings` and
  in health output.
* **Alert** when an observed release remains uningested for **7 days** — an
  operational alert, distinct from the freshness warning: it means the pipeline is
  failing, not merely that HMLR has not published.
* **Never become unavailable due to staleness.** A stale but verified snapshot is
  always served in preference to `unready`. Staleness is a warning, not an outage.
* Recent source periods remain **provisional** (§1.3) regardless of freshness.

Observed-release state (last-seen ETag, last-ingested release, first-observed
timestamp) is recorded so the 7-day alert is measured from **observation**, not
from build time.

---

## 5. Packaging

DuckDB (~59 MB native wheel) must not be forced on every library consumer.

```toml
[project.optional-dependencies]
snapshot = ["duckdb==1.5.5"]     # pinned: snapshot is built by 1.5.5
```

Lazy import inside the snapshot adapter; a typed, actionable error if missing.
`property_core` imports must not fail without it.

| Consumer | Needs `snapshot`? | Why |
|---|---|---|
| `property_core` as a PyPI library | **No** | live adapter is the default |
| `property_cli` (core mode) | **No** | unless `--source snapshot` |
| `Dockerfile` → `property-shared` (REST + plain MCP) | **Yes** | serves comps from snapshot |
| `Dockerfile.app` → `propertydata` (MCP app) | **Yes** | same |
| CI unit tests | **Yes** (dev extra) | adapter tests |

Entry points: `property-api` (`app.main:app`) and `property_app.server:main`, both
only when `PPD_SNAPSHOT_ENABLED=1`. With the flag off, both boot on the live
adapter and DuckDB is never imported. **Two images change; the published library
does not.**

---

## 6. Licensing and data-protection posture

The snapshot is **private implementation data**: not offered for download, not
exposed by any endpoint, no route serves the bundle or bulk rows, and **no
bulk or address export exists**.

Required attribution:

> Contains HM Land Registry data © Crown copyright and database right 2021. This
> data is licensed under the Open Government Licence v3.0.

**Placement — dataset metadata and documentation only.** It appears in `/v1/meta`,
the dataset metadata block, README, `docs/design/ppd-source-routing.md`, CLI
`meta`, and the MCP servers' `instructions` string. **It is not repeated in every
tool response.** Per-response provenance carries `source`/`source_release`/
coverage fields and a stable pointer (e.g. `attribution_ref: "/v1/meta"`), not
licence prose.

**Address fields** (`paon`, `saon`, `street`, `locality`, `town`, `district`,
`county`, `postcode`) are used **solely to provide residential property-price
information** — matching a property to its sale history and locating comparables.
Not used for address validation, autocomplete, geocoding, mailing lists, or any
address-derived product.

**Requires separate Royal Mail review before any implementation:**
* raw or bulk **export** of address-bearing rows in any format;
* any endpoint returning address fields not tied to a price result;
* any non-price use — address validation, autocomplete, geocoding, PAF-like lookup;
* redistribution of the snapshot bundle.

None are proposed. Any of them stops for review.

---

## 7. TDD and rollout

### 7.1 Red tests — written failing first

**Geography correctness**
1. `B5` never matches `B50` — district search returns only `B5` outcodes while
   `B50` rows exist. Asserted against direct ground truth.
2. Sector isolation (`M3 7` returns only `M3 7`).
3. Full keyset traversal of the densest outcode: zero duplicates, zero omissions,
   canonical order across same-date ties.
4. Filtered comps honour `property_type` and `transaction_category` exactly.

**Coverage routing**
5. Explicit `from_date` before `coverage_from` → 422 `ppd_coverage_error` with
   structured `requested` and `available`; never 200 with partial rows.
6. `from_date` inside coverage → 200, `source: "snapshot"`.
7. Absent `from_date` → narrowed to `coverage_from` **with** warning.
8. `blocks` with unbounded `months` resolving before `coverage_from` → 422, not a
   silent clamp.
9. CLI equivalents exit non-zero and print both ranges.

**Missing vs unavailable**
10. Empty in coverage, probe says nothing older → `older_records_exist: false`,
    no warning.
11. Empty in coverage, older records exist → `older_records_exist: true` + warning.
12. **Probe times out (3 s) → `older_records_exist: null` + warning, never
    `false`**, and no "never sold" claim anywhere in the payload.
13. Probe issues **no query at all** when snapshot results are non-empty.
14. Probe uses `LIMIT 1` existence, **not `COUNT`**, and is not retried.
15. No verified snapshot → 503 / typed tool error, never an empty result set.
16. Live upstream failure → 502 `upstream_unavailable`, distinct from both.
17. Subject-property lookup failure → `subject_property: null` **with** warning;
    genuine no-match → `null` **without** warning. The two are distinguishable.

**Exact-ID fallback**
18. `GET /v1/ppd/transaction/{id}` returns `source: "linked_data"` and works for a
    transaction **outside** snapshot coverage.
19. `record_status` on search still raises `UnsupportedRecordStatusFilterError`
    against the snapshot adapter (parity with live).

**Sample completeness (§3.1.1)**
20. Result at `limit` → `sample_complete: false`.
21. **`sample_count = 3`, `sample_limit = 5`, no exhaustion evidence →
    `sample_complete: false`.** Counts alone never establish completeness; this
    test exists specifically to prevent the inference rule being reintroduced.
21b. Snapshot adapter observing exhaustion (`limit + 1` fetch returning fewer
    than `limit + 1`) → `sample_complete: true`.
21c. Live SPARQL with no explicit exhaustion observation →
    `sample_complete: false`, regardless of how few rows returned.
21d. `sample_complete` defaults to `false` on a freshly constructed provenance
    block.

**Provenance across all four consumers**
22. REST comps carries the full provenance block.
23. Plain MCP `property_comps` carries it in `structured_content`.
24. MCP app `search_comps` carries it.
25. CLI `ppd comps` carries it in both core and `--api-url` modes.
26. Mixed-source comps: top-level `snapshot`, nested `subject_property` `sparql`.
27. `recent_period_provisional` true iff the window intersects the provisional tail.
28. Every PPD response carries a compact `attribution_ref`.
28b. `attribution_ref` **resolves** to metadata containing the exact required
    attribution string, character for character. **The expected value is a
    literal pinned in the test file itself** — the test must NOT import or derive
    it from the same constant the documentation and runtime use, or it would pass
    if that constant were corrupted.
28c. Long licence prose does **not** appear in transaction or comps payloads.
29. Both `ppd_transactions` descriptions state coverage-bounded semantics and no
    longer say "every recorded transaction".

**Live-path containment (PR 2, §2.7)**
39. `B5` district search never matches `B50` **on the live path**, same assertion
    as test 1.
40. Malformed `postcode` / `postcode_prefix` → typed **422**, not a passthrough
    and not an empty 200; allowlisted grammar accepts valid outcodes/sectors.
41. **Regression fixture: `raw_bindings_returned == fetch_limit` (upstream window
    full) but post-filter results fewer than `limit` → MUST NOT escalate.**
    Geography preserved, `escalated_from`/`escalated_to` null, completeness
    warning emitted, `sample_complete: false`. This is the exact case the rev-3
    rule got wrong.
41b. `source_exhausted` unknown/absent → treated as **not** exhausted; no
    escalation.
42. `limit=3, thin_market_threshold=5` on a dense sector → **geography
    unchanged**; presentation limit never widens sector→district.
43. **Live never escalates, even with `source_exhausted: true`** — the evidence
    is limit-derived, so it cannot authorise widening. The requested geography is
    returned with a warning.
43b. **Decisive regression:** same fixture and window at `limit=4` vs `limit=5`
    → identical `search_level`, no escalation either way, the warning present
    exactly once, and no additional upstream request.
43c. `raw_bindings_returned` and `fetch_limit` are propagated from the transport
    layer to the decision point — asserted directly, not via the row list.
44. `record_status` still raises `UnsupportedRecordStatusFilterError`; corrected
    docs no longer claim or imply the filter works.
45. `offset > 0` emits the instability warning; documentation states offset paging
    may repeat or omit rows.

**Exact-ID Linked Data taxonomy (PR 2, §2.8)**
46. `primaryTopic` object → `found`, 200, `source: "linked_data"`.
47. `primaryTopic` **bare string** → `not_found`, **404**, typed, no warning —
    and **no `AttributeError`** anywhere in the path.
48. Upstream HTTP error / timeout / unparseable body → `lookup_failed`, **502**
    `upstream_unavailable` + warning.
49. `lookup_failed` is **never** rendered as `not_found`.

**PR 1 inertness gate (no behaviour change)**
55. Golden responses are **byte-identical** before and after PR 1 for the named
    surfaces: REST `/v1/ppd/comps`, REST `/v1/ppd/transactions`,
    REST `/v1/meta/integrations`, core `PPDService.comps`,
    core `PPDService.search_transactions`, both MCP `ppd_transactions` tools
    (plain server and MCP app), and CLI `ppd comps`.
56. The golden is driven by **deterministic in-memory source fixtures** — a fixed
    row set with the transport seam patched. No live upstream is contacted, and a
    live SPARQL response is never compared byte-for-byte: it is not stable, and
    the test would be measuring the upstream rather than the change.
57. **Sockets are hard-failed** for the duration of the capture, so an accidental
    network call fails the test rather than silently making it non-deterministic.
    A self-check proves the socket block is actually armed.
58. **No provenance field is exposed in PR 1.** `attribution_ref`,
    `completeness_basis`, `source_release`, `older_records_exist` and
    `sample_complete` must appear in no response payload.

**Optional-dependency declaration (PR 1, §5)**
50. `property_core` imports under an explicit DuckDB import blocker.
51. Every current public export imports under that blocker.
52. `pyproject.toml` declares `snapshot = ["duckdb==1.5.5"]`.
53. `uv.lock` contains the optional dependency and `uv lock --check` succeeds.
54. `PPD_SNAPSHOT_ENABLED` defaults false.

The blocker is a `sys.meta_path` finder raising on `duckdb`, applied in a clean
subprocess. These must **not** assert against `sys.modules` in the shared test
process: an earlier test may already have imported DuckDB, making them pass
vacuously.

**Deferred out of PR 1** — there is no adapter or routing in PR 1, so these would
be vacuous or need a premature stub:
* *requesting the snapshot adapter without the extra raises the typed actionable
  error* → **runtime/adapter PR (PR 3)**;
* *flag-off REST/MCP request paths import no DuckDB* → **PR 4**, where mutation
  testing can prove the flag controls a real import path.

**Runtime**
30. Streamed fetch: boot peak RSS does not scale with bundle size.
31. Extraction attacks — traversal, deep traversal, absolute path, symlink,
    symlink-then-write-through, hardlink, duplicate members, member-count cap,
    decompressed-size cap — each rejected, nothing written outside staging.
32. Hostile archive whose **SHA-256 matches its manifest** → rejected at
    extraction, previous snapshot still serving.
33. Failed update retains the old snapshot: `CURRENT` unchanged, no staging
    residue, queries still answer.
34. Concurrent startup single-flight: N workers, cold cache → exactly **one**
    download; others activate from cache.
35. Cached restart performs **zero** additional download.
36. Cleanup retains exactly current + previous.
37. Insufficient disk → typed failure before download begins.
38. Stale verified snapshot is served rather than going unready;
    `freshness_days > 45` emits a warning.

### 7.2 Shadow comparison — decision O4

Ship off by default (`PPD_SNAPSHOT_ENABLED=0`).

**Stage 1 — shadow.** For a sampled fraction of comps requests run both adapters,
**return the live result**, and record a structured diff: transaction-ID set
difference, per-field equality on shared IDs, count delta, latency of both.
Shadow failures never affect the response.

**The live SPARQL adapter is not the numerical gold standard.** A divergence is a
question to answer, not automatically a snapshot defect — live is subject to its
own truncation, timeout and ordering behaviour. Exit therefore requires
explanation, not a similarity score.

**Exit criteria — all must hold. No percentage threshold.**

* **Zero unexplained false empties** — no case where the snapshot path returns
  empty and live returns rows within coverage without a classified explanation.
* **Zero geography contamination** — no B50-in-B5 class error, no sector or
  outcode bleed, in the entire corpus.
* **100% field equality on shared transaction IDs** — where both return the same
  ID, every compared field is identical.
* **Every divergence classified.** Expected classes: provisional-tail lag; rows
  revised by monthly A/C/D records since the build; live-side truncation or
  ordering differences. An unclassified divergence blocks exit.
* **Zero snapshot errors in the agreed corpus** — no unhandled exception, no
  typed error where the request was in-coverage and well-formed.
* **p95 < 1 second** on real traffic.

The corpus is agreed before Stage 1 begins and is fixed for the duration.

**Stage 2 — opt-in. Hard deployment gates, measured before the flag is enabled.**

The two facts Phase 3 could not evidence are now **blocking gates**, not caveats:

* **G1 — transient boot disk measured on the real 512 MB Fly app.** Measure peak
  transient disk for the **11-partition** bundle (~214 MiB streamed + ~230 MiB
  extracted, both live until the atomic rename) on the actual machine. The
  measurement must be taken, recorded, and fit within the machine's volume with
  the §4.7 `bundle_bytes * 2.5` headroom rule satisfied.
* **G2 — worker count verified, or one worker explicitly pinned.** All Phase 2/3
  RSS figures are a single uvicorn process. Either verify the deployed worker
  count and re-derive the RSS budget for that count, **or** explicitly pin the
  app to one worker and record that as a deployment constraint.

**If either gate fails or cannot be measured, stop before enabling the flag.**
No estimate substitutes for the measurement.

Once both pass: enable for `comps`/`yield`/`report`/`blocks` on `property-shared`
only; live adapter as automatic fallback on typed snapshot errors. Monitor
`source` distribution and warning rates.

**Stage 3 — default on**, both images. Live retained as fallback and as the sole
path for exact-ID, address-search and subject-property lookups.

Rollback at any stage: `PPD_SNAPSHOT_ENABLED=0` + restart. No data migration — the
snapshot is derived and disposable.

---

## 8. Changelog plan

To be written in the implementation PR, under a new minor version.

**Changed (behavioural — call out prominently)**
* `GET /v1/ppd/transactions` and `GET /v1/ppd/blocks` now return **422
  `ppd_coverage_error`** when the requested date range precedes snapshot
  coverage, instead of a 200 from live SPARQL. Structured `requested` and
  `available` ranges are included. **Callers passing `from_date` older than
  `coverage_from` must narrow the range or use
  `GET /v1/ppd/transaction/{id}`.**
* An absent `from_date` is narrowed to `coverage_from` and warned, rather than
  meaning "all time".
* Both `ppd_transactions` tool descriptions now state coverage-bounded semantics.
* `comps` distinguishes subject-property **lookup failure** from **no history**;
  a failure now emits a warning instead of a silent `null`.
* **Malformed `postcode`/`postcode_prefix` now returns a typed 422** instead of
  being passed through to SPARQL.
* **Auto-escalation is disabled on the live source.** `auto_escalate` remains
  accepted for compatibility but no longer widens sector→district: the only
  available evidence (`raw_bindings_returned < fetch_limit`) derives from the
  caller's presentation limit, so the geography would still move with page size.
  **Callers will see a narrower geography than before** — the previous widening
  was a page-size and filtering artefact, not a market judgement — plus a warning
  explaining why. Snapshot routing may re-enable it in PR 4 on limit-independent
  evidence.
* **`sample_complete` is no longer inferred from counts.** It defaults `false`
  and is `true` only on positive adapter evidence, so some responses that
  previously looked complete are now correctly marked incomplete.
* **`GET /v1/ppd/transaction/{id}` now returns 404** for a genuinely absent
  record (upstream bare-string `primaryTopic`) and **502** on upstream
  failure/parse error, instead of leaking `AttributeError`.
* **`offset > 0` now emits a warning** that offset pagination is unstable and may
  repeat or omit rows.

**Added**
* Provenance block on all PPD responses (`source`, `source_release`,
  `coverage_from`/`coverage_to`, `freshness_days`, `recent_period_provisional`,
  `older_records_exist`, `sample_count`/`sample_limit`/`sample_complete`).
* Optional `snapshot` extra (`duckdb==1.5.5`); `PPD_SNAPSHOT_ENABLED`, default off.
* HMLR attribution in `/v1/meta`, CLI `meta` and both MCP `instructions` strings.

**Unchanged**
* Exact-ID `GET /v1/ppd/transaction/{id}` remains Linked Data.
* `address-search` remains live SPARQL.
* `months` limits unchanged (`le=60` app dashboard, `le=120` REST) — O5.
* The published library gains no required dependency.

---

## 9. Out of scope

Hot refresh while serving; cross-machine fetch coordination; incremental/delta
snapshot updates; a separate full-history service (**O6** — deep history is not a
current product requirement); aligning the 60/120-month limits (**O5**); any bulk
or address export (§6). Untested and therefore unclaimed: real Tigris latency or
reliability; behaviour on a real 512 MB Fly machine, especially transient boot
disk; concurrency beyond 2 simultaneous queries; soak testing; multi-worker RSS
totals — all Phase 2/3 figures are a single uvicorn process.

---

## 10. Final PR sequence (frozen)

**Governing rule: no implementation PR lands before the specification that
governs it.** This document lands in PR 1 at `docs/design/ppd-source-routing.md`;
PRs 2–4 are reviewed against it.

| PR | Contents | Flag | Behaviour change |
|---|---|---|---|
| **PR 1** | This versioned specification at `docs/design/ppd-source-routing.md`; provenance and typed-error models; `snapshot` optional dependency; `PPD_SNAPSHOT_ENABLED` (default **off**) | off | **none** |
| **PR 2** | Live-path correctness containment (§2.7); exact-ID Linked Data taxonomy (§2.8); subject-property taxonomy (§2.6); corrected `ppd_transactions` descriptions (§3.3) | off | **yes** — independently deployable, no snapshot required |
| **PR 3** | Boot runtime: streaming fetch, verification, hardened extraction, atomic activation, single-flight locking, readiness states, retention (§4.1–4.7) | off | none at request level |
| **PR 4** | Snapshot adapter, source routing, coverage handling, bounded existence probe (§2.1–2.5) | off | none until enabled |

**PR 4 implementation note.** Response wiring must build each `PPDProvenance` **atomically** from already-gathered counts and completeness
evidence (§3.1.2). The block is frozen; incremental assignment as the adapter
learns more is not available and must not be worked around with
`model_copy(update=...)`.

Then, each separately authorised:

5. **Build pipeline** — 11-partition year-only build, manifest with
   `provisional_from`, daily release check, monthly rebuild.
   **Local build and validation only. No upload, bucket, Fly secret, cloud
   resource or production mutation** (§4.8). Artifact distribution is a separate
   approval.
6. **Fixed shadow corpus**, agreed before Stage 1 and frozen for its duration.
7. **Rollout gates** — G1 (measured transient disk on the real 512 MB Fly app for
   the 11-partition bundle) and G2 (verified worker count, or one worker pinned).
   **Either failing stops the rollout before the flag is enabled.**
8. **Stage 2 opt-in**, then **Stage 3 default on**.

PR 2 is the only PR in this sequence that changes behaviour, and it does so
without any snapshot dependency: it fixes defects that exist on the live path
today.

Rollback throughout: `PPD_SNAPSHOT_ENABLED=0` plus restart. The snapshot is
derived and disposable; no data migration exists to reverse.
