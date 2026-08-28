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
| `pp-complete.csv` | HM Land Registry public open data, unauthenticated. ~5.5 GB |
| The release's `ETag` / `Last-Modified` / `Content-Length` | recorded by `check-release` into the release-state file |
| `--coverage-to` | the release's declared coverage end, stated by the operator |

`--coverage-to` and the release record are kept **independent on purpose**: the
coverage gate checks that the operator's declaration matches the end implied by
the release's publication date (a file published in July covers to 30 June).
Deriving one from the other would make the gate say nothing.

## Commands

```bash
# 1. Has HMLR published? HEAD only -- nothing is downloaded.
uv run --extra snapshot python -m tools.ppd_snapshot check-release \
    --state ~/ppd-snapshot/release-state.json

# 2. Build, validate, package, verify the digest, and boot the result
#    through the real runtime and adapter. Stops before packaging if a gate fails.
uv run --extra snapshot python -m tools.ppd_snapshot all \
    --csv  ~/ppd-snapshot/pp-complete.csv \
    --work ~/ppd-snapshot/work \
    --dist ~/ppd-snapshot/dist \
    --coverage-to 2026-06-30 \
    --release-state ~/ppd-snapshot/release-state.json \
    --memory 4GB

# 3. Re-run the gates against an existing snapshot directory.
uv run --extra snapshot python -m tools.ppd_snapshot validate \
    --snapshot ~/ppd-snapshot/work/snapshot \
    --coverage-to 2026-06-30 --source-coverage-end 2026-06-30
```

`--memory` is the DuckDB limit, not a peak-RSS promise; DuckDB spills to
`--work/tmp` beneath it. On a machine with little free RAM, lower it — the build
gets slower, not less correct.

## Outputs

```
dist/current.json                          {"current_manifest": "manifest-<version>.json"}
dist/manifest-<version>.json               exactly the eleven SnapshotManifest fields
dist/snapshot-<version>.tar.zst            eleven year=YYYY/data.parquet members, nothing else
dist/build-report-<version>.json           provenance, timings, per-year rows, boot-check result
```

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
| `rows` | the declared count, the union count and the sum of the parts agree |
| `uniqueness` | `transaction_id` is a key across the whole window |
| `coverage` | the bounds are the intended partition boundary and the release's declared end, and every row falls **inside** them |
| `guarantee` | the window still answers a 120-month request — what makes eleven partitions load-bearing rather than ten |
| `provisional` | the boundary is the computed month and lies inside the window |
| `ordering` | each partition is in `transfer_date DESC, transaction_id ASC`, checked by physical row number |

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

## Stop conditions

Halt and report; there is no override flag for any of these.

* Any gate fails, or the boot check does not end `READY`.
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

**Observed twice on one machine; not a guarantee.** Nothing here establishes that
DuckDB 1.5.5 or zstd promise byte-reproducible output, so the pipeline does not
depend on it: what it checks is the *logical* content digest — same rows, same
values, same order, per partition — which is a property of the build rather than
of the writer.

### What this means for G1

| | Specification §1.1 / §4.7 | Measured |
|---|---|---|
| Bundle size | 214 MiB | **266.2 MiB** (+24.4%) |
| Download @100 Mbit/s | 18.0 s | **~22.3 s** |
| Peak transient boot disk | ~444 MiB implied | **~534.1 MiB** (bundle and extraction both live until the bundle is unlinked) |
| §4.7 free-space precondition (`bundle_bytes * 2.5`) | ~535 MiB | **665.4 MiB** |

These are inputs to G1, not a G1 result: G1 is a measurement on the real 512 MB
Fly machine and is **not** part of this work.

## Known correction required before G1

§1.1 of the frozen specification sizes eleven partitions at **214 MiB**. That
figure is a **year+area** measurement, while §1.2 mandates **year-only**, which
the same Phase 3 run measured at **+22%**. The real year-only bundle is
materially larger (see the table above), which moves two numbers the rollout
depends on:

* the §1.1 download estimate (18.0 s @100 Mbit/s) understates transfer time, and
  therefore overstates the headroom inside the 30 s readiness target; and
* **G1** — transient boot disk on the 512 MB Fly app — must be measured against
  the real bundle size, with §4.7's `bundle_bytes * 2.5` free-space rule applied
  to it.

**The specification is frozen and is not edited by this PR.** Correcting §1.1's
sizing table is a decision round that belongs before G1 and the rollout.
`MAX_BUNDLE_BYTES` (1 GiB) is unaffected and still has ample margin.
