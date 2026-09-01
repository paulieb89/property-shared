# PPD source-routing and implementation specification (rev 10 — FROZEN)

**Status:** **FROZEN at rev 10.** Accepted. No further architecture work. Changes
to this document require a new decision round, not an edit in passing.

**Revision 10** was authorised by the Stage 1 mechanism decision round, before
Stage 1 started and before any Stage 1 evidence existed. It changes **one exit
criterion and nothing else**: §7.2's "p95 < 1 second **on real traffic**" becomes
"**p95 < 1 second on the deployed production Machine and selected artifact,
measured across the frozen corpus request mix**".

The reasoning is stated in full at §7.2 and is summarised here: organic `comps`
traffic on `property-shared` is sparse and uncontrolled, so a percentile over it
measures the callers rather than the adapter, and could not be reproduced or
attributed; the frozen thirteen-case corpus is deliberately risk-shaped, is
identical between runs, and is harder than organic traffic. The revision also
avoids adding permanent request-path machinery — a queue, a worker thread,
sampling configuration and a telemetry stream inside the serving application —
that would exist solely to produce rollout evidence and would outlive the gate.

**What is given up is stated rather than hidden: the request mix is chosen, not
observed.** This is a gate revision made *before* Stage 1, not a claim that a
corpus run is organic traffic, and not a licence to relabel one as the other.

**No other requirement is relaxed.** The 30 s readiness target, the
`bundle_bytes * 2.5` headroom rule, the other five Stage 1 exit criteria, the
`comps`-only corpus scope, and G1a, G1b, G2 and G3 are unchanged.
`PPD_SNAPSHOT_ENABLED` remains the sole authority to route and remains absent.
Nothing is enabled, no image is deployed, and no artifact is replaced.

**Revision 9** was authorised by the Phase D review round, after the partial-G1a
measurement recorded in
[`docs/ops/2026-08-31-ppd-snapshot-rollout.md`](../ops/2026-08-31-ppd-snapshot-rollout.md).
That measurement showed 36.7 s of materialization plus 3.1 s of adapter-open
validation on the real `property-shared` Machine — so on **the measured path**,
a boot awaited inside the ASGI lifespan did not meet the 30 s readiness target.
That is a statement about what was measured, not a proof about every possible
path: the transfer ran at 63.6 Mbit/s on a depleted CPU burst balance, and a
faster transfer could bring an awaited boot back under 30 s. Rev 9 removes the
dependency on that question rather than answering it.

Rev 9 changes **when the boot runs**, not what it produces or what may be
served. §4.10 gains a non-blocking rule: the lifespan *starts* the boot and
returns immediately, the application is ready serving live data, and the
snapshot becomes eligible to route only once it has materialized and validated.
It also adds the control-only `PPD_SNAPSHOT_SHADOW_ENABLED` flag, which performs
that boot and deliberately never routes, so full G1a can be measured against the
real application lifecycle without serving a single snapshot row.

**No requirement is relaxed.** The 30 s readiness target is unchanged — rev 9
makes it *measurable* rather than unreachable-by-construction, and does not
claim it is met. The `bundle_bytes * 2.5` headroom rule, every Stage 1 exit
criterion, and G1a, G1b, G2 and G3 are unchanged. `PPD_SNAPSHOT_ENABLED` remains
the sole authority to route. Nothing is enabled, no image is deployed, and no
artifact is replaced.

**Revision 8** was authorised by the corpus-acceptance and artifact-distribution
decision round, after PRs #30 and #31 merged. It is a **status** revision, not an
architecture one. It records the fixed shadow corpus and its local rehearsal as
merged, corrects a Basis paragraph that denied the adapter and boot lifecycle
this same document describes, and narrows the artifact-distribution language to
what the owner's scoped determination settled — pointing at
[`ppd-artifact-distribution-decision.md`](ppd-artifact-distribution-decision.md)
rather than continuing to call the question open. **No requirement is relaxed:**
the 30 s readiness target, the `bundle_bytes * 2.5` headroom rule, every Stage 1
exit criterion, and G1a, G1b, G2 and G3 are unchanged; nothing is enabled, no
image or flag is touched, and no artifact is hosted.

