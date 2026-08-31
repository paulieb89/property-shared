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
