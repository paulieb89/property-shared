# Stage 1 shadow comparison — runbook

**Nothing in this runbook has been executed.** It describes the sequence for the
Stage 1 gate; every step is separately authorised. `PPD_SNAPSHOT_ENABLED` is
absent from both applications and stays absent throughout — Stage 1 never routes
a single request to the snapshot.

Governed by [`docs/design/ppd-source-routing.md`](../design/ppd-source-routing.md)
§7.2 (rev 10) and the frozen
[`docs/design/ppd-shadow-corpus.md`](../design/ppd-shadow-corpus.md).

---

## What Stage 1 is here

A **controlled production-Machine corpus run**. The thirteen frozen `comps`
cases are executed on the deployed `property-shared` Machine, against the
selected artifact `v20260828T194003Z` (coverage `2016-01-01..2026-06-30`), which
that Machine has already materialized under `PPD_SNAPSHOT_SHADOW_ENABLED`.

It is **not** a traffic sampler. Rev 10 revised the p95 criterion to say so
explicitly, before Stage 1 began, and records what that gives up: the request
mix is chosen, not observed. Read §7.2 before reading a report.

**Why out of band.** The comparator is a separate process invoked over
`fly ssh console`. It is in no request path, so *"shadow comparison never makes
a live request fail"* holds by construction. Nothing permanent is added to the
serving application: no queue, no worker thread, no sampling configuration and
no telemetry stream that would outlive the gate it was built for.

## Preconditions

| | |
|---|---|
| G1a, G2, G3 | complete — [2026-08-31-ppd-snapshot-rollout.md](2026-08-31-ppd-snapshot-rollout.md) Phase E |
| Artifact | `v20260828T194003Z` materialized and `state: ready` on the Machine |
| `PPD_SNAPSHOT_ENABLED` | **absent** on both apps, and stays absent |
| `PPD_SNAPSHOT_SHADOW_ENABLED` | set on `property-shared` only |
| `propertydata` / G1b | out of scope, untouched |

Confirm the artifact before anything else:

```bash
curl -s https://property-shared.fly.dev/v1/meta | jq .snapshot
# expect: enabled false, shadow_enabled true, state "ready", routable false,
#         version "v20260828T194003Z", coverage 2016-01-01..2026-06-30
```

`routable: false` while `state: ready` is the whole point of shadow mode: the
artifact is validated on the Machine and reachable by no request.

## Step 0 — baseline the Machine

```bash
uv run python scripts/fly_observability_snapshot.py \
    --app property-shared --org personal --window 30m \
    --output docs/ops/evidence/<date>-stage1-before.json
```

Existing tooling, reused deliberately. No new observability platform is
introduced for this gate.

## Step 1 — deploy (separately authorised)

The comparator reaches the Machine through the ordinary image. This is a
dependency-and-tooling change only: no flag, no routing, no behaviour change.

```bash
fly deploy --ha=false            # property-shared only
```

A deploy restarts the Machine, so the ephemeral rootfs is wiped and the snapshot
re-materializes. Wait for `state: ready` again before continuing (Phase E
measured ~44 s after readiness).

## Step 2 — qualify the artifact

Read-only. No download, no live call, nothing written into the snapshot.

```bash
fly ssh console -a property-shared
cd /app
PPD_SHADOW_COMPARE_ENABLED=1 python -m tools.ppd_snapshot.stage1_shadow \
    qualify --out /tmp/stage1-candidate-instance.json
cat /tmp/stage1-candidate-instance.json
```

It emits a **candidate** Instance: the full bundle digest and version, the seven
selected geographies with the rule and measurement each satisfied, and the
`S1_full` / `S3_full` / `S9_full` aggregate baselines.

Check two fields before going further:

* `unqualified_placeholders` — must be empty. A placeholder the artifact could
  not qualify has no geography, and the corpus cannot run without one.
* `baselines_satisfy_their_relations` — must be `true`. If it is `false`,
  `baselines_refusal` says which relation failed; the Definition's remedy is a
  substituted geography with recorded justification, which is an authoring
  decision, not one this tool may make.