**Revision 7** was authorised by the rollout-premise decision round, after
PR 5 produced and measured a real artifact. It corrects the §1.1 sizing baseline
against measured bytes, separates measurements from calculations, splits G1 into
the per-target gates G1a and G1b, replaces G3's now-impossible "before routing is
introduced" ordering with a satisfiable deploy-and-observe invariant, updates the
implementation status to PRs 1-5, and removes Fly-Volume language from §7.2. **No
requirement is relaxed:** the 30 s readiness target, the `bundle_bytes * 2.5`
headroom rule and every Stage 1 exit criterion are unchanged.

**Revision 6** was authorised by the PR 4 review, which found that §2.5 checked
only the lower coverage bound. It adds the disjoint and extends-past cases, the
guaranteed-surface gap fallback (§2.5), the completeness scoping rule (§3.1.1a),
and the coverage-metadata precondition (§2.5.1). No other section changed.

**Implementation status.** Implemented by **PR 1**: this specification, the
provenance and transport-evidence models, the protocol-neutral exception types,
the optional `snapshot` dependency declaration, and the disabled
`PPD_SNAPSHOT_ENABLED` flag (no observable behaviour change). By **PR 2**: the
live-path correctness containment of section 2.7, the exact-ID taxonomy of
section 2.8, and the subject-property taxonomy of section 2.6. By **PR 3**: the
boot runtime of sections 4.1-4.7 — streaming fetch, verification, hardened
extraction, atomic activation, single-flight locking and readiness states, all
structural and wired to nothing. By **PR 4**: the DuckDB snapshot adapter with
schema, row-count and queryability validation before it may route; lifespan
wiring per section 4.10; coverage routing and the bounded existence probe of
sections 2.4-2.5; live fallback on every typed snapshot failure; and response
wiring of the provenance block across all four consumers.

By **PR 5**: the local build and validation pipeline of section 4.8 — build,
gates, packaging, source receipt, boot check and atomic promotion — local only,
with no upload, image, deployment or flag surface touched.

By **GitHub PR #30** (rollout step 6, first half): the fixed shadow corpus of
section 7.2, as [`docs/design/ppd-shadow-corpus.md`](ppd-shadow-corpus.md) — the
Definition, split from the artifact-bound Instance that is written when the
Stage 1 artifact is selected. By **GitHub PR #31** (rollout step 6, second half):
the local rehearsal of that corpus in `tools/ppd_snapshot/rehearse.py`,
adapter-only and socket-blocked, which ran against one real artifact and
corrected four defects in the Definition before it was frozen. **Neither is
Stage 1**, and the rehearsal produces no Stage 1 evidence — see section 7.2.

The numbering is deliberately explicit: "PR 1"–"PR 5" above are the *specified*
sequence of section 10, which stops at the build pipeline. #30 and #31 are the
GitHub pull requests that merged the corpus work, and conflating the two
numbering schemes is how a reader loses track of which is a plan and which is a
fact.

**Still unimplemented or unperformed:** the **hosting, credentials, transport,
retention and audit design** for artifact distribution, and its implementation
(§6, and the decision record it now points at); the dependency-only image
rollout; real completion of G1a, G1b, G2 and G3; the **Stage 1 corpus Instance**
and the Stage 1 production shadow itself, for which no production dual-read
implementation exists; snapshot enablement at any stage; and the v1.15 release.
`PPD_SNAPSHOT_ENABLED` remains off in all checked-in configuration, neither
production image installs the `snapshot` extra, and no request is served from a
snapshot in production.

**Deliberately not implemented, and not deferred by omission:** auto-escalation
stays disabled on both sources. The snapshot adapter does supply the
limit-independent evidence section 8 anticipated, but re-enabling widening
changes which area a caller's request covers, which is a behaviour change of its
own and was not in PR 4's scope. Both paths return the requested geography with
a source-specific warning.

**Governing rule:** this specification governs PRs 1–4; **no implementation PR
may land before the specification that governs it.**

**Basis:** the sizing, layout and latency figures throughout come from Phase 2
(contract prototype) and Phase 3 (full-history validation), both local-only, in
which `PricePaidDataClient.sparql_search` was patched in a lab harness. **That is
their provenance, not a statement about what exists today:** PR 3 shipped the
boot runtime and PR 4 the snapshot adapter and its lifespan wiring, both in
`property_core.snapshot` and both asserted to be wired in
`tests/snapshot/test_rollout_prerequisites.py`. What no figure here rests on is a
*deployed* measurement — none has been taken on either Machine, which is what
G1a and G1b exist to produce.

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

