# PPD private-snapshot-delivery rollout evidence log

Tracks execution of the gated rollout plan (dependency-only images →
private-delivery code → partial G1a) against
`docs/design/ppd-source-routing.md` §7/§10 and
`docs/design/ppd-private-delivery.md`. `PPD_SNAPSHOT_ENABLED` stays unset on
both apps throughout every phase recorded here — nothing in this document
enables snapshot serving.

## Phase A — dependency-only images, deployed and observed with the flag off

**Goal**: land PR#37 (`feat/ppd-snapshot-image-dependencies`) and deploy it,
satisfying G3 requirement 1 — *"the dependency-only image change must land,
deploy and be observed with `PPD_SNAPSHOT_ENABLED` off before any snapshot
enablement."*

### Merge and release

| Step | Commit/tag | Notes |
|---|---|---|
| PR#37 head re-verified | `56048c4` | Confirmed immediately before merge, `MERGEABLE` |
| PR#37 merged to `main` | `58957ff` | Regular merge commit, branch **not deleted** |
| Version bump PR (#39) | `1e372ac` | `release/v1.15.2`: `pyproject.toml`, `server.json` (both fields), `uv.lock` → 1.15.2. No code change. |
| Release published | tag `v1.15.2`, target `1e372ac` | Preconditions checked from a clean worktree pinned to `1e372ac` before tagging: `HEAD` matches, working tree clean and identical to `origin/main`, versions consistent (1.15.2 everywhere), both Dockerfiles carry `--extra snapshot`, no `.env*` tracked or present. |

### Deployment (`release.yml`, run `33409165110`)

All three jobs succeeded (previous `v1.15.1` release had a partial Fly
failure — this run did not repeat it):

| Job | Result | Duration |
|---|---|---|
| Publish to PyPI | success | 20s |
| Deploy property-shared to Fly | success | 1m27s |
| Deploy propertydata to Fly | success | 1m57s |

PyPI confirmed: `property-shared` 1.15.2 published
(`property_shared-1.15.2-py3-none-any.whl`).

Deployed image identities (both Machines' `GH_SHA` label confirmed
`1e372ac54c252bbd0f019d971b9bb426cd7d1dd8` — the exact release commit):

| App | Machine | Digest |
|---|---|---|
| `property-shared` | `7849207a412608`, version 132 | `sha256:086bbe5a6131f75d2890309822eaf4dc6fa4a48c4f6e469cf83574f55b642379` |
| `propertydata` | `d897115a995d48`, version 54 | `sha256:2c0df1228c26ba8fc004f4a78154f7216469cab0aa5e3bb72badf20fa4e1b35e` |

### Observation

**Health**: both Machines `started`, `1 total, 1 passing` per `fly status`.
External health probes, 5x each, all 200:

- `property-shared` `/v1/health`: ttfb 0.061–0.169s.
- `propertydata` `/health`: ttfb 0.052–0.156s.

**Snapshot flag off — property-shared**: `GET /v1/meta` (the live server
process's own computed state, not a fresh process):
```json
{"snapshot": {"enabled": false, "routable": false, "source_error": null}}
```

**Snapshot flag off — propertydata**: no equivalent HTTP endpoint exists
(`/health` returns only `{"status": "ok"}`; no MCP tool exposes
`snapshot_status()`). Checked directly against the **actual running server
process's own environment** instead of a freshly spawned one: identified the
real process via `/proc/<pid>/cmdline` scan over `fly ssh console`
(`/opt/venv/bin/python /opt/venv/bin/property-app`, PID 634 — not PID 1,
which is Fly's own `/fly/init` supervisor), then read only the
`PPD_SNAPSHOT_ENABLED` entry from `/proc/634/environ`: **absent**
(`grep` exit 1, no other environment content examined or reported).

**G2 — worker count**: exactly one server process found on each Machine via
the same `/proc` scan (`uvicorn ... app.main:app`, PID 635, on
property-shared; `property-app`, PID 634, on propertydata) — confirms the
single-uvicorn-worker assumption underlying prior RSS budget figures, on the
real deployed Machines, read-only (no pinning/deployment mutation).

**G3 requirements 2 & 3 — built-image import + flag-on-missing-dep fails
closed**: `tests/snapshot/image_smoke.py` run against the exact pulled,
digest-identified deployed images (`docker pull
registry.fly.io/<app>@sha256:<digest>` after `fly auth docker`; **not** a
fresh `docker build` from source). Modes `off`, `healthy`, `duckdb`-blocked,
`zstandard`-blocked only — `include-private` (the `botocore`-blocked mode)
deliberately deferred to Phase B, since PR#37 alone doesn't yet add the
`TigrisObjectSource`/S3-bucket branch that mode exercises.

```
{"python": "3.11.16", "duckdb": "1.5.5", "zstandard": "0.25.0", "botocore": "1.43.83"}
{"image": "api", "mode": "off",       "passed": true, "live_fixture_calls": 1}
{"image": "api", "mode": "healthy",   "passed": true, "live_fixture_calls": 0}
{"image": "api", "mode": "duckdb",    "passed": true, "live_fixture_calls": 1}
{"image": "api", "mode": "zstandard", "passed": true, "live_fixture_calls": 1}
```
```
{"python": "3.11.16", "duckdb": "1.5.5", "zstandard": "0.25.0", "botocore": "1.43.83"}
{"image": "mcp", "mode": "off",       "passed": true, "live_fixture_calls": 1}
{"image": "mcp", "mode": "healthy",   "passed": true, "live_fixture_calls": 0}
{"image": "mcp", "mode": "duckdb",    "passed": true, "live_fixture_calls": 1}
{"image": "mcp", "mode": "zstandard", "passed": true, "live_fixture_calls": 1}
```

The `duckdb`/`zstandard`-blocked modes both show the runtime raising the
typed `SnapshotExtraMissingError` and falling back to the live source
(`live_fixture_calls: 1`), matching G3 requirement 3 exactly — a missing
optional dependency fails closed to live, it does not take the service down
or half-enable it. No dependency was removed from, and serving was never
enabled on, the real production images — both smoke runs were against
isolated `docker run` containers built from the pulled deployed images.

### Result

**G3 requirement 1 satisfied**: dependency-only images landed, deployed,
and observed with the flag off, on both apps. **G2 evidence recorded**:
single worker confirmed on both real Machines. **G3 requirements 2–3
evidenced** on the exact deployed image digests. `PPD_SNAPSHOT_ENABLED`
confirmed absent from both apps' real running processes throughout.

**Not yet done** (deliberately, per the rollout plan): PR#38 (private
delivery code) not yet merged/deployed; `include-private` smoke mode not
yet run; G1a/G1b not yet measured; no snapshot credentials installed on
either app.

## Phase B — private-delivery code, merged and deployed with the flag off

**Goal**: retarget, re-verify and merge PR#38 (`feat/ppd-private-delivery`)
onto the post-Phase-A `main`, then deploy and observe it with
`PPD_SNAPSHOT_ENABLED` still off.

### A gap found in Phase A, corrected here

Running the full test suite against PR#38's actual merge candidate (not a
stale branch-tip diff) failed one pre-existing test:
`tests/test_release_manifest_version.py::test_the_changelog_heads_with_the_version_being_built`.
Cause: Phase A bumped `pyproject.toml`/`server.json`/`uv.lock` to 1.15.2 but
never added a `CHANGELOG.md` entry — the full suite was never run against
the release branch before merging it in Phase A, only the version files'
own parsing was checked. Not a defect in PR#38 (its merge-candidate diff
against `main` never touches `CHANGELOG.md`); a gap in Phase A's own
process. Corrected by folding a `CHANGELOG.md` catch-up entry for v1.15.2
into PR#38's own release commit, alongside its own v1.15.3 entry — see
below. Also caught and fixed while doing this: a first attempt regenerated
`uv.lock` before its merge conflict markers were resolved, `uv lock` failed
to parse and the failure went unnoticed by `git rebase --continue` (which
only checks that `git add` was run, not that the result is valid) —
committing `uv.lock` with literal `<<<<<<<`/`=======`/`>>>>>>>` markers
still in it. Found by re-grepping the file before pushing, fixed by hand,
`uv lock` then confirmed clean with no further diff. Full suite green
(1642 passed, 26 skipped) once both were corrected.

