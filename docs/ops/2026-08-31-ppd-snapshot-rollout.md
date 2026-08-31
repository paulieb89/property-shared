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