| Partitions | Years | Size | Transfer @100 Mbit/s |
|---|---|---|---|
| 10 | 2017–2026 | 193 MiB — **estimated** (year+area basis) | 16.2 s — **calculated from that estimate** |
| **11** | **2016–2026** | **266.2 MiB — measured (year-only)** | **22.3 s — calculated from the measurement** |
| 12 | 2015–2026 | 244 MiB — **estimated** (year+area basis) | 20.4 s — **calculated from that estimate** |

**The eleven-partition row is the only measured row.** 279,109,872 bytes
(266.2 MiB), from two independent local builds on 2026-08-28 that produced a
byte-identical bundle (`docs/ops/ppd-snapshot-build.md`).
An earlier revision published 214 MiB here — a superseded year+area measurement
applied to a year-only layout, when §1.2 mandates year-only and the same Phase 3
run measured that layout at +22%. The 10- and 12-partition rows remain year+area
**estimates**, retained only for shape; their transfer times are calculated from
those estimates and are therefore doubly derived.

**22.3 s is arithmetic, not a measurement**: 279,109,872 × 8 / 1e8, assuming full
link utilisation and zero protocol overhead. It leaves ~7.7 s inside the 30 s
readiness target — down from the ~12 s the superseded figure implied. No real
transfer has been timed on either Machine; only G1a/G1b can produce one. Phase 3
measured extract+probe at 2.0 s on a 3.55x larger bundle (945.5 MiB).

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

**Amended after PR 4 review (rev 6).** Rev 5 specified only the *lower* bound.
That left a request for a period entirely after `coverage_to` — next month, say
— running against the snapshot, matching nothing, and returning an empty result
marked `sample_complete: true`: a confident statement that no such sales exist,
made by a source that could not have known. **The whole interval is checked.**

For surfaces taking explicit dates (`/v1/ppd/transactions`, `/v1/ppd/blocks` via
`months`, and CLI equivalents), evaluated in order:

1. Requested range inside coverage → SNAPSHOT, `source: "snapshot"`.
2. **Range disjoint from coverage** — it starts after `coverage_to`, or ends
   before `coverage_from` → **HTTP 422, typed, structured.** The remedy names
   the boundary that was crossed; telling a caller who asked for next month to
   "set `from_date >= coverage_from`" is advice that cannot work.
3. Range starts before `coverage_from` (overlapping) → **HTTP 422, typed,
   structured. Never a partial 200 that looks complete.**
4. No `from_date` → treated as `coverage_from`, with warning
   `"unbounded from_date narrowed to snapshot coverage"`.
5. **Range extends past `coverage_to`** — including every request with no
   `to_date`, since that means "up to now" → the queried window is **clamped to
   `coverage_to`**, a warning names what was excluded, and the response
   **may not claim completeness** (§3.1.1a). This is deliberately not a refusal:
   the overlap is a useful answer, and refusing every open-ended request would
   make the snapshot unusable.

**Guaranteed surfaces differ only in case 2 and 3.** Their `months` is bounded
and the snapshot is sized for the maximum, so a window reaching past coverage
means a *stale snapshot*, not a request the caller got wrong:

* starts before `coverage_from` → narrow to `coverage_from` and warn;
* **disjoint from coverage** → a typed `snapshot_coverage_gap` failure, which
  routes to the **live source** with a warning. A refusal would blame the caller
  for a window they never chose; an empty result would be a false claim.

### 3.1.1a `sample_complete` is scoped to the requested interval

`sample_complete` may be `true` **only when the caller's entire requested
interval lies inside `[coverage_from, coverage_to]`.** The adapter's
`limit_plus_one` evidence is a fact about what it searched; where part of the
requested window was never in the snapshot, exhausting the remainder proves
nothing about the rest.

Likewise **`offset > 0` withdraws the basis.** A short final page establishes
that the page ended, not that the pages skipped over were examined, and
`sample_complete` is a claim about the whole matching set.

Both withdrawals happen centrally, where the provenance block is built, so no
call site can omit one.

### 2.5.1 Coverage metadata is a routing precondition

Routing answers every coverage question from `coverage_from`, `coverage_to` and
`provisional_from`. Absent or contradictory values do not degrade those answers,
they **remove them silently**: a verification record with no bounds answered a
1995 request from an eleven-year snapshot, reported null coverage, and claimed
the sample was complete.

