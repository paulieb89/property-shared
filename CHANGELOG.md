# Changelog

## v1.15.3 (2026-08-31) — private Tigris snapshot delivery, serving off

**Released with `PPD_SNAPSHOT_ENABLED` off on both apps.** Adds a read-only,
signed `TigrisObjectSource` — the transport the PPD snapshot runtime will use
to fetch a private, credentialed bundle instead of a public URL or local
directory — but nothing routes to it yet: the flag stays unset, and every PPD
surface keeps answering from the live source exactly as before this release.
This is dependency-only and delivery-code-only, per the gated rollout in
`docs/design/ppd-source-routing.md` §7 and
`docs/design/ppd-private-delivery.md`; see those for the remaining gates
(G1a, G1b, G2, Stage 1 exit) still required before any enablement.

### Added

- **`property_core.snapshot.s3_source.TigrisObjectSource`.** Official
  `botocore` SigV4 signing (lazy-loaded from the optional `snapshot` extra);
  explicit bucket-scoped credentials, no discovery or metadata-service lookup;
  fixed HTTPS endpoint; no writes or retries; redirects rejected without
  forwarding credentials; bare object names validated before every request.
  Reuses the existing streamed HTTP transport, `read1` chunking, checksum,
  length and timeout controls unchanged.
- **Non-2xx responses from the source are now typed.** A 4xx/5xx from Tigris
  raises `SnapshotSourceError` (previous cause preserved via `from exc`)
  instead of leaking a raw `urllib.error.HTTPError` — timeouts are unaffected
  and still translate to `DownloadDeadlineExceeded`.
- New configuration, consulted only once a bucket is set:
  `PPD_SNAPSHOT_S3_BUCKET`, `PPD_SNAPSHOT_S3_PREFIX` (default `ppd`, and now
  falls back to that default when explicitly set empty, not just when unset),
  `PPD_SNAPSHOT_S3_ACCESS_KEY_ID`, `PPD_SNAPSHOT_S3_SECRET_ACCESS_KEY`.
  Configuring a bucket alongside `PPD_SNAPSHOT_DIR`/`PPD_SNAPSHOT_URL` is
  rejected as ambiguous; `PPD_SNAPSHOT_DIR` and `PPD_SNAPSHOT_URL` together
  keep the pre-existing precedence (`DIR` wins) unchanged.

## v1.15.2 (2026-08-31) — dependency-only snapshot images, serving off

**No API, response, error or data change.** Both production Dockerfiles
(`property-shared` and `propertydata`) install the optional `snapshot`
extra — `duckdb`, `zstandard`, `botocore` — so the deployed images are ready
for private PPD snapshot delivery. `PPD_SNAPSHOT_ENABLED` remains unset on
both apps: the snapshot runtime never boots, and the live source continues
to serve every request exactly as before this release. No Fly config,
worker, volume, secret or scale change. This is the dependency-only rollout
gate (G3 requirement 1, `docs/design/ppd-source-routing.md`): the dependency
change lands, deploys and is observed with the flag off before any snapshot
code or enablement follows.

## v1.15.1 (2026-08-31) — hotfix: PPD comps no longer blocks the event loop

**Upgrade if you run v1.15.0.** No API, response, error or data change; no
dependency, image, flag or configuration change. One defect, two call sites.

### Fixed

- **`PPDService.comps` ran on the event loop and stalled the whole worker.**
  It is synchronous, and both `GET /v1/ppd/comps` and the MCP `property_comps`
  tool called it directly from inside `async def`. For the whole of an upstream
  Land Registry round trip the single uvicorn worker could not run any other
  task — including `/v1/health`, a constant-returning coroutine that performs
  no I/O. Live PPD queries take 60–120 s; Fly's health check allows 5 s, so the
  check timed out, the Machine left the proxy's candidate set, and requests
  queued behind `could not find a good candidate`. Observed in production on
  2026-08-30 as a total stall of `property-shared` with **load average 0.00**
  and 1.74 GB of 2 GB free — zero CPU while serving nothing is a blocked loop,
  not overload.

  Both call sites now use the bounded `anyio.to_thread.run_sync` pattern that
  `app/api/v1/rightmove.py` already used. Exceptions propagate unchanged, so
  every status code, response shape and the EPC enrichment step are identical.

### Not changed