## Step 3 — review and commit the Instance

Retrieve the candidate, review it, and commit it as **its own small
evidence/configuration change**:

```bash
fly ssh sftp get /tmp/stage1-candidate-instance.json
```

Set `governs_run` to the Stage 1 run it governs. Nothing artifact-specific is
hard-coded in the tool, and the Instance is never read as runtime configuration.

**A new artifact creates a new Instance and restarts Stage 1.** It never
silently mutates the corpus.

## Step 4 — run the comparison

```bash
fly ssh sftp shell            # put the reviewed instance at /tmp/stage1-instance.json
fly ssh console -a property-shared
cd /app
PPD_SHADOW_COMPARE_ENABLED=1 python -m tools.ppd_snapshot.stage1_shadow \
    compare \
    --instance /tmp/stage1-instance.json \
    --report   /tmp/stage1-report.json \
    --latency-repeats 30 \
    --max-live-per-case 1 \
    --live-delay-seconds 2.0 \
    --deadline-seconds 3600
```

Two passes:

* **correctness** — every case once through each arm. **One rate-limited live
  observation per case**: thirteen calls to HM Land Registry in total. A retry
  beyond that needs separate authorisation.
* **latency** — the snapshot arm alone, 13 cases × 30 repetitions = **390
  observations**, with **no further live calls at all**.

The run stops, and still writes its report, on any of: a failed `/v1/health`, a
Machine `MemAvailable` below the floor, a snapshot error, the deadline, or an
unclassified divergence.

## Step 5 — close the evidence

```bash
fly ssh sftp get /tmp/stage1-report.json
uv run python scripts/fly_observability_snapshot.py \
    --app property-shared --org personal --window 30m \
    --output docs/ops/evidence/<date>-stage1-after.json
```

Write `docs/ops/<date>-ppd-stage1-shadow.md` with the classification, the
verdict against each exit criterion, and anything the run could not decide.

## Reading the report

`exit_criteria` carries one block per criterion. Three deserve care:

**`field_equality_on_shared_ids`** — check `vacuous_comparison_shapes` before
believing a pass. A shape listed there shared **no** transaction id while both
arms returned rows. "100% equality on shared ids" is trivially true over an
empty intersection, which is exactly what a systematic difference in id spelling
between the two sources would produce. The tool reports that as a failure.

**`every_divergence_classified`** — `unclassified` must be `0`.
`operator_confirmation_required` counts proposed **later A/C/D revisions**,
which cannot be evidenced from these two sources: confirming one needs the
monthly change records published after the build. They are proposed, never
asserted.

**`p95_under_one_second`** — measured over the 390 snapshot-arm observations by
nearest rank (sorted ascending, 1-based rank `ceil(p/100 × N)`; for N=390 and
p=95 that is rank 371). An observed value, never an interpolation. `p50`, `p99`
and `max` are reported for context; **only p95 < 1 s is the gate.**

## Hygiene

Transaction ids and the values of compared fields exist in memory for the length
of one comparison and are then discarded. The report carries counts, month
histograms, field-mismatch tallies, geography results, warning classes, source
evidence, latency, classification and artifact identity. **No id, address, price
or row reaches a report** — the same rule the local rehearsal already follows.

## Rollback

There is nothing to roll back. The comparator routes nothing, installs nothing
into the serving process, downloads no artifact and writes nothing into the
snapshot. Stopping means not running it; `PPD_SHADOW_COMPARE_ENABLED` is never
persisted anywhere.

## What Stage 1 will not prove

* **Later A/C/D revision cannot be machine-evidenced.** It is proposed with
  `operator_confirmation_required`, and because ids are deliberately not
  persisted, chasing a specific row against HM Land Registry is not possible
  from the report alone. An unclassified divergence blocks exit; what further
  evidence to authorise is a decision at that point.
* **False empties and geography contamination are proved for the corpus
  geographies**, which is what the criteria ask — not for the whole artifact.
* **The p95 is over a chosen request mix**, on the deployed Machine and the
  selected artifact. It is not organic traffic and must never be described as
  such.