Before the adapter may route, it requires **both bounds present, valid ISO
dates, and correctly ordered**, and `provisional_from` — if present — inside
them. Anything else is a typed `snapshot_metadata_invalid` failure and the
caller uses the live source.

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
| Snapshot behind the advertised release | n | `snapshot` | 200 | `behind_advertised_release: true` + warning (same-Machine only) |
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
* Limits: `MAX_BUNDLE_BYTES` **1 GiB** (~3.8x margin over the measured
  266.2 MiB bundle); socket
  timeout **10 s**; total download deadline **300 s**; stall detection
  **60 s**. Any breach aborts and deletes the temp file. Both time budgets are
  checked after **every** read, the one returning EOF included — checking only
  on a non-empty chunk let a read that blocked past the budget and then returned
  EOF finish successfully.
* **One socket timeout, not separate connect and read timeouts.**
  `urlopen(timeout=...)` takes a single value covering connection setup and every
  blocking socket operation, so advertising two was a fiction: passing a second
  value to the bundle request simply changed that connection's timeout as well.
  `HttpObjectSource(socket_timeout=...)` is used for both control and bundle
  requests, and is the only real interrupt in this design.
* **Transport timeouts are translated into the typed taxonomy.** A socket
  timeout surfaces as `DownloadDeadlineExceeded` with the original
  `TimeoutError` preserved as its cause, so callers handle one taxonomy rather
  than a bare `builtins.TimeoutError` escaping from urllib.
* **What the time budgets do and do not promise.** Neither is an interrupt.
  `read()` is synchronous, so elapsed time can only be inspected once it
  returns: a read that blocks for ten minutes is *detected* after ten minutes,
  not aborted at 60 s. The bundle stream uses `read1`, which returns after one
  underlying socket read, so the 300 s budget is evaluated at real intervals
  rather than being deferred behind a single `read(n)` that loops internally.
  The 60 s value remains the backstop for sources that cannot honour a socket
  timeout — a local file, a test double — and for a connection that dribbles
  rather than going silent.
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
Extract to `staging/<version>.<rand>/`; verify **structurally** — the archive
member validation above, plus an exact parquet-file count against the manifest
and a full file inventory of paths and sizes; write `.verified.json`;
`os.replace()` into `snapshots/<version>/`; atomically flip `CURRENT` via
temp-file + `os.replace()`.

**The boot runtime never opens the snapshot.** It does not connect DuckDB, run
`count(*)`, or check any schema. "Materialized and structurally verified" is a
weaker claim than "queryable", and reporting the second when only the first was
established would let a well-formed but unusable snapshot be served.
**DuckDB, schema and row-count validation are the routing layer's
responsibility (PR 4), to be performed before it serves anything from the
snapshot.** The earlier wording here described a DuckDB probe; that was the lab
harness's behaviour, and at full history it scans every row.

The verification record persists the **validated coverage, provisional, layout
and provenance fields** carried through from the manifest, so routing can answer
coverage questions from the materialized snapshot alone — offline, and without
re-fetching a manifest that may since have rotated.
**Any failure leaves the previous verified snapshot serving, untouched** —
verified for corrupt manifest, corrupt bundle, digest mismatch, truncated
transfer and hostile archive.

The readiness probe counts Parquet files on the **filesystem**, never via
`count(DISTINCT filename)` (a Phase 3 defect: it scans every row).

### 4.5 States (ephemeral materialization)

**The materialization is ephemeral.** Both production Machines run on Fly's
default root filesystem — `fly.toml` and `fly.app.toml` declare no `[mounts]`, no
Volume and no `persist_rootfs` — so the extracted snapshot is **wiped on every
restart and deploy**. It is that Machine's read-only query database for that
Machine's lifetime, and nothing more. The single-flight lock remains meaningful:
it coordinates the workers sharing one Machine.

Two consequences, both load-bearing:

* **No retention across restarts.** Exactly **one** active snapshot is kept.
  Retaining a "previous" version would imply a rollback path that does not
  survive the restart or deploy a rollback exists for.
* **A snapshot is not a fallback for a source outage.** After a restart there is
  none. **The fallback is the live SPARQL source.**