### Retarget, re-verify, merge

| Step | Commit | Notes |
|---|---|---|
| PR#38 base retargeted | `main` (was `feat/ppd-snapshot-image-dependencies`) | Did not happen automatically on PR#37's merge (branch wasn't deleted); retargeted explicitly via `gh pr edit`. |
| Changelog + version fix pushed to PR#38's branch | `7f39e77` | Rebased onto post-Phase-A `main` (was originally based on the pre-Phase-A tip); `pyproject.toml`/`server.json`/`uv.lock` → 1.15.3, `CHANGELOG.md` gains both the v1.15.2 catch-up and v1.15.3 entries. |
| Merge candidate built and tested | — | Real rebase result (branch sits directly on `main` as an ancestor, not a synthetic diff), diffed against `main`: exactly the 8 originally-reviewed files plus the 4 version/changelog files, nothing else. Full unit + `tests/snapshot/` suite: **1642 passed, 26 skipped**. Both Docker images rebuilt from the candidate and confirmed to build cleanly (then discarded — pre-merge verification only). |
| PR#38 merged to `main` | `aa112ef` | Branch **not deleted**. |
| Release published | tag `v1.15.3`, target `aa112ef` | Same clean-checkout precondition discipline as Phase A: `HEAD` matches, working tree clean and identical to `origin/main`, versions consistent (1.15.3 everywhere), `CHANGELOG.md` headed `## v1.15.3`, both Dockerfiles carry `--extra snapshot`, no `.env*` tracked or present. |

### Deployment (`release.yml`, run `33415985975`)

| Job | Result | Duration |
|---|---|---|
| Publish to PyPI | success | 27s |
| Deploy property-shared to Fly | success | 57s |
| Deploy propertydata to Fly | success | 1m48s |

Deployed image identities (both Machines' `GH_SHA` label confirmed
`aa112ef842f677261fa6d81252418eebcc7d1ace`):