- **Only `comps` was defective.** It was the only `async def` handler in the
  PPD router; the sibling endpoints and MCP tools are plain `def`, which
  Starlette and FastMCP already run in a threadpool. Tests drive a slow stub
  through the real route and through FastMCP's own dispatcher to demonstrate
  that rather than assert it, and would fail if a sibling were ever converted
  to `async def` without an offload.
- Fly concurrency limits, worker count, Machine count, Docker dependencies and
  `PPD_SNAPSHOT_ENABLED` are untouched, so the fix is observable against an
  unchanged baseline. Whether `hard_limit = 10` is right is a separate question
  to reassess now that the loop no longer blocks — it is backpressure, not a
  bug.

Incident record, with timestamped evidence:
`docs/ops/2026-08-30-property-shared-stall.md`.


## v1.15.0 (2026-08-30) — PPD snapshot source routing + live-path correctness containment

**Five implementation PRs** (#24-#28) and **four rollout-preparation PRs**
(#29-#32), against the design in `docs/design/ppd-source-routing.md`, now at
rev 8. The rollout-preparation PRs change documents, tests and local operator
tooling only: they touch no Dockerfile, fly config, image, secret, dependency,
flag or deployment.

**Released with `PPD_SNAPSHOT_ENABLED` off, and with neither production image
installing the `snapshot` extra** — so nothing is routed to a snapshot, none is
materialized, and every PPD surface answers from live SPARQL. **The live path
itself does change, and that is the point of this release:** read *Changed*
below before upgrading. Every PPD-bearing response also gains an additive
`provenance` block, here declaring `source: "sparql"` and null coverage fields.
The further changes marked *only when a snapshot is enabled and materialized*
ship dormant behind the flag and take effect nowhere in this release.

### Changed — behavioural, read before upgrading

- **PPD auto-escalation no longer widens the search area on the live source.**
  `auto_escalate` is still accepted, but `comps` (and everything derived from it —
  `/v1/ppd/comps`, `property_comps`, `search_comps`, `/v1/analysis/yield`,
  `calculate_yield`, the dashboards) now returns the **requested, narrower**
  geography plus a warning explaining why. The only exhaustion evidence available
  on the live path is `raw_bindings_returned < fetch_limit`, and `fetch_limit`
  derives from the caller's presentation limit — so the same data at `limit=4` and
  `limit=5` could produce different geography. The previous widening was a
  page-size and filtering artefact, not a market judgement. **Callers relying on
  automatic widening will see fewer, closer comparables.** Snapshot routing may
  re-enable it later on limit-independent evidence. *Rental-radius escalation is a
  separate mechanism and is unaffected.*
- **District searches no longer leak neighbouring outcodes.** `STRSTARTS(?postcode,
  "B5")` matched `B50 4AA` — Alcester, ~20 miles from inner Birmingham — silently
  mixing two districts into comparable sales. Results for outcode searches will
  change where a longer neighbouring outcode exists (`B5`/`B50`, `N1`/`N10`,
  `E1`/`E17`, `B1`/`B15`).
- **Malformed postcodes now return a typed 422** on `/v1/ppd/transactions`,
  `/comps`, `/address-search`, `/blocks` and `/v1/analysis/yield`, instead of
  reaching SPARQL and returning an empty `200` that read as "no sales here".
- **`GET /v1/ppd/transaction/{id}`** returns **404** only for the observed
  Linked Data not-found stub, **502** for a malformed-but-successful upstream
  response, and no longer leaks `AttributeError`. Previously every non-object
  `primaryTopic` — including missing, null, list and arbitrary strings — was
  reported as 404, asserting a transaction does not exist when we did not know.
- **`offset > 0` now returns a warning** that offset pagination is unstable and
  may repeat or omit rows across pages.
- **`comps` distinguishes a failed subject-property lookup from no sale history.**
  A failure warns; a genuine no-match does not. Previously both were a silent
  `null`.
- Both `ppd_transactions` tool descriptions no longer claim "every recorded
  transaction"; they state a coverage-bounded, most-recent result that is not a
  complete history, and point at `provenance.older_records_exist` and
  `provenance.sample_complete`.

**Only when a snapshot is enabled and materialized:**

- **`GET /v1/ppd/transactions` and `GET /v1/ppd/blocks` return a typed 422
  `ppd_coverage_error`** when the requested range starts before
  `coverage_from`, instead of a 200 from live SPARQL. The body carries
  structured `requested` and `available` ranges plus a remedy — never prose to
  parse, and never a partial 200, which would be indistinguishable from a
  complete answer. **Callers passing an old `from_date` must narrow the range
  or use `GET /v1/ppd/transaction/{id}`,** which stays on Linked Data and keeps
  working for transactions of any age. The CLI equivalents exit non-zero and
  print both ranges.
- **An absent `from_date` is narrowed to `coverage_from` and warned**, rather
  than continuing to mean "all time".
- **`comps` and everything derived from it narrow rather than refuse.** Their
  `months` is bounded by every surface that exposes it (60 or 120), and the
  snapshot is sized to cover the maximum, so a window reaching past coverage
  means a stale snapshot rather than an impossible request.
- **An empty dateless result is never allowed to read as "never sold".** On zero
  rows from a narrowed window, one bounded existence probe runs against the live
  source: `LIMIT 1`, three-second timeout, no retries. `older_records_exist` is
  `true` (warn), `false` (honest empty, no warning) or `null` (warn). A probe
  that failed or timed out yields `null` and never `false` — `false` is a
  positive claim about the world and only a completed probe may make it. No
  probe is issued when the snapshot returned rows.
- **Every typed snapshot failure falls back to the live source** and says so in
  a warning. A coverage refusal and a malformed postcode are not snapshot
  failures and are never softened into a live retry.
- **The whole requested interval is checked against coverage, not just its
  start.** A range disjoint from coverage — one beginning after `coverage_to`,
  or ending before `coverage_from` — is refused with a remedy naming the
  boundary that was crossed. A range extending past `coverage_to`, which
  includes every request with no `to_date`, is clamped to `coverage_to` with a
  warning naming what was excluded. On bounded-`months` surfaces a disjoint
  window is a `snapshot_coverage_gap` failure and the live source answers,
  because the caller never chose that window.
- **`offset` is honoured on the snapshot path.** Paging is exact — the ordering
  is total, so successive pages neither repeat nor omit a row.
- **Malformed and inverted date ranges are typed caller errors (422
  `invalid_date_range`), on both sources, before either is queried.** Coverage
  decisions compare ISO strings lexically, which is meaningful only for
  well-formed dates: `"nonsense"` sorts after `"2026-06-30"`, so a garbage
  `to_date` read as "beyond coverage" and was silently clamped to it. An
  inverted range (`from_date` after `to_date`) describes an empty window, so it
  passed both coverage checks, matched nothing, and was reported as a
  **complete** empty result. On the live path the same inputs previously gave a
  **502** (a caller error dressed as an upstream outage) and an empty **200**.

### Added

- **Snapshot boot runtime** (`property_core.snapshot`) — streamed verified
  download, hardened archive extraction, staging with atomic activation,
  single-flight process locking, and readiness states. **Wired to nothing:** it
  is not booted by any request path, does not query a snapshot, and changes no
  response. No hot refresh.
  **Readiness is structural, not queryable:** the runtime verifies the published
  digest and length, validates every archive member, and checks an exact file
  inventory. It never opens the snapshot, connects DuckDB or checks a schema —
  DuckDB, schema and row validation belong to the routing layer, before it
  serves anything from the snapshot. The verification record persists the
  validated coverage, provisional and layout fields so routing can answer
  coverage questions offline.
  **Ephemeral by design:** both Machines run Fly's default rootfs with no Volume
  and no `persist_rootfs`, so the extracted snapshot is wiped on restart and
  deploy. It is that Machine's read-only query database for its lifetime — one
  active snapshot, no retention of a previous version, and no durability claim.
  When no snapshot is materialized the caller **falls back to the live SPARQL
  source**, not to a cache. No Volume or persistent-rootfs change is made here.
- **Rollout gate G3 recorded:** the boot runtime needs `duckdb` and `zstandard`,
  which live only in the optional `snapshot` extra. Neither production image
  installs it (`--extra api` / `--extra apps`), which is correct while the flag
  is off because the runtime is never booted. G3 requires all four of: both
  Dockerfiles installing `--extra snapshot` unconditionally, with that
  dependency-only change landing, deploying and being observed while
  `PPD_SNAPSHOT_ENABLED` is off, before any snapshot enablement; built-image
  smoke tests importing both packages in the actual image; flag-on with either
  dependency unavailable failing closed with snapshot readiness false; and the
  production flag staying off until those checks, G2, and the G1 gate for the
  target being enabled — G1a for `property-shared`, G1b for `propertydata` —
  all pass. Requirements 2 and 3 belong to PR 4 / the rollout.
  A repository-config lint ships here as a **secondary guard only** — it reads
  checked-in Dockerfiles and fly configs, so it cannot see the flag being enabled
  by a Fly secret or injected environment. Both packages stay optional and stay
  together; neither becomes a required dependency. The Dockerfiles are
  deliberately unchanged.
- `zstandard` added to the optional `snapshot` extra. The bundle is `.tar.zst`;
  Python 3.11 has no stdlib zstd and neither production image installs the `zstd`
  binary, so without a reader the runtime could not open a real bundle.
- `warnings` on `PPDCompsResponse`, `YieldAnalysis` and `MarketAnalysis`, carried
  through REST, both MCP servers, the CLI, the HTML report and the comps, yield
  and unified dashboards — including each dashboard's LLM-facing text, not only
  its visual tree. A derived figure is never presented without the caveat
  attached to the data it came from.
- **Provenance block on every PPD-bearing response** — `source`,
  `source_release`, `snapshot_imported_at`, `coverage_from`/`coverage_to`,
  `freshness_days`, `recent_period_provisional`, `older_records_exist`,
  `sample_count`/`sample_limit`/`sample_complete`, `completeness_basis`,
  `attribution_ref` and `warnings`. Additive and nullable: a caller that ignores
  it sees no change. Carried through REST (`/v1/ppd/comps`,
  `/v1/ppd/transactions`, `/v1/ppd/address-search`, `/v1/ppd/transaction/{id}`),
  both MCP servers, and the CLI. **Mixed-source responses declare both halves
  separately:** comps may come from the snapshot while `subject_property`
  carries its own `source: "sparql"`, because a property's history routinely
  predates coverage. `YieldAnalysis` carries `sale_provenance` for the same
  reason a yield carries its comps warnings.
- **`sample_complete` is never inferred from counts.** It defaults `false` and
  is `true` only with a stated `completeness_basis`: `limit_plus_one` from the
  snapshot adapter, or `source_exhausted` from an explicit transport-layer
  observation. `sample_count = 3` against `sample_limit = 5` is legitimately
  incomplete. It is additionally **scoped to the requested interval** — an
  interval reaching past either coverage bound was only partly searched — and is
  **withdrawn whenever `offset > 0`**, because a short final page says the page
  ended, not that the pages skipped over were examined. Both withdrawals happen
  where the block is built, so no call site can omit one — and `SnapshotPage`,
  which is exported, no longer hands out a basis at a non-zero offset in the
  first place. Its `exhausted` flag remains page-scoped and true.
- **Every Parquet partition is validated individually** before the union view
  exists. `union_by_name` fills a column a partition lacks with NULLs, so a
  single partition missing `outcode` passed a check over the combined view,
  silently contributed no rows to any outcode search, and the short result was
  then reported as exhaustive — a whole year of sales gone, with the response
  saying nothing was missing.
- **Coverage metadata is a routing precondition.** Both bounds must be present,
  valid ISO dates and correctly ordered, and `provisional_from` must lie inside
  them; anything else is a typed `snapshot_metadata_invalid` failure and the
  caller uses live. A record with no bounds previously answered a 1995 request
  from an eleven-year snapshot, reported null coverage, and claimed the sample
  was complete.
- **DuckDB snapshot adapter** (`property_core.snapshot.adapter`) — the layer that
  turns a structurally verified snapshot into a routable one. Before it answers
  anything it validates the column schema and types, checks the row count
  against the verification record, and executes a real query. Each failure is a
  typed `SnapshotFailure`, so an unusable snapshot becomes a live fallback and
  never an empty result set. Geography is `outcode = ?` / `sector = ?` against
  materialized columns, so `B5` cannot match `B50` by construction; filters are
  pushed into SQL, which is what makes its `limit + 1` completeness evidence
  independent of the caller's page size.
- **Boot wiring through the FastMCP lifespan** (`property_core.snapshot.bootstrap`)
  — once per server process, never per request and never lazily on first use.
  `app/main.py` awaits the FastMCP lifespan explicitly from inside its FastAPI
  lifespan, because mounting does not chain them. Runtime state is
  process-scoped, never MCP session state, and the filesystem single-flight lock
  still coordinates the workers on a Machine. **A boot failure is not a startup
  error:** the server comes up and serves from the live source.
- **HM Land Registry attribution at `GET /v1/meta`**, in CLI `meta`, and in both
  MCP `instructions` strings. Responses carry the compact `attribution_ref`
  pointing there; licence prose is never inlined into a data payload.
- Provenance and evidence models (`PPDProvenance`, `TransportEvidence`,
  `SourceKind`, `CompletenessBasis`), `CoveragePolicy`, and the typed error
  taxonomy (`PPDError`, `PPDCoverageError`, `InvalidPostcodeError`,
  `TransactionNotFoundError`, `UpstreamShapeError`, `SnapshotFailure`,
  `SnapshotUnavailableError`, `UpstreamUnavailableError`), all exported from
  `property_core`.
- **Local snapshot build and validation pipeline** (`tools/ppd_snapshot/`),
  deliberately outside the published wheel. Builds the eleven year-only Parquet
  partitions from `pp-complete.csv`, publishes the immutable manifest the runtime
  reads plus a separate build report, and gates the artifact on schema and column
  types (per partition, never over the union), row count, `transaction_id`
  uniqueness, declared-coverage containment, the 120-month guarantee, the
  provisional boundary, the file inventory, the bundle digest and deterministic
  ordering. It then boots the result through the real `SnapshotRuntime` and opens
  it with the real `SnapshotAdapter`, which is the only claim worth making about
  a build. Also carries the section 4.9 release check: a `HEAD` on
  `pp-complete.csv` comparing `ETag`/`Last-Modified`/`Content-Length` against the
  recorded release, with the seven-day uningested alert measured from
  observation. **Local only** — no upload, bucket, cloud resource, Fly command,
  secret, image or deployment change (§4.8). Runbook:
  `docs/ops/ppd-snapshot-build.md`.
- **A source receipt binds the CSV to the release it claims to be.** Every gate
  downstream checks the snapshot against itself, so an internally consistent
  snapshot of the wrong file passed all of them: a 131-byte stale CSV built,
  validated and booted `READY` while the release record described a
  999,999,999-byte release under a different ETag. The receipt records the
  SHA-256 and length computed from the file alongside the release's validators,
  and the build refuses unless file, receipt and latest observation all agree.
  A missing receipt is a refusal, not a default, and a receipt cannot be minted
  from a file alone: it requires the SHA-256 captured when the release was
  downloaded, since length agreement lets same-length bytes through under any
  ETag. `download` mints one while streaming the release, taking bytes, digest
  and validators from a single response; `receipt --expected-sha256` is the
  weaker path for a file already on disk, and the receipt records which was
  used. The release check now uses the
  official **HTTPS** endpoint published on GOV.UK rather than the plaintext S3
  website endpoint, so neither the validators nor the body are open to tampering
  in transit.
- **The build fails closed on malformed required source values.** `TRY_CAST`
  silently turned an unparseable price into NULL and published the row as a sale
  with no price, while an unparseable date made a row vanish; every count-based
  gate was happy either way. An unparseable `transfer_date` anywhere, or an
  unparseable `price` or blank `transaction_id` inside the window, now stops the
  build, and two new gates enforce it independently: `required_values` (no NULL
  in a required column) and `reconciliation` (rows counted from the source equal
  rows written). A price must be **written as digits**, not merely be castable:
  `TRY_CAST` silently turns `1.5` into 2, `2.5` into 3, `1e3` into 1000, `0x10`
  into 16 and `1_000` into 1000, each landing in the snapshot as a plausible
  integer no gate can question.
- **Releases are assembled outside the publishing directory and promoted only
  after booting.** A forced-`UNREADY` boot previously left the bundle, manifest
  and `current.json` in the final directory — a publishable release nobody had
  validated. Candidates now live under the work directory, not under `dist/`,
  and `current.json` is replaced **last and atomically**: `write_text`
  truncates before writing, so an interrupted promotion used to leave an empty
  pointer where a working release's pointer had been.
- **The expected coverage end cannot be passed in.** `build` and `all` derive it
  from the bound release's publication date; there is no `--source-coverage-end`
  on either. Setting both dates so they agreed published a 28 July release as
  covering 31 July. The declaration is compared with the derived end **before
  the build runs**, so a mismatch writes no Parquet at all rather than leaving a
  failed snapshot directory behind.
- **A failed refresh no longer destroys the release already held.** The
  downloader streams into a unique sibling temporary file and replaces the
  destination only after the transfer's length is confirmed; writing the
  destination directly truncated a working CSV as soon as a refresh began, and
  a mid-stream failure erased it while its receipt survived to describe it. The
  CSV and its receipt are committed as a pair by an explicit transaction that
  removes the renamed-aside backup only after publication or a confirmed
  restoration — if the rollback itself fails the backup is kept and its path
  reported, because it is then the only copy of the previous release — with the
  CSV rolled back if the receipt cannot be written, and a destination that resolves to the receipt path
  is refused before any request. Every document the pipeline replaces — release
  state, receipt, manifest, build report, `current.json` — is now written by
  sibling-and-rename; the release state in particular carries the timestamp the
  seven-day uningested alert is measured from.
- **Promotion is a rename, on one filesystem, and says so.** The device IDs of
  the candidate and dist directories are compared before anything moves;
  `shutil.move` across a boundary would silently copy 266 MiB, which is neither
  atomic nor within the transient-disk and timing model G1 was measured
  against.
- Optional `snapshot` extra (`duckdb==1.5.5`) and `PPD_SNAPSHOT_ENABLED`
  (default **off**). The published library gains no required dependency.
- **The Stage 1 shadow corpus, frozen** (`docs/design/ppd-shadow-corpus.md`) —
  the fixed set of `comps` request shapes the Stage 1 shadow will run through
  both adapters, with frozen parameters, universal invariants, executable
  warning-class predicates, recording rules and a four-class divergence taxonomy.
  Split into a **Definition** and an artifact-bound **Instance**: the Definition
  carries no artifact, date or count, so a monthly rebuild produces a new
  Instance rather than rewriting the evidence for a run already under way.
  Warning *classes* are compared, never warning *text*, because snapshot and
  live warnings are deliberately worded differently by source — and each
  substring is pinned against the call site that emits it, so a reworded warning
  fails loudly instead of leaving the corpus silently matching nothing.
- **A local rehearsal of that corpus** (`tools.ppd_snapshot rehearse`), outside
  the published wheel. Adapter-only, sockets hard-failed with a self-check, the
  instance refused before anything is materialized. Running it against a real
  artifact corrected four things the Definition had wrong, none visible from
  reading it — the provisional flag is universal rather than per-case; page-set
  containment is unanswerable at `limit=50` and moved to declared aggregate
  counts; `not_evaluable` is never a pass; and the recorded midnight-failure
  state could not occur. All four were applied before the freeze.
  **A rehearsal is not Stage 1 and can never become it:** with no live arm it
  satisfies no p95 and no divergence criterion, and its reports are marked
  `not_stage_1_evidence`. Summary of the real run:
  `docs/ops/ppd-shadow-rehearsal-summary.md`.
- **The artifact-distribution scope determination**
  (`docs/design/ppd-artifact-distribution-decision.md`) — the owner's decision
  permitting private delivery of the bundle to project-controlled Fly Machines
  for internal, read-only price-information use. No public download, no surface
  serving the bundle or bulk rows, no address use outside price information,
  attribution unchanged. **It grants no mutation authority:** hosting,
  credentials, transport, retention and audit remain a separate design and a
  separate authorisation, and it settles exactly one of the four Royal Mail
  review triggers in specification §6.
- `docs/design/ppd-source-routing.md` — the frozen specification governing this
  work.

### Fixed

- `record_status` filtering stays disabled, but its documented rationale was
  factually wrong: `lrppi:recordStatus` **does** exist on the SPARQL transaction
  and binds to `.../ppi/add`. The honest reason is that it is not yet supported
  under the verified binding and performance contract. It is now rejected before
  routing, so the snapshot path gives the same explanation and remedy as live.
- **The HM Land Registry attribution statement was emitting the wrong year.**
  `hmlr_attribution()` substituted the current year, so it rendered "2026". The
  year is part of the wording HM Land Registry prescribes, not a copyright
  notice for today: the required statement pins **2021**, as the frozen
  specification quotes it and as the Price Paid Data downloads page states
  (checked 2026-08-28). Now a fixed constant, with the runtime value pinned in
  test alongside the specification — the existing test checked only the
  specification, which is how the wrong year passed review.
- **CLI JSON output is parseable again.** `_echo_json` went through rich's
  `print`, which soft-wraps at the terminal width, so a long value — a coverage
  warning, say — came out with a newline inserted mid-string and the document no
  longer parsed. JSON output exists to be machine-read.

### Not in this work

- **Auto-escalation stays disabled on both sources.** The snapshot adapter does
  supply the limit-independent evidence that would make widening defensible, but
  changing which area a caller's request covers is a behaviour change of its
  own. Both paths return the requested area with a warning saying why, and the
  reason differs by source because the reasons genuinely differ.
- **Rollout gates G1a, G1b, G2 and G3**, and every deployment step behind them.
  No Dockerfile, Fly config, image, secret or deployment is touched here, and
  neither production image installs the `snapshot` extra yet — which G3 requires,
  landed and observed with the flag off, before the flag may be enabled.
- **Artifact distribution, as built.** Its *scope* is now determined (above); its
  hosting, credentials, transport, retention and audit are not designed, and
  nothing is hosted. The build pipeline produces a bundle on a workstation and
  stops there.
- **The Stage 1 production shadow.** No dual-read, sampling or diff-recording
  code path exists in `property_core`, the API or either MCP server. The corpus
  is defined and rehearsed locally; Stage 1 additionally needs that production
  instrumentation, a corpus Instance bound to a selected artifact, and an
  artifact materialized on a deployed Machine.
- **A measurement the rollout needs:** the real eleven-partition **year-only**
  bundle is **266.2 MiB**, not the 214 MiB §1.1 previously estimated — that figure is a
  year+area measurement, while §1.2 mandates year-only, which the same Phase 3
  run measured at +22%. **Corrected in specification rev 7** by the
  rollout-premise decision round: §1.1 now publishes the measured 266.2 MiB with
  22.3 s labelled as calculated, G1 is split into G1a (`property-shared`, 2 GB)
  and G1b (`propertydata`, 512 MB), and G3's ordering clause is replaced with the
  deploy-and-observe invariant. No gate is relaxed, no image or flag is touched,
  and nothing is enabled.


## v1.14.2 (2026-08-26) — MCP server card version; inferred-GBP warning ordering

Two small corrections found by dogfooding v1.14.1 in production. No behaviour change to any tool, endpoint or data value.

### Fixed
- **The MCP app advertised the FastMCP version on its server card.** `initialize` returned `{"name":"property-app","version":"3.2.4"}` — the pinned dependency's version, not the app's. FastMCP falls back to its own when the constructor receives no `version=`, and `property_app/server.py` never passed one, so the protocol card disagreed with the app's own `/.well-known/mcp/server-card.json` route. Pre-existing (v1.13.0 would have reported 3.2.4 too) and cosmetic, but a card that misreports what is deployed defeats its purpose. Both servers now advertise the installed `property-shared` version, asserted through a real `initialize` handshake and against the live well-known route, as a property rather than a literal so it holds across releases.
- **The inferred-GBP warning now leads for scalar SAP certificates.** Every other warning on a certificate explains why something is *absent*; this one qualifies a number that is *present* and that the reader is looking at. Rendered fifth of five in the HTML report it read as boilerplate, so a cost could be taken as measured when only its amount was. Ordering is pinned by test. Modern object-shaped certificates are unchanged — they state their currency and carry no such warning.

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

### Fixed after human review
- **The report service used the inferred cost values but dropped the caveat.** `EPCData.warnings` stopped at `_fetch_epc_data()`, so a report presented GBP amounts whose currency was inferred as though they were stated. `EnergyPerformance` now carries `warnings`, the service propagates them, and the shared HTML report template renders them beside the energy block. Asserted at every step: service output, REST JSON and rendered HTML each disclose it exactly once.
- **`EPCMoney` could be constructed with contradictory provenance.** `EPCMoney(value=...)` produced `currency=None` with `currency_stated=True` — "a currency was stated" and "there is no currency" at the same time. `currency_stated` is now a derived property rather than a settable field, so the contradiction is structurally impossible; a value passed for it is ignored.
- Enrichment and REST-search tests asserted success alone; they now assert the warning propagates with the attached certificate.

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