| State | Readiness | Behaviour |
|---|---|---|
| `ready` | 200 | a **structurally verified** snapshot is materialized on this Machine — digest, member safety and file inventory checked. **Not** a claim that it is queryable; PR 4 validates DuckDB, schema and row counts before routing to it |
| `unready` | 503 | nothing materialized; typed `snapshot_unavailable`, and the caller **falls back to the live source** |

There is deliberately no `ready_stale` state. Where the advertised release cannot
be fetched but a snapshot was already materialized on this Machine — typically by
another worker in the same boot — it is adopted and flagged
`behind_advertised_release`. A same-lifetime convenience, **not a durability
guarantee**.

Startup where this Machine already materialized the advertised version skips the
download (measured in the lab: **0.81 s, 0 bytes**) — same Machine, not across a
restart.

**Published versions are immutable.** One `snapshot_version` names one set of
bytes. If a manifest advertises a version already materialized here under a
*different* `bundle_sha256`, the runtime **fails closed**: it keeps serving what
it has, reports the digest conflict, and does not re-materialise. Publishing
changed bytes requires a **new version**. Version directories are never replaced
in place and never carry generation suffixes — those made a single published
version identify several different snapshots.

### 4.6 Process-safe single-flight
Exclusive `flock()` on `<cache>/.boot.lock` held across download → verify →
extract → activate. A worker that cannot acquire it **blocks** (bounded by
`property_core.snapshot.lock.DEFAULT_TIMEOUT`, default 420 s), then re-reads
`CURRENT` and activates from
cache with **no download**. The lock file records a PID for diagnosis only:
`flock` is released by the kernel when its holder dies, so there is no stale lock
to break, no `LOCK_STALE_SECONDS`, and no PID consulted to decide whether the
lock is held. A leftover lock *file* is never a wedged boot. Staging dirs are
per-attempt (`mkdtemp`) so a broken lock can never produce two writers on one
path. `flock` is advisory and per-host — correct for multiple workers in one
machine; it does not coordinate across machines, and one fetch per machine is
intended.

### 4.7 Cleanup
Retain **only the active** version; delete the rest after a successful
activation. Retention of a previous version was removed once the filesystem was
confirmed ephemeral: it cannot enable a rollback across the very events a
rollback exists for, and keeping it would misrepresent the store as durable.
Staging dirs and temp bundles deleted on every exit path. Before download,
require `bundle_bytes * 2.5` free disk, else fail closed with a typed error.

**Introducing a Volume or `persist_rootfs` is out of scope for the runtime PR.**
If durable retention becomes desirable it is a deployment change with its own
review, and this policy would be revisited alongside it — never assumed by the
runtime.

### 4.8 Build-stage authorisation limits

The build pipeline stage may **build and validate an artifact locally only**.
**No upload, bucket creation, Fly secret, cloud resource or production mutation
is authorised.**

The **scope** of artifact distribution is settled: the owner's determination in
[`ppd-artifact-distribution-decision.md`](ppd-artifact-distribution-decision.md)
permits private delivery of the bundle to project-controlled Fly Machines for
internal, read-only price-information use. **That is a scope decision and
nothing more.** Where a bundle is hosted, how a deployed app authenticates to
it, how long it is retained and how access is audited remain a **separate design
and a separate mutation authorisation**, neither of which this specification
settles. Permission to distribute is not permission to create a bucket, upload
an artifact, or configure Fly.

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

### 4.10 Lifespan wiring (governing rule for PR 4)

Where the runtime is started is part of the design, not an implementation
detail, so it is fixed here before PR 4 begins.

* **Boot once per server process, through the FastMCP lifespan.** Not per
  request, not lazily on first use.
* **Where the MCP app is mounted alongside FastAPI, combine the two lifespans
  explicitly.** Mounting does not chain them; a lifespan that is never awaited
  is a boot that never happens.
* **Runtime state is process-scoped, never MCP session state.** Session state is
  client- and session-scoped, while the materialization belongs to the process
  and the Machine — storing it per session would re-boot per client and leak
  across reconnects.
* **Retain the filesystem single-flight lock** across workers on the same
  Machine. Lifespan wiring coordinates nothing between processes.
* **A startup failure leaves the server available on the live fallback.** Boot
  returning `UNREADY` is a normal outcome, not a startup error: the process must
  come up and serve from the live source.
