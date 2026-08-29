# PPD snapshot build — local runbook

How the Price Paid Data snapshot is built and validated on a workstation.
Governed by [`docs/design/ppd-source-routing.md`](../design/ppd-source-routing.md)
rev 6 (§1.1–1.3, §4.8, §4.9). The pipeline lives in
[`tools/ppd_snapshot/`](../../tools/ppd_snapshot/) and is deliberately
outside the published wheel.

## Scope — and what this must not do

**Build and validate locally. Nothing else** (§4.8). No upload, bucket, cloud
resource, Fly command, secret, Dockerfile change, deployment config, feature-flag
change, release or version bump happens here or is enabled by anything here.
`--dist` is a directory on this machine; `current.json` is written beside the
manifest only so the whole boot path can be exercised offline through
`LocalDirectorySource`.

**Artifact distribution — where a bundle is hosted and how a deployed app
reaches it — is a separately approved decision** and is not settled by this
runbook.

## Inputs

| Input | Where it comes from |
|---|---|
| `pp-complete.csv` | HM Land Registry public open data, unauthenticated, over **HTTPS**: `https://price-paid-data.publicdata.landregistry.gov.uk/pp-complete.csv` (the [GOV.UK single-file page](https://www.gov.uk/government/statistical-data-sets/price-paid-data-single-file)). ~5.5 GB |
| The release's `ETag` / `Last-Modified` / `Content-Length` | recorded by `check-release` into the release-state file |
| The **source receipt** | minted by `download` while streaming the release, or by `receipt` for a file already on disk — the SHA-256 and byte length computed from the bytes, alongside the validators of the release they arrived with |
| `--coverage-to` | the operator's declaration of the window end, **checked before the build runs** against the end derived from the bound release |

The plaintext S3 *website* endpoint used during the lab phase is not used: over
HTTP both the validators this pipeline trusts and the 5.5 GB body are open to
tampering in transit, and the receipt would then faithfully bind the build to
whatever arrived.

### The source receipt

Every gate after the build checks the snapshot against *itself*, so an
internally consistent snapshot of the **wrong file** passes all of them. A
131-byte stale CSV once built, validated and booted `READY` while the release
record described a 999,999,999-byte release under a different ETag.

The receipt is the binding, and it has to be **grounded in evidence captured at
download time** or it binds nothing: a receipt minted from a file plus a set of
validators accepts any same-length bytes under any ETag. So there are two ways
to obtain one, and they are not equally strong:

* `download` streams the release, digests the bytes as they arrive and reads the
  validators off the **same response** — file, digest and provenance from one
  observation (`evidence: "streamed-download"`). This is the intended path. It
  streams into a unique sibling temporary file and replaces the destination only
  once the length agrees with `Content-Length`, so **a failed refresh leaves the
  release already held byte-for-byte intact**; writing the destination directly
  would truncate a working CSV the moment a refresh began. The CSV and its
  receipt are one fact in two files, so both are written before either is
  published and the CSV is rolled back if the receipt cannot be committed — a
  half-committed pair is worse than a refused refresh, because nothing
  downstream can tell it happened. A destination that resolves to the receipt
  path is refused before any request is made.

  The commit is an explicit transaction (`staged` → `backed_up` →
  `dest_published` → `published`). While it is open, the renamed-aside backup is
  the **only** copy of the previous release, so it is deleted at exactly two
  points: after publication, and after a restoration confirmed to have worked.
  **If the rollback itself fails**, `download` exits `3`, keeps the backup and
  prints its path — see below.
  *It has never been pointed at the real host in this work; no download of the
  5.5 GB object is authorised here, and the mechanism is exercised against a
  loopback server.*
* `receipt --expected-sha256 <digest>` mints one for a file already on disk, and
  refuses unless the file's computed digest matches the digest recorded when it
  was fetched. Weaker — it trusts a record made elsewhere — and the receipt says
  so (`evidence: "recorded-checksum"`).

It then refuses in three directions:

* **file vs recorded download** — minting refuses unless the file's SHA-256 is
  the one recorded when the release was fetched; length agreement alone would
  let same-length bytes through;
* **file vs release** — minting also refuses unless the file's length is the
  length the observed release declares;
* **file vs receipt** — every build recomputes SHA-256 and length, so a file
  edited or replaced since is refused (including an edit that preserves length);
* **receipt vs latest observation** — if `ETag`, `Last-Modified` or
  `Content-Length` have moved, the file on disk is a previous release and the
  build refuses.

There is no default and no override: a missing receipt is a refusal, and
`build` applies the same check as `all` — it writes the artifact `validate` then
blesses, so it is not a way around the binding.

`--coverage-to` and the release record are kept **independent on purpose**: the
coverage gate checks that the operator's declaration matches the end implied by
the bound release's publication date (a file published in July covers to 30
June). `build` and `all` therefore accept **no** way to set that expected end —
a 28 July release was once published as covering 31 July by passing both dates
so they agreed with each other. `validate` still accepts `--source-coverage-end`
as a diagnostic and says out loud when the gate is comparing two operator-stated
dates.

## Commands

```bash
# 1. Has HMLR published? HEAD only -- nothing is downloaded.
uv run --extra snapshot python -m tools.ppd_snapshot check-release \
    --state ~/ppd-snapshot/release-state.json

# 2. Fetch the release and mint its receipt from the same response. (For a file
#    already on disk, use `receipt --expected-sha256 <digest recorded at fetch>`.)
uv run --extra snapshot python -m tools.ppd_snapshot download \
    --dest    ~/ppd-snapshot/pp-complete.csv \
    --receipt ~/ppd-snapshot/receipt.json

# 3. Verify the source, build, validate, package into a candidate, boot it
#    through the real runtime and adapter, and only then promote. Stops before
#    packaging if a gate fails, and before promotion if the boot fails.
uv run --extra snapshot python -m tools.ppd_snapshot all \
    --csv  ~/ppd-snapshot/pp-complete.csv \
    --work ~/ppd-snapshot/work \
    --dist ~/ppd-snapshot/dist \
    --coverage-to 2026-06-30 \
    --release-state  ~/ppd-snapshot/release-state.json \
    --source-receipt ~/ppd-snapshot/receipt.json \
    --memory 4GB
# `--coverage-to` is the operator's declaration. The end it is checked against
# is DERIVED from the bound release's publication date and cannot be passed in:
# a flag that sets both makes the coverage gate compare a claim with itself.

# 4. Re-run the gates against an existing snapshot directory. Without
#    --rows and --eligible-source-rows the reconciliation gate cannot run, and
#    an unrunnable gate is reported as skipped and exits non-zero.
uv run --extra snapshot python -m tools.ppd_snapshot validate \
    --snapshot ~/ppd-snapshot/work/snapshot \
    --coverage-to 2026-06-30 --source-coverage-end 2026-06-30 \
    --rows 10394935 --eligible-source-rows 10394935
```

`--memory` is the DuckDB limit, not a peak-RSS promise; DuckDB spills to
`--work/tmp` beneath it. On a machine with little free RAM, lower it — the build
gets slower, not less correct.

## Outputs

```
work/candidates/candidate-<version>/       assembled here, booted from here -- OUTSIDE dist
dist/current.json                          replaced atomically, LAST, at promotion
dist/manifest-<version>.json               exactly the eleven SnapshotManifest fields
dist/snapshot-<version>.tar.zst            eleven year=YYYY/data.parquet members, nothing else
dist/build-report-<version>.json           provenance, timings, per-year rows, boot-check result
```

**Nothing reaches the dist root until it has booted, and the candidate is not
inside it.** A candidate under `dist/` is still inside the directory something
else may sync, mirror or serve — "ignore the subdirectory" is a convention, not
a boundary — so candidates are assembled under the work directory, booted
through the real runtime from there, and promoted only on `READY`.

**The work and dist directories must be on one filesystem**, and this is
enforced rather than advised: promotion compares their device IDs and refuses
before moving anything if they differ. `os.replace` cannot cross devices and
`shutil.move` silently degrades to a copy — not atomic, and it doubles both the
transient disk and the wall time the G1a/G1b model is derived from, while
leaving a window where a half-copied bundle sits in the publishing directory.
That model is derived, not measured: no wall time has been observed on either
Machine. Promotion is `os.replace` throughout, never a copy.

Promotion moves the bundle, then the manifest, then the report, and replaces
`current.json` **last and atomically** (write a unique sibling, then rename). A pointer is
a promise that what it names is present, and `write_text` truncates before it
writes: interrupted, it would leave an empty pointer where a working one used to
be, taking down the release that was already published. An interrupted promotion
now leaves the previous pointer byte-for-byte intact. A failed boot leaves the
candidate in place for diagnosis and the dist root untouched.

The published manifest carries **only** what
`property_core.snapshot.models.SnapshotManifest` declares. That model is frozen
and `extra="forbid"`, so a manifest carrying build provenance does not degrade
gracefully — it fails to parse at boot and the Machine falls back to the live
source. (The Phase 3 prototype's manifest is exactly that shape: it carries
`source_sha256`, `compression`, `row_group_size` and `logical_sort_order`, and is
not publishable as-is.) Everything else lives in the build report, which nothing
reads at runtime.

## What is checked, and by whom

The gates in `validate.py` check what the build *declared* against what it
*wrote*:

| Gate | What it establishes |
|---|---|
| `partitions` | exactly the eleven expected years, one `data.parquet` each, nothing else in the tree |
| `schema` | every partition on its own terms against `property_core.snapshot.schema.REQUIRED_COLUMNS`, names **and** types — per file, never over the union, because `union_by_name` hides a partition missing a column |
| `required_values` | no row has a NULL `transaction_id`, `price` or `transfer_date`. `TRY_CAST` turns an unparseable value into NULL, which every count-based gate then waves through — the snapshot would serve a sale with no price |
| `reconciliation` | the rows the **source** held for this window, counted from the staged source with its own predicate, equal the rows the snapshot wrote. Every other count comes from the artifact, so a row lost between reading and writing is invisible to all of them |
| `rows` | the declared count, the union count and the sum of the parts agree |
| `uniqueness` | `transaction_id` is a key across the whole window |
| `coverage` | the bounds are the intended partition boundary and the release's declared end, and every row falls **inside** them |
| `guarantee` | the window still answers a 120-month request — what makes eleven partitions load-bearing rather than ten |
| `provisional` | the boundary is the computed month and lies inside the window |
| `ordering` | each partition is in `transfer_date DESC, transaction_id ASC`, checked by physical row number |

The build itself **fails closed** before any of this: a source row whose
`transfer_date` does not parse stops the build outright — it can be neither
placed in the window nor shown to be outside it, so dropping it would be
deciding silently — and a non-canonical `price` or a blank `transaction_id`
*inside* the window stops it too. Rows outside the window are not the
snapshot's problem and are not policed.

**A price must be written as digits, not merely be castable.** `TRY_CAST` is not
a validity test: it accepts and silently *changes* `1.5` to 2, `2.5` to 3, `.5`
to 1, `1e3` to 1000, `0x10` to 16 and `1_000` to 1000. Each lands in the
snapshot as a plausible integer that no gate reading the artifact can question,
so the source text is matched against `^[0-9]+$` before any cast. Signed forms
are refused too: guessing at intent is how the rounding got in.

**Coverage is a declaration about the source release, not a measurement of the
rows.** `min(transfer_date) == coverage_from` is deliberately *not* required: a
window whose first day saw no sale is normal, and requiring it would make the
declaration follow the data instead of the other way round.

Then the artifact is judged by the code that has to serve it: `SnapshotRuntime`
streams and digest-verifies the bundle, extracts it with member validation,
checks the exact Parquet-file count and full file inventory, and activates it
atomically; `SnapshotAdapter.open` runs its own schema, row-count and
queryability validation. `all` exits non-zero unless that ends in `READY`.

## Cadence (§4.9)

* **Daily** `check-release`. One `HEAD`; no download unless the validators moved.
* **Rebuild monthly, following each observed release** — cadence follows the
  release, not the calendar.
* An observed release still uningested after **7 days** raises an alert from
  `check-release`: that means the pipeline is failing, which is a different fact
  from the snapshot merely being old. The clock runs from **observation**, and
  `all` stops it by recording the ingested release in the state file.
* `freshness_days > 45` is a *runtime* warning in the provenance block, not a
  build concern. A stale but verified snapshot is always served in preference to
  going unready.

Every document this pipeline replaces — the release state, the receipt, the
manifest, the build report, `current.json` — is written to a unique sibling,
fsynced, and renamed over its target. `write_text` truncates first, so an
interrupted write would leave an empty file where a working one was; for the
release state that would reset the first-observed timestamp the seven-day alert
is measured from.

### If `download` exits 3

The commit failed *and* the previous release could not be put back. The
destination holds the new bytes, the receipt still describes the old ones, and
the previous release is retained in the temporary file whose path is printed.
Recover by moving that file back over the destination, or by re-running
`download`. Nothing deletes it for you: it is the only copy.

## Stop conditions

Halt and report; there is no override flag for any of these.

* Any gate fails, or the boot check does not end `READY` (nothing is promoted).
* The CSV does not match its receipt, or the receipt does not match the latest
  observed release — including a release that has moved on since the download.
* A source row inside the window has a non-canonical `price` or no
  `transaction_id`, or any source row has an unparseable `transfer_date`.
* The declared `--coverage-to` is not the end the bound release implies. This
  is checked **before the build runs**, so a mismatched declaration writes no
  Parquet at all — a directory that failed validation is still a directory
  someone can point `validate` at.
* The candidate and dist directories are on different filesystems.
* The download destination and the receipt path are the same file.
* The recorded `ETag` differs from the release the CSV was fetched from — a fresh
  5.5 GB download is a cost decision, not something the pipeline should make.
* `transaction_id` is not unique within the window, or the row count disagrees.
* Anything that would need an upload, bucket, Fly command, secret, image change,
  flag change or release.

## Measured results

Recorded from two full local builds on 2026-08-28 (workstation, no network,
no deployed system touched). Source: the HM Land Registry release fetched on
2026-08-27.

| | |
|---|---|
| Source file | `pp-complete.csv`, 5,494,145,759 bytes, sha256 `b643c0ff…4031d0` |
| Source release | ETag `"333695120b2f0a82265a499df7682980-655"`, Last-Modified Tue, 28 Jul 2026 |
| Declared coverage | `2016-01-01` … `2026-06-30`, `provisional_from` `2026-03-01` |
| Source rows | 31,430,611 |
| Rows in the eleven-year window | **10,394,935** |
| Eligible source rows (counted from the source) | 10,394,935 — equal, so nothing was lost between reading and writing |
| Source rows with a malformed required value | 0 (`transfer_date` anywhere, `price`/`transaction_id` in window) |
| Source rows with a non-canonical price | 0 of 31,430,611 — checked across the whole file, not only the window |
| Distinct `transaction_id` | 10,394,935 — equal, so the key holds |
| Rows with no parseable date | 0 |
| Partitions | 11 (`year=2016` … `year=2026`) |
| Parquet on disk | 280,924,336 B (**267.9 MiB**) |
| Bundle `.tar.zst` | 279,109,872 B (**266.2 MiB**), sha256 `50f802b2…9072c` |
| Extracted by the runtime | 280,925,271 B (267.9 MiB) |
| Build | ingest 44.6 s · derive 13.5 s · write 8.7 s |
| Whole pipeline | **82 s** wall clock: build → validate → package → verify → boot |
| Peak RSS | 2,912.5 MB with `--memory 2GB` (DuckDB spills beneath the limit) |
| Boot through `SnapshotRuntime` + `SnapshotAdapter` | **READY**, 1.4 s |
| DuckDB | v1.5.5 |

Rows per partition: 2016 1,046,436 · 2017 1,067,591 · 2018 1,037,613 ·
2019 1,012,160 · 2020 897,565 · 2021 1,281,653 · 2022 1,076,779 · 2023 860,931 ·
2024 929,467 · 2025 932,678 · 2026 252,062.

The 1.4 s boot is from a **local directory** source: it contains no transfer and
is not a readiness-target measurement. Only G1, on the real machine against real
object storage, can produce that.

### Reproducibility, as observed

Two independent full builds from the same CSV produced **byte-identical Parquet
files and a byte-identical bundle** — the same sha256 `50f802b2…9072c` — and
identical logical content digests.

The fail-closed source checks were added after that build and re-run against the
same CSV using the shipped predicates — including the stricter canonical-price
rule: **zero** rows with a malformed required value, **zero** non-canonical
prices anywhere in the 31,430,611-row file, and an eligible source count of
10,394,935 — exactly the published row count. The artifact's content and size
are therefore unchanged by that work, and the build was not re-run. The per-partition content digests recorded in the
build report predate the switch to the length-prefixed encoding and are not
comparable across that change; the bundle digest is.

**Observed twice on one machine; not a guarantee.** Nothing here establishes that
DuckDB 1.5.5 or zstd promise byte-reproducible output, so the pipeline does not
depend on it: what it checks is the *logical* content digest — same rows, same
values, same order, per partition — which is a property of the build rather than
of the writer.

### What this means for G1a and G1b

| | Superseded §1.1 / §4.7 baseline | Now | Class |
|---|---|---|---|
| Bundle size | 214 MiB (year+area) | **266.2 MiB** (+24.4%) | **measured** — 279,109,872 B |
| Extracted | ~230 MiB implied | **267.9 MiB** | **measured** — 280,925,271 B |
| Transfer @100 Mbit/s | 18.0 s | ~22.3 s | *calculated* — bytes × 8 / 1e8 |
| Simultaneous bundle + extracted payload | ~444 MiB implied | ~534.1 MiB | *calculated* — 266.2 + 267.9, arithmetic only |
| §4.7 free-space precondition (`bundle_bytes * 2.5`) | ~535 MiB | ~665.4 MiB | *calculated* — policy constant × measured bytes |

**Only the first two rows are measurements.** The remaining three are arithmetic
over them, and are stated as inputs rather than results. In particular
~534.1 MiB is **not** a measured peak disk figure: it is a sum that ignores
staging directories, per-attempt temporary files and filesystem overhead, and no
overlap has been observed on any machine.

These are inputs to G1a/G1b, not their outcome. **G1a** measures actual
allocation, extraction overlap, transfer and readiness on `property-shared`
(2 GB RAM, ephemeral rootfs); **G1b** repeats it on `propertydata` (512 MB RAM,
ephemeral rootfs). Neither app declares a Fly Volume. Passing G1a authorises
neither `propertydata` nor Stage 3. Neither gate is part of this work.

## Sizing correction — applied in specification rev 7

§1.1 previously sized eleven partitions at **214 MiB** — a superseded year+area
measurement, while §1.2 mandates **year-only**, which the same Phase 3 run
measured at **+22%**. The real year-only bundle is materially larger (see the
table above), which moved two numbers the rollout depends on:

* the §1.1 transfer figure (18.0 s @100 Mbit/s) understated transfer time and so
  overstated the headroom inside the 30 s readiness target — now ~22.3 s,
  calculated, leaving ~7.7 s; and
* the transient-disk budget, now split into **G1a** (`property-shared`, 2 GB) and
  **G1b** (`propertydata`, 512 MB), each measured against the real bundle with
  §4.7's `bundle_bytes * 2.5` free-space rule applied to it.

**Specification rev 7 carries the correction**; this runbook records the
measurement it was derived from. `MAX_BUNDLE_BYTES` (1 GiB) is unaffected and
retains a ~3.8x margin over the measured bundle.