| App | Machine | Digest |
|---|---|---|
| `property-shared` | `7849207a412608`, version 133 | `sha256:df24d3b26fb296ddba1dc4ca305ce392aa596ba1055919f8c616ae1650c9fe7b` |
| `propertydata` | `d897115a995d48`, version 55 | `sha256:b2aa363db38840cb8c16b4fc83c378eac2048d2c3e5e34f1e24c00d816561b9a` |

### Observation

**Health**: both Machines `started`, `1 total, 1 passing`. External health
probes, 5x each, all 200 (property-shared ttfb 0.055–0.114s; propertydata
ttfb 0.081–0.217s).

**Snapshot flag off — property-shared**: `GET /v1/meta` →
`{"snapshot": {"enabled": false, "routable": false, "source_error": null}}`.
Also confirmed directly against the real running process: identified via
`/proc` cmdline scan (`uvicorn app.main:app`, PID 634 — a fresh PID from the
restart, not the same as Phase A's), `PPD_SNAPSHOT_ENABLED` absent from
`/proc/634/environ`.

**Snapshot flag off — propertydata**: same technique as Phase A (no HTTP
introspection endpoint exists). Real server process identified (`property-app`,
PID 634), `PPD_SNAPSHOT_ENABLED` confirmed absent from `/proc/634/environ`.

**G2 — worker count**: exactly one server process found on each Machine
again, same read-only method as Phase A.

**G3 — full smoke matrix including `include-private`**: now that PR#38's
`TigrisObjectSource`/bucket branch exists on the deployed image, ran all
five `image_smoke.py` modes (`off`, `healthy`, `duckdb`-blocked,
`zstandard`-blocked, `botocore`-blocked) against the pulled, digest-identified
deployed images for both apps — not a rebuild.

```
{"python": "3.11.16", "duckdb": "1.5.5", "zstandard": "0.25.0", "botocore": "1.43.83"}
{"image": "api", "mode": "off",       "passed": true, "live_fixture_calls": 1}
{"image": "api", "mode": "healthy",   "passed": true, "live_fixture_calls": 0}
{"image": "api", "mode": "duckdb",    "passed": true, "live_fixture_calls": 1}
{"image": "api", "mode": "zstandard", "passed": true, "live_fixture_calls": 1}
{"image": "api", "mode": "botocore",  "passed": true, "live_fixture_calls": 1}
```
```
{"python": "3.11.16", "duckdb": "1.5.5", "zstandard": "0.25.0", "botocore": "1.43.83"}
{"image": "mcp", "mode": "off",       "passed": true, "live_fixture_calls": 1}
{"image": "mcp", "mode": "healthy",   "passed": true, "live_fixture_calls": 0}
{"image": "mcp", "mode": "duckdb",    "passed": true, "live_fixture_calls": 1}
{"image": "mcp", "mode": "zstandard", "passed": true, "live_fixture_calls": 1}
{"image": "mcp", "mode": "botocore",  "passed": true, "live_fixture_calls": 1}
```

The new `botocore`-blocked mode shows the same typed-fail-closed-to-live
behavior as `duckdb`/`zstandard`: `SnapshotExtraMissingError`, live fallback,
no crash, no half-enablement — now exercised on the actual
`TigrisObjectSource` code path, not just the pre-existing snapshot classes.

### Result

PR#38 merged and deployed with `PPD_SNAPSHOT_ENABLED` confirmed absent on
both apps throughout, by direct process-environment inspection, not
inference. Full `image_smoke.py` matrix (all 5 modes) passes against both
apps' exact deployed image digests. No snapshot credentials installed on
either app. No Fly config, worker, volume, secret, or scale change beyond
the two release deploys themselves.

**Not yet done** (per the rollout plan, deliberately): Phase C (the
narrowly-scoped boot-only verification tool) not yet started; G1a/G1b not
yet measured even partially; no snapshot credentials installed on either
app.

## Phase C — boot-only verification tool, merged and deployed, no credentials

**Goal**: land the narrowly-scoped boot-only verification tool
(`tools/ppd_snapshot/boot_only_verify.py`) into `property-shared` only,
deploy it, and confirm serving stays off and no snapshot credentials exist
on either app — Phase D (staging/applying credentials and actually running
G1a) is explicitly out of scope here.

### Review round: three blocking gaps found and fixed before merge

The tool was built and opened as PR#43, then held for review rather than
merged immediately (per the rollout plan). Review found three real gaps
against the plan's own contract, all fixed on the same PR before merge:

1. **Phase timing.** The original version reported only
   `SnapshotRuntime.boot()`'s total time, with no separate fetch/extraction
   timing or bundle/extraction overlap window, and RSS/memory sampling
   stopped before `SnapshotAdapter.open()` — excluding DuckDB validation
   memory from `process_peak_rss_bytes`. Fixed by wrapping the exact
   `download_verified`/`safe_extract` calls the runtime makes (patching
   `property_core.snapshot.runtime`'s names for one run, restored after —
   `runtime.py` itself untouched) and widening disk/memory sampling through
   adapter-open validation.
2. **Cleanup could cross into the app cache and fail silently.** The
   collision check rejected the verifier nested inside the app's
   `PPD_SNAPSHOT_CACHE_DIR`, but not the reverse (app cache nested inside
   the verifier, which the unconditional `rmtree` could then delete).
   Cleanup also used `ignore_errors=True`, hiding a removal failure behind
   an apparently successful run. Fixed: nesting rejected in either
   direction; a cleanup failure is now caught, recorded
   (`cleanup_ok`/`cleanup_error`), and folded into the CLI's exit code.
3. **The cold-run gate was user-disableable.** `--expected-bundle-bytes 0`
   let a production invocation weaken the exact-279,109,872-byte check to
   merely `bytes_downloaded > 0`. The flag was removed entirely from the
   CLI; the importable function still accepts the parameter for tests only.

Also added: every result the tool produces — including refusals — now
carries `evidence_scope: "partial_g1a"`, `g1a_complete: false`,
`stage_1_evidence: false` explicitly, replacing a generic label.

**Verification of the fix**: 19 tests (up from 13), full
`scripts/validate.sh` green, and **every new/changed guard
mutation-tested** — each fix was temporarily reverted, its test confirmed
to fail for the stated reason, then restored. Concrete evidence from the
phase-binding mutation test (three independently, deliberately slowed
phases): `fetch_ms=314.0` (300 ms injected), `extraction_ms=1.9`
(un-delayed, correctly small), `validation_ms=157.4` (100 ms injected +
real overhead), `materialization_ms=323.9` (≈ fetch+extraction, correctly
excluding the validation delay).

### Merge and release

| Step | Commit/tag | Notes |
|---|---|---|
| PR#43 opened, held for review | `4efc6e9` | Not merged pending review, per the rollout plan. |
| Fixes for the three gaps above | `8635102` | +6 tests (19 total). Full suite and image re-verified before re-review. |
| CHANGELOG amended | `e471e22` | Corrected release date to 2026-09-01; documented the tool as an `### Added` entry under v1.16.0, stating serving stays off and no credentials are installed. |
| PR#43 merged to `main` | `176c401` | Branch **not deleted**. |
| Release published | tag `v1.16.0`, target `176c401` | Same clean-checkout precondition discipline as prior phases: `HEAD` matches, working tree clean and identical to `origin/main`, versions consistent (1.16.0 everywhere), `CHANGELOG.md` headed `## v1.16.0`, `Dockerfile` carries both `--extra snapshot` and the verifier `COPY`, `Dockerfile.app` correctly unchanged, no `.env*` tracked or present. |

### Deployment (`release.yml`, run `33449116644`)

Note: `release.yml` now runs a `Validate release revision` job first
(added by the separate CI-safety work merged as PR#41/#42 during this
rollout), ahead of publish/deploy.

| Job | Result | Duration |
|---|---|---|
| Validate release revision | success | — |
| Publish to PyPI | success | — |
| Deploy property-shared to Fly | success | 1m10s |
| Deploy propertydata to Fly | success | 1m37s |

Deployed image identities (both Machines' `GH_SHA` label confirmed
`176c401ce2651fb734f7908e566854e3e5cb9aad`):

| App | Machine | Digest |
|---|---|---|
| `property-shared` | `7849207a412608`, version 134 | `sha256:5c1c4039edc1e2e47ca13180c577963272d0399c5593fcad113fc97df925f335` |
| `propertydata` | `d897115a995d48`, version 56 | `sha256:7bc00872498c8a2fdcce8146163b3fa3c2448e96bd8476ac5a2c86a1427be9dd` |

### Observation

**Health**: both Machines `started`, `1 total, 1 passing`. External health
probes, 5x each, all 200 (property-shared ttfb 0.049–0.101s; propertydata
ttfb 0.056–0.118s).

**Snapshot flag off — property-shared**: `GET /v1/meta` →
`{"snapshot": {"enabled": false, "routable": false, "source_error": null}}`.
Also confirmed directly against the real running process
(`uvicorn app.main:app`, PID 634): `PPD_SNAPSHOT_ENABLED` absent from
`/proc/634/environ`.

**Snapshot flag off — propertydata**: same technique (no HTTP introspection
endpoint exists). Real server process identified (`property-app`, PID 634),
`PPD_SNAPSHOT_ENABLED` confirmed absent from `/proc/634/environ`.

**Verifier presence, property-shared only**: `test -f
/app/boot_only_verify.py` on the real deployed Machine — **present** on
`property-shared`, confirmed **absent** on `propertydata` (matching the
plan's property-shared-only scope).

**No snapshot credentials on either app**: `fly secrets list` for both
apps shows only the pre-existing `OPENAI_API_KEY`/`COMPANIES_HOUSE_API_KEY`/
`EPC_API_TOKEN` (property-shared) and `COMPANIES_HOUSE_API_KEY`/
`EPC_API_TOKEN` (propertydata) — no `PPD_SNAPSHOT_S3_*` secret present on
either app.

### Result

The boot-only verifier is merged, released as v1.16.0, and deployed to
`property-shared` only. Serving stays off on both apps, confirmed by direct
process-environment inspection. No snapshot credentials exist on either
app. Stopping here, as instructed — Phase D (staging and applying
credentials, then running the verifier for partial G1a evidence) is not
authorized by this entry and has not started.

## Phase D — credentials installed, boot-only verification run, partial G1a measured

**Date**: 2026-09-01. **Goal**: stage and apply the bucket-scoped ReadOnly
Tigris credentials on `property-shared` only, then run
`/app/boot_only_verify.py` once against the real private artifact to obtain
**partial G1a** evidence. Serving stayed off throughout. No release, no image
change, no `propertydata` work.

The deployed image is unchanged from Phase C: v1.16.0, digest
`sha256:5c1c4039edc1e2e47ca13180c577963272d0399c5593fcad113fc97df925f335`,
label `GH_SHA=176c401ce2651fb734f7908e566854e3e5cb9aad`. No release was needed
— the verifier was already in that image.

### Preconditions, verified before any credential was staged

| Check | Result |
|---|---|
| Machine identity | `7849207a412608`, version 134, `lhr`, `started` |
| Health | `servicecheck-00-http-8080` passing, 1 total / 1 passing |
| Snapshot serving | `GET /v1/meta` → `{"enabled": false, "routable": false, "source_error": null}` |
| Snapshot credentials | `fly secrets list` showed only `OPENAI_API_KEY`, `COMPANIES_HOUSE_API_KEY`, `EPC_API_TOKEN` |
| Worker count | `Dockerfile` CMD is `uvicorn app.main:app --host 0.0.0.0 --port 8080`, no `--workers` → one worker (G2) |
| Verifier present | `test -f /app/boot_only_verify.py` → exit 0 |
| Verify dir absent | `test ! -e /ppd-verify-<ts>` → exit 0 |
| App cache absent | `test ! -e /tmp/ppd-snapshot` → exit 0, nothing previously materialized |
| Rootfs free | 8,319,373,312 B against the §4.7 preflight requirement of 279,109,872 × 2.5 = 697,774,680 B |

Baseline from `scripts/fly_observability_snapshot.py` (1 h window): Machine
memory total 2,064,257,024 B, available 1,791,881,216 B, rootfs free
8,319,373,312 B, process RSS 109,432,832 B, no OOM exits. Three series
returned `no_data` (`app_concurrency`, `instance_exit_oom`, `app_tool_calls`)
— all known-absent corroborating series, not a Phase D failure.

### Credential installation

The owner — not the agent — staged and applied the four values through
`fly secrets import -a property-shared --stage` on stdin followed by
`fly secrets deploy -a property-shared`. The agent never saw, typed, echoed or
logged the values, and never read the contents of `/proc/<pid>/environ`.

Exactly four names were added: `PPD_SNAPSHOT_S3_ACCESS_KEY_ID`,
`PPD_SNAPSHOT_S3_SECRET_ACCESS_KEY`, `PPD_SNAPSHOT_S3_BUCKET`,
`PPD_SNAPSHOT_S3_PREFIX`. **`PPD_SNAPSHOT_ENABLED` was not included**, and was
confirmed absent from the Machine environment by
`grep -ac PPD_SNAPSHOT_ENABLED /proc/self/environ` → `0` (count only; contents
never read). `GET /v1/meta` continued to report `enabled: false,
routable: false` throughout. `propertydata` was untouched.

The Machine restarted 134 → 135 and returned to 1 total / 1 passing.

### Two blockers before a measurement was obtained

**1. Verifier defect — the documented invocation could not run.**
`--verify-dir /tmp/ppd-verify-<ts>` was refused with
`{"refused": "no mount entry matches /tmp"}`. Root cause, reproduced against
the Machine's real `/proc/mounts`: `_filesystem_type()` built its prefix test
as `resolved.startswith(stripped + "/")`, and for the root mount `stripped` is
`"/"`, so the prefix became `"//"` — which no absolute path starts with. The
root filesystem matched only the exact path `/`, never anything beneath it. A
Fly Machine has no dedicated `/tmp` mount (`/tmp` falls under `/`, an overlay
whose upper layer is ext4 on `/dev/vdb` at `/.fly-upper-layer`), so every run
was refused, including the invocation in the tool's own docstring.

Nothing was materialized: the check runs before the verification directory is
created and before the `try/finally`, so the refusal was inert — no Tigris
request, no filesystem change, no cleanup pending. Fix raised separately as a
narrow PR with three regression tests; **not merged, released or deployed**.

**Amendment to the sibling-path requirement, authorised by the owner.** With
the fix undeployed, the verify directory was moved to `/ppd-verify-<ts>` —
parent `/`, an exact mount entry. Recorded explicitly because it departs from
the `/tmp` sibling form: `/` is the *same* disk-backed overlay as `/tmp` (same
device, same free space, same `/.fly-upper-layer` Prometheus series), it
cannot nest with `/tmp/ppd-snapshot` in either direction, and the check's
intent — refuse a tmpfs/ramfs root — is still satisfied, as `/dev/shm` still
resolves to `tmpfs`. The measurement is equivalent to one taken under `/tmp`.

**2. Tigris rejected the first credential pair.** The second invocation
reached materialization and failed with
`SnapshotSourceError: snapshot source returned HTTP 403 for 'current.json'`,
`bytes_downloaded: 0`, `cold_run_valid: false`, `cleanup_ok: true`. No retry
was attempted. Note that HTTP 403 does not distinguish rejected credentials
from a missing object: an S3-compatible store returns 403 rather than 404 when
the key lacks `ListBucket`. The owner replaced both credential values; the
`PPD_SNAPSHOT_S3_BUCKET` and `PPD_SNAPSHOT_S3_PREFIX` digests were unchanged,
so the bucket and prefix were never in question. Machine restarted 135 → 136,
health returned to 1 total / 1 passing.

Neither of these two runs produced any measurement, and neither is recorded as
one.

### The measured run

One invocation, `--verify-dir /ppd-verify-20260901T053928Z`, against artifact
`v20260828T194003Z`. Exit 0.

| Field | Value |
|---|---|
| `evidence_scope` | `partial_g1a` |
| `g1a_complete` / `stage_1_evidence` | `false` / `false` |
| `readiness` | `ready` |
| `version` | `v20260828T194003Z` |
| `reused_existing` | **`false`** — genuinely cold |
| `bytes_downloaded` | **`279109872`** — exactly `EXPECTED_BUNDLE_BYTES` |
| `cold_run_valid` | **`true`** |
| `validated` | `true` |
| `coverage_from` .. `coverage_to` | `2016-01-01` .. `2026-06-30` |
| `behind_advertised_release` | `false` |
| `source_error` | `null` |
| `warnings` | `[]` |
| `fetch_ms` | 35,080.9 |
| `extraction_ms` | 919.3 |
| `overlap_window_ms` | 919.3 |
| `materialization_ms` | 36,699.8 |
| `validation_ms` | 3,108.2 |
| `peak_transient_disk_bytes` | 539,565,056 (514.6 MiB) |
| `machine_min_available_memory_bytes` | 1,707,376,640 (1.59 GiB) |
| `process_peak_rss_bytes` | 118,976,512 (113.5 MiB) |
| `cleanup_ok` / `cleanup_error` | `true` / `null` |

No unexpected fields were present.

### Reading the numbers against the design doc's calculated inputs

The rev-8 figures were explicitly labelled calculations to be confirmed or
refuted. They are refuted in one respect and confirmed in another.

* **Transfer time. Refuted.** The calculation assumed a nominal 100 Mbit/s and
  derived ~22.3 s. Measured: 35.1 s, an effective **63.6 Mbit/s** from Tigris
  to this Machine. The estimate was optimistic by ~57%.
* **Simultaneous payload. Confirmed, with a sampling caveat.** The calculated
  ~534.1 MiB (266.2 + 267.9, arithmetic only) sits just above the measured
  peak of 514.6 MiB. The sampler polls every 0.2 s and extraction lasted only
  0.92 s, so the observed peak is a **lower bound**: at the sampled maximum
  260,455,184 B of payload had been extracted alongside the full bundle,
  roughly 93% of the declared ~267.9 MiB. The true instantaneous peak is
  therefore close to the ~560 MB arithmetic ceiling. Report 514.6 MiB as
  measured, not as the maximum that occurred.
* **Preflight headroom. Ample.** 697,774,680 B required against 8,319,373,312 B
  free — a factor of ~11.9.
* **Memory. Comfortable.** Machine-wide available memory never fell below
  1,707,376,640 B on a 2 GB Machine, and the verifier process peaked at
  118,976,512 B RSS while the live server continued serving.

**The 30 s readiness target is not met by materialization alone.**
`materialization_ms` was 36,699.8 ms, and a further 3,108.2 ms of adapter-open
validation brings the cold path to ~39.8 s before any application startup
work is counted. This is a measured fact about this artifact on this Machine,
not a projection, and it is the single most consequential result of Phase D.
It does not by itself fail G1a — G1a is about application time-to-readiness,
which has not been measured — but no application-startup measurement can be
faster than the materialization it contains. Any plan that assumes a 30 s cold
boot needs to be revisited before enablement.

**The measurement was taken on a depleted CPU burst balance, and that is the
production-representative condition.** `fly_instance_cpu_balance` traces the
Machine restart, not the verifier, as the consumer:

```
05:38:28   25,742
05:38:58    4,544   (-21,198)   <- the restart itself
05:39:28    4,708              <- verifier run starts
05:40:28    4,551
```

The v136 restart burned 21,198 credits a full minute *before* the run began.
The verifier then executed its entire 36.7 s materialization at a balance of
roughly 4,500-4,900 against a pre-restart peak of ~25,700 — that is, at
throttled baseline CPU on a `shared-cpu-1x` — consuming only ~490 credits
itself. CPU busy peaked at 69.9% during the run. The balance recovers at
~299/min, so ~60 minutes to regain the peak.

This matters for how the figure is used. In production the snapshot boot runs
inside the application lifespan, immediately after Machine start — precisely
when the restart has just consumed the burst balance. **The throttled
condition measured here is therefore the realistic one, and re-measuring on a
credit-restored Machine would produce an optimistic number that does not
correspond to a real cold boot.** No such re-measurement was taken, and the
36.7 s figure stands as the production-representative sample.

It also identifies an untested lever: if CPU credit rather than network
bandwidth is the dominant constraint on the cold path, a larger or
dedicated-CPU Machine could change these timings materially. That has not been
measured and is not claimed here.

**On `warnings: []`.** The artifact's `coverage_to` of 2026-06-30 was 63 days
old on the measurement date, beyond the `FRESHNESS_WARNING_DAYS = 45`
threshold. No warning appears here because that threshold is applied in
`property_core/ppd_source.py` at query/provenance time, not at boot. The
verifier performs boot and adapter validation only. The freshness warning will
fire once serving is enabled against this artifact.

### Cleanup and post-run state

`cleanup_ok: true` was corroborated independently: `test ! -e
/ppd-verify-20260901T053928Z` → exit 0. Machine remained version 136 — the
verifier caused no restart — `started`, 1 total / 1 passing,
`GET /v1/health` → 200 in 50 ms, `GET /v1/meta` →
`{"enabled": false, "routable": false, "source_error": null}`.

The after-state collector report corroborates both the materialization and the
cleanup:

| Series | Before | After |
|---|---|---|
| `rootfs_free_bytes` | 8,319,373,312 | 8,319,373,312 |
| `rootfs_free_bytes_min` (15 s resolution) | 8,319,373,312 | 8,038,354,944 |
| `memory_available_min` | 1,791,881,216 | 1,688,379,392 |

Free space returned exactly to baseline, confirming the materialization left
nothing behind.

**The two disk measurements disagree, and the difference is instructive.** The
collector's free-space delta is 281,018,368 B; the verifier's directory-size
peak is 539,565,056 B — roughly double. Fly stores one sample per 15 s, so the
collector's minimum landed at a moment when approximately one payload was on
disk rather than at the brief simultaneous bundle-plus-extraction peak. This is
exactly the resolution limitation recorded in the collector's own
`TRANSIENT_DISK_NOTE`. **The verifier's 0.2 s sampling is authoritative for
transient disk; the collector figure corroborates only** — and here it would
have understated the peak by a factor of ~1.9 if taken as the measurement.

### Result

**Partial G1a. Materialization measured; application startup lifecycle not
measured.**

What this establishes on the real `property-shared` Machine, against the real
private artifact: a genuinely cold fetch of exactly the declared 279,109,872
bytes, its extraction, its adapter-open validation, the transient disk and
memory cost of doing so, and complete cleanup — with serving off and the live
path unaffected throughout.

What it explicitly does **not** establish, and must not be cited as:

* **Not completed G1a.** No application time-to-readiness: no ASGI startup, no
  async lifespan, no single-flight lock behaviour under the deployed worker
  count. A standalone process cannot produce these.
* **Not Stage 1 evidence.** No real-traffic sample, no divergence
  classification.
* **Not G1b.** `propertydata` was not touched: no credentials, no deployment,
  no verifier — it does not carry the verifier in its image.
* **Not authority to enable serving.** `PPD_SNAPSHOT_ENABLED` remains absent on
  both apps.

Credentials remain installed on `property-shared` only. The verifier defect
fix is open as a separate PR and is not merged, released or deployed.

## Phase E — v1.17.0 released with both flags off, then shadow mode enabled; application readiness measured

**Date**: 2026-09-01. **Goal**: release the non-blocking snapshot lifecycle,
deploy it with both flags off, observe both applications, then enable
`PPD_SNAPSHOT_SHADOW_ENABLED` on `property-shared` only and measure the half of
G1a that Phase D structurally could not produce — **application
time-to-readiness against the real lifespan**. `PPD_SNAPSHOT_ENABLED` was not
enabled, Stage 1 was not begun, and `propertydata` configuration was not
touched.

### Release

`v1.17.0`, tag target `eda3a84ac6fe17488778946978c2a0d6801ae436`. Preconditions
checked against that exact revision before publishing: `HEAD` matched
`origin/main`, working tree clean and identical to it, versions consistent at
1.17.0 (`pyproject.toml`, `server.json` ×2, `uv.lock`), `CHANGELOG.md` headed
`## v1.17.0`, `Dockerfile` carrying both `--extra snapshot` and the verifier
`COPY`, `Dockerfile.app` unchanged against `v1.16.0`, and no `.env*` tracked or
present. `./scripts/validate.sh` at that revision: **1767 passed, 27 skipped**.

`release.yml` run `33488039568` — all four jobs succeeded: Validate release
revision, Publish to PyPI, Deploy property-shared, Deploy propertydata.

| App | Machine | Version | Digest | `GH_SHA` |
|---|---|---|---|---|
| `property-shared` | `7849207a412608` | 136 → 137 | `sha256:863733618cc80d35cb2a2f2f8999c17baa74e35e1ce9dc837069e2866d0f0818` | `eda3a84…` |
| `propertydata` | `d897115a995d48` | 56 → 57 | `sha256:c30eacbdb855a9ba0ec4c987acf69d059119e6ca5ac4012050aa71909b802aae` | `eda3a84…` |

### Flag-off observation

Both Machines `started`, 1 total / 1 passing. `property-shared`
`GET /v1/health` 200 in 108 ms; `propertydata` `GET /health` 200 in 133 ms.

`property-shared` `GET /v1/meta` →
`{"enabled": false, "shadow_enabled": false, "state": "not_started",
"routable": false, "source_error": null}`. Nothing was imported and nothing
touched the filesystem, which is what `not_started` asserts.

No `PPD_SNAPSHOT_*` secret existed on `propertydata` before or after.

### Enabling shadow mode on `property-shared` only

`fly secrets set PPD_SNAPSHOT_SHADOW_ENABLED=1 -a property-shared`, initiated
08:43:51 UTC, returned 08:44:10 UTC. Machine event log shows exactly one
`start`, at 08:43:59 UTC — no restart loop, no second start. Machine version
137 → 138; Machine ID, image digest and `GH_SHA` unchanged.

A poller sampled `GET /v1/health` and `GET /v1/meta` every 0.25 s from before
the restart through to steady state (194 samples over 80.3 s).

### The measurement

| Observation | Value |
|---|---|
| First non-200 (restart begins) | 08:43:55.059 |
| Last non-200 | 08:44:01.658 |
| **First 200 — application ready** | **08:44:04.950** |
| **Application unavailable → ready** | **9.89 s** |
| Snapshot state at first 200 | **`warming`** |
| `warming` → `ready` | **44.37 s** (08:44:04.950 → 08:44:49.320) |
| Artifact | `v20260828T194003Z`, coverage `2016-01-01`..`2026-06-30` |
| `routable` true in any sample | **false** (150 samples with `shadow_enabled: true`) |
| `enabled` true in any sample | **false** |
| Non-200 HTTP codes | none |
| Connection errors | 3, all inside the restart window |
| `/v1/health` latency | p50 54 ms, p95 90 ms, max 1423 ms |

**The application was ready in 9.89 s, and it was ready 44.4 s before the
snapshot was.** That is the property the non-blocking lifecycle exists to
produce: readiness is now decoupled from materialization. Under the previous
design the same boot would have held startup for the whole 44.4 s.

Note what the 9.89 s does *not* include: it is measured from the client, so it
spans Fly's Machine stop, guest boot, uvicorn startup and the first successful
health response. It is an upper bound on application readiness as a user
experiences it, not a lower bound on the process alone.

### Resources

| Metric | Before | After |
|---|---|---|
| Machine memory total | 2,064,257,024 | 2,064,257,024 |
| Machine memory available | 1,786,740,736 | 1,766,899,712 |
| Machine memory available, min over window | 1,736,843,264 | 1,736,843,264 |
| Process RSS | 108,531,712 | 157,216,768 |
| Rootfs free | 8,319,373,312 | 8,040,230,912 |
| OOM exits | 0 | 0 |

Process RSS rose **46.4 MiB** — the open DuckDB adapter, retained because this
is the application's own materialization, not a discarded verification. Rootfs
consumed and **retained** 279,142,400 B (266.2 MiB): `du -sh /tmp/ppd-snapshot`
reports 269M, and `find /tmp/ppd-snapshot -name '*.zst'` returns nothing, so the
transient bundle was removed after extraction and only the extracted payload
persists. That is the designed steady state — one ephemeral materialization per
Machine, wiped on restart.

The collector's own transient-disk delta was 281,022,464 B over 61 samples.
Consistent with the retained figure, but at Fly's 15 s resolution it cannot see
the simultaneous bundle-plus-extraction peak — Phase D showed that same
comparison understating the verifier's 0.2 s peak by a factor of ~1.9.

### What this does and does not complete

**Completed here — the readiness limb of G1a.** Application time-to-readiness
was measured on the real image and Machine, through the real ASGI/FastMCP
lifespan, against the real private artifact, with a real materialization
running concurrently. Phase D's boot-only verifier structurally could not
produce this figure.

**Not measured here.** Peak transient disk and the bundle/extraction overlap
window were not captured during this boot: the application boot carries no
0.2 s sampler, and the collector's 15 s resolution is corroborating only. Those
two quantities have measurements only from the Phase D verifier run —
279,109,872 bytes downloaded, 539,565,056 B sampled peak (itself a lower
bound), 919.3 ms overlap window.

**Therefore G1a's four quantities now all have measurements, but not from one
run.** Transfer time, peak transient disk and overlap window come from the
Phase D verifier on the v1.16.0 image as a standalone process; time-to-readiness
comes from this run on the v1.17.0 image through the application lifespan. The
Machine and the artifact are the same in both. Whether that combination
satisfies G1a, or whether a single instrumented application boot is required,
is a gate decision and is **not** claimed here.

**Explicitly not done.** `PPD_SNAPSHOT_ENABLED` was not enabled and remains
absent — confirmed after the change, alongside `PPD_SNAPSHOT_SHADOW_ENABLED`
and the four `PPD_SNAPSHOT_S3_*` credentials. No Stage 1 corpus was run; the
frozen corpus remains `comps` only. `propertydata` received the v1.17.0 image
through the normal two-app release and **no configuration change of any kind**:
it carries no `PPD_SNAPSHOT_*` secret, and with both flags absent its snapshot
state is `not_started`. G1b was not attempted.