* **The boot must not gate readiness (rev 9).** The lifespan *starts* the boot
  and returns immediately; ASGI/FastMCP readiness never awaits materialization.
  Phase D measured 36.7 s of materialization plus 3.1 s of validation on the
  2 GB Machine, so on that path an awaited boot did not satisfy the 30 s
  readiness target. A faster transfer might; the point of this rule is that
  readiness no longer depends on the answer. The boot therefore runs
  on its own thread, outside the event loop and outside any cancel scope: the
  work it does is blocking I/O that no cancellation can interrupt, and a
  task-group scope cancelled from a lifespan's `finally` deadlocks when the
  lifespan runs in a portal task. Shutdown stops accepting installs, joins
  briefly, and abandons anything still running; the thread is a daemon.
  **Readiness reports live availability, never snapshot availability.**
* **Shadow mode: `PPD_SNAPSHOT_SHADOW_ENABLED` (rev 9).** A control-only flag.
  It starts exactly the same boot, and never makes the result routable —
  `active_adapter()` continues to consult `PPD_SNAPSHOT_ENABLED` alone, on every
  call. Its purpose is to let full G1a — application time-to-readiness against
  the real lifespan, on the real image and Machine — be measured with a real
  artifact while every user request is still answered from the live source.
  Enabling it is not, and never becomes, permission to serve snapshot data.
* **Boot lifecycle is reported, not inferred.** `snapshot_status()` (and
  therefore `/v1/meta`) carries `state` — `not_started` / `warming` / `ready` /
  `failed` — alongside `enabled`, `shadow_enabled`, `source_error` and the
  artifact identity. `routable` tracks `active_adapter()` and so is true only
  when serving is enabled *and* validation completed; a warming or failed boot
  is visibly distinct from a routing one.

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

The first three are not proposed and stop for review. **The fourth is
determined, for one scope only:**
[`ppd-artifact-distribution-decision.md`](ppd-artifact-distribution-decision.md)
records the owner's determination permitting private delivery of the bundle to
project-controlled Fly Machines, for internal read-only price-information use,
with no public download and no surface serving the bundle or bulk rows. **It
settles that trigger and no other**, and it grants no implementation or mutation
authority. Everything above about placement, address-field use and attribution
is unchanged by it.

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
36. Cleanup retains exactly the active version; no previous version survives
    (§4.7).
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
* **p95 < 1 second on the deployed production Machine and selected artifact,
  measured across the frozen corpus request mix.** *(Revised at rev 10, before
  Stage 1 began — see below.)*

The corpus is agreed before Stage 1 begins and is fixed for the duration.

**Rev 10 revision of the p95 criterion — made before Stage 1 started, and not a
claim that synthetic traffic is organic traffic.** Rev 9 and earlier wrote this
criterion as "p95 < 1 second **on real traffic**", which presumed a
traffic-sampling shadow: a fraction of arriving `comps` requests would be
compared and timed in the request path.

That is deliberately no longer the mechanism, for two reasons.

* **Organic `comps` traffic on `property-shared` is sparse and uncontrolled.**
  A percentile over whatever requests happen to arrive is dominated by whatever
  geography and window a caller happened to choose, and by how few of them there
  were. It measures the callers, not the adapter. Reaching a defensible sample
  size would take weeks, and the resulting mix would still be unknown and
  unrepeatable — a number nobody could reproduce or attribute.
* **The frozen corpus is risk-shaped on purpose.** Its thirteen cases were
  chosen to span the contamination boundary, the thin and dense extremes,
  truncation at `limit`, the widest 120-month window, type and category
  filtering, and the expected-empty cases. That mix is *harder* than organic
  traffic, is identical between runs, and is attributable case by case. A p95
  over it is a statement about the adapter.

The measurement therefore moves to the frozen corpus, executed **on the deployed
production Machine, against the selected artifact** — which is what makes it a
production measurement rather than a workstation one. What is given up is stated
plainly rather than papered over: **the request mix is chosen, not observed.**
This is a gate revision, made before any Stage 1 evidence existed, and it must
never be read as a claim that a corpus run is organic traffic. Nothing else in
the exit criteria is relaxed.

**It also removes permanent production machinery introduced solely for rollout
evidence.** Traffic sampling would have required a background queue, a worker
thread, sampling configuration and a telemetry stream inside the serving
application — code that exists only to measure a rollout, in the request path of
a live service, outliving the gate it was built for. An out-of-band comparator
on the same Machine has none of that: it is not in any request path, so "shadow
comparison never makes a live request fail" holds by construction rather than by
careful coding.

**A local rehearsal is still not Stage 1.** Exercising the fixed corpus against
an already-verified local artifact validates routing, coverage handling and
divergence classification. It runs on a workstation with no live arm, so it is
neither a production-Machine measurement nor a divergence comparison, and it
**cannot satisfy** the p95 criterion or the divergence exit criteria. It must
never be recorded as a Stage 1 result. Consistent with the rule above, live SPARQL is
diagnostic, not the numerical gold standard; any new live SPARQL call is a
separately authorised action.

**Stage 2 — opt-in. Hard deployment gates, measured before the flag is enabled.**

The two facts Phase 3 could not evidence are now **blocking gates**, not caveats:

* **G1a — transient boot behaviour measured on `property-shared`, the 2 GB-RAM
  Stage 2 target.** On that app's actual image and Machine, measure: peak
  transient disk during materialization; the overlap window in which the bundle
  and its extraction are both live; wall-clock transfer time; and time to
  readiness. The materialization is on Fly's **default ephemeral rootfs** —
  neither app declares a Volume or `persist_rootfs` (§4.5) — so the constraint is
  free rootfs bytes, not volume capacity, and it must be observed on the Machine
  rather than assumed. **Where the materialization root resolves
  (`PPD_SNAPSHOT_CACHE_DIR`, default `/tmp/ppd-snapshot`) must first be
  established as disk-backed rather than tmpfs-backed**, or the disk and RAM
  figures mean different things than they appear to. The §4.7
  `bundle_bytes * 2.5` free-space precondition must hold against the real
  measured bundle. The 30 s readiness target is unchanged.

  **Calculated inputs, to be confirmed or refuted by the measurement — never
  reported as its result:** ~534.1 MiB simultaneous bundle-plus-extracted payload
  (266.2 + 267.9, arithmetic only; excludes staging directories, per-attempt
  temporary files and filesystem overhead); ~665.4 MiB preflight threshold
  (`bundle_bytes * 2.5`); ~22.3 s transfer at a nominal 100 Mbit/s. **None of
  these is a measured peak.**

* **G1b — the same measurement on `propertydata`, the 512 MB-RAM Stage 3
  target**, on its own image and Machine, likewise on ephemeral rootfs.

  **Both gates test ephemeral-rootfs disk behaviour; RAM size is a separate
  constraint measured alongside it.** The two targets differ in RAM, image,
  entrypoint and health-check grace period (60 s against 30 s), so no result
  transfers between them. **Passing G1a authorises neither `propertydata` nor
  Stage 3.** Stage 2 requires G1a; Stage 3 requires G1b.
* **G2 — worker count verified, or one worker explicitly pinned.** All Phase 2/3
  RSS figures are a single uvicorn process. Either verify the deployed worker
  count and re-derive the RSS budget for that count, **or** explicitly pin the
  app to one worker and record that as a deployment constraint. Verification is
  read-only; **pinning is a deployment mutation with its own authorisation.**

  **Open, and blocking G2 if the deployed count exceeds one:** a worker waiting
  on the §4.6 single-flight lock can block for up to 420 s, and the Fly
  health-check grace periods are 60 s (`property-shared`) and 30 s
  (`propertydata`). At one worker per Machine the lock never contends and the
  question is moot; above one it must be answered before the flag is enabled.
  **Rev 7 records this and deliberately does not resolve it** — a resolution
  needs deployment evidence or a new operational policy, neither of which a
  documentation correction may invent.

  **Rev 9 narrows, but does not close, this concern.** Rev 7 stated the boot
  "runs inside the lifespan and therefore blocks startup"; under §4.10's
  non-blocking rule it no longer does, so a worker waiting out the 420 s lock no
  longer holds up ASGI startup and no longer interacts with the health-check
  grace periods at all. Those three numbers are reconciled to that extent. What
  remains open is unchanged and still blocking above one worker: the deployed
  worker count is not verified, and the per-worker RSS budget was derived for a
  single uvicorn process. Phase D observed one worker in the checked-in
  `Dockerfile` CMD (no `--workers`), which is configuration evidence, not the
  deployment verification G2 asks for.

* **G3 — the snapshot extra is installed in both production images, and proven
  to be.** The boot runtime imports `duckdb` and `zstandard`, which live only in
  the optional `snapshot` extra. Neither image installs it today
  (`--extra api` / `--extra apps`), which is correct while the flag is off
  because the runtime is never booted. Both packages stay optional and stay
  together in that one extra; neither becomes a required `property_core`
  dependency.

  G3 passes only when all four hold:

  1. **Both production Dockerfiles install `--extra snapshot` unconditionally.**
     **The dependency-only image change must land, deploy and be observed with
     `PPD_SNAPSHOT_ENABLED` off before any snapshot enablement.** An earlier
     revision required this *before routing is introduced*; routing merged in
     PR 4, so that ordering can no longer be satisfied by any future action and
     was replaced rather than quietly dropped. The intent it protected is kept
     in full: the dependency change ships and is observed on its own, carrying
     no behavioural change with it.
  2. **Built-image smoke tests import both `duckdb` and `zstandard`** in the
     actual built image. Reading the Dockerfile is not evidence that the wheel
     resolved, installed and imports on that platform.
  3. **Flag-on with either dependency unavailable fails closed**: the runtime
     raises the typed `snapshot_extra_missing` error, snapshot readiness stays
     **false**, and the live source continues to serve. A missing optional
     dependency must never take the service down or silently half-enable it.
  4. **The production flag is not enabled until those image checks, G2, and the
     G1 gate for the target being enabled, all pass** — G1a for Stage 2 on
     `property-shared`, G1b for Stage 3 on `propertydata`.

  **What the repository test does NOT cover.** `tests/snapshot/test_rollout_prerequisites.py`
  is a **repository-config lint**, not enforcement of G3. It reads the checked-in
  Dockerfiles and fly configs and nothing else, so it cannot see the flag being
  enabled by a **Fly secret** (`fly secrets set PPD_SNAPSHOT_ENABLED=1`), by
  machine environment, or by any deploy-time injection — on those paths it stays
  green while the feature is on and the dependencies are missing. It is kept as a
  cheap secondary guard for the ordinary mistake of enabling the flag in
  checked-in config without adding the extra. Requirements 2 and 3 are what
  actually enforce G3, and both belong to PR 4 / the rollout.

**If any gate fails or cannot be measured, stop before enabling the flag.**
No estimate substitutes for the measurement.

Once G1a, G2 and G3 all pass: enable for `comps`/`yield`/`report`/`blocks` on
`property-shared` only; live adapter as automatic fallback on typed snapshot
errors. Monitor `source` distribution and warning rates. **Stage 3 additionally
requires G1b.**

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
reliability; behaviour on either real Fly Machine — `property-shared` (2 GB) or
`propertydata` (512 MB) — especially transient boot disk on ephemeral rootfs;
concurrency beyond 2 simultaneous queries; soak testing; multi-worker RSS
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

5. **Build pipeline** — *merged (PR 5).* 11-partition year-only build, manifest
   with `provisional_from`, daily release check, monthly rebuild.
   **Local build and validation only. No upload, bucket, Fly secret, cloud
   resource or production mutation** (§4.8). Artifact distribution's **scope is
   determined** — see
   [`ppd-artifact-distribution-decision.md`](ppd-artifact-distribution-decision.md)
   — while its **hosting, credentials, transport, retention and audit remain a
   separate design, and every mutation remains separately authorised.**
6. **Fixed shadow corpus** — *merged (PR #30), and frozen.* Agreed before Stage 1
   and frozen for its duration. Its **local rehearsal** — *merged (PR #31)* — is
   a correctness exercise only: it runs on a workstation with no live arm, so
   it **cannot satisfy** Stage 1's production-Machine p95 or divergence exit
   criteria. The artifact-bound corpus **Instance** is written
   when the Stage 1 artifact is selected, and has not been.
7. **Rollout gates** — G1a (`property-shared`, 2 GB), G1b (`propertydata`,
   512 MB), G2 (verified worker count, or one worker pinned) and G3
   (dependency-only images landed, deployed and observed with the flag off).
   **Any of them failing stops the rollout before the flag is enabled.**
8. **Stage 2 opt-in**, then **Stage 3 default on**.

PR 2 is the only PR in this sequence that changes behaviour, and it does so
without any snapshot dependency: it fixes defects that exist on the live path
today.

Rollback throughout: `PPD_SNAPSHOT_ENABLED=0` plus restart. The snapshot is
derived and disposable; no data migration exists to reverse.
