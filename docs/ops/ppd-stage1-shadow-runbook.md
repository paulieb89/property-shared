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
| `propertydata` / G1b | out of scope; redeployed by the shared release workflow, but unchanged in configuration and scope |

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

## Step 1 — release and deploy (separately authorised)

**Use the established release workflow, not a manual `fly deploy`.** Publishing
a GitHub release runs `.github/workflows/release.yml`, which validates the
released revision, publishes to PyPI, and deploys **both** Fly apps from that
commit.

```
merge PR -> publish a GitHub release -> release.yml:
    validate (_validate.yml)
      -> publish to PyPI
        -> flyctl deploy --remote-only --ha=false                 (property-shared)
        -> flyctl deploy --config fly.app.toml --remote-only ...  (propertydata)
```

A local `fly deploy` ships **the working directory, not a commit**. Stage 1
evidence has to be attributable to a revision — a measurement taken against an
image built from whatever happened to be on a laptop cannot be tied to anything,
and "which code produced this p95?" becomes unanswerable. That is the whole
reason the release path exists; use it.

**This redeploys `propertydata` too.** Say so plainly rather than claiming
otherwise: `release.yml` deploys both apps on every release, so `propertydata`
receives the new image. What does **not** change is its configuration or its
scope — `Dockerfile.app` is untouched by this work, `propertydata` carries no
`PPD_SNAPSHOT_*` secret, its snapshot state stays `not_started`, it does not
carry the comparator, and G1b is neither attempted nor affected. "Untouched"
means untouched in configuration and scope, not that no deploy reaches it.

After the release completes, confirm what is actually running — from the app,
never from git:

```bash
fly image show -a property-shared
curl -s https://property-shared.fly.dev/v1/meta | jq .snapshot
```

A deploy restarts the Machine, so the ephemeral rootfs is wiped and the snapshot
re-materializes. Wait for `state: ready` again before continuing (Phase E
measured ~44 s after readiness). Confirm `enabled: false` and `routable: false`
have not changed.

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

* `unqualified_definitional_cases` — must be empty. `B5` and `B50` are named in
  the Definition because the boundary is a definitional choice, but §4 is
  explicit that an Instance must still qualify them: S2 must be non-empty under
  frozen parameters, and S1 needs a neighbour carrying enough volume for
  B50-in-B5 contamination to be visible at all. Against a near-empty `B50`, a
  clean S1 result proves nothing — the contamination boundary becomes a test
  that cannot fail. Unlike the seven placeholders these cannot be substituted:
  `B5`/`B50` *is* the boundary the corpus is built around.

  The Definition states S1's rule qualitatively ("comparable or greater
  volume"). A tool needs a number, so the threshold is named in
  `MIN_NEIGHBOUR_VOLUME_RATIO` and the **measured ratio is recorded beside it**
  under `threshold_is_an_operationalisation` — judge the operationalisation
  rather than trust it.

**`qualify` exits non-zero on any of those**, so a scripted invocation cannot
mistake an unusable candidate for success.

## Step 3 — review and commit the Instance

Retrieve the candidate, review it, and commit it as **its own small
evidence/configuration change**:

```bash
fly ssh sftp get /tmp/stage1-candidate-instance.json
```

`staleness_bound_days` is **enforced at load, not merely recorded**: the
comparator refuses an Instance older than its own bound. The artifact is fixed,
but the frozen window moves forward every day, so counts qualified months ago
describe a query nobody now runs. Re-run `qualify` rather than reusing them.
`qualified_at` must be a canonical `YYYY-MM-DD` string and may not be in the
future.

Set `governs_run` to the Stage 1 run it governs. The comparator **refuses** an
Instance whose `governs_run` is blank or still carries the placeholder `qualify`
wrote: unfilled, that field ties the Instance to nothing, and its whole purpose
is to record that this review happened. Nothing artifact-specific is hard-coded
in the tool, and the Instance is never read as runtime configuration.

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

`--latency-repeats` is deliberately not a way to lower the bar: the gate is
defined at 30 repetitions per case, and a run producing fewer reports
`insufficient_evidence`, never a pass. `--max-live-per-case` below 1 and
`--latency-repeats` below 1 are **refused before any work happens** — an option
that silently does nothing is worse than no option, because it tells an operator
they have a control they do not have. The live budget
(`max_live_per_case x 13`) is checked before every live call, so the declared
bound survives a code change rather than resting on the shape of the loop.

The run stops, and still writes its report, on any of: a failed `/v1/health`, a
Machine `MemAvailable` below the floor, the deadline, an unclassified
divergence, or a midnight crossing. A health, memory and deadline check also
runs **after the final observation**, so a run cannot finish on a Machine that
went bad during its last case and report a pass measured under conditions
nobody checked.

### Midnight

`comps` derives its window from `date.today()`, so an observation straddling
midnight describes a different window from the one recorded. Such an observation
is **never skipped** — skipping it would leave a report claiming thirteen cases
while holding twelve, and a latency sample short of its declared size, with the
totals concealing both.

The snapshot arm retries up to three times, because a local retry costs nothing.
The live arm does not: a retry there is another request to HM Land Registry and
the correctness pass is budgeted at one per case. A crossing that survives its
retries **aborts the run and writes a failed report**. The two arms of a pair
must also share a calendar date; if they do not, the pair compares two different
windows and the run aborts — nothing downstream could detect that, since both
arms look internally consistent on their own.

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

`exit_criteria` carries one block per criterion, and **every one of them can
only move the verdict towards failure**. There is no path by which a missing
observation, an absent arm, a short sample or an unconfirmed classification
produces a pass: absence is never evidence of compliance.

`all_thirteen_cases_compared` is a precondition for most of the others. A report
covering fewer than thirteen cases with two successful arms each is not a
smaller Stage 1 result — it is not a Stage 1 result.

Four blocks deserve particular care:

**`field_equality_on_shared_ids`** — check `vacuous_comparison_shapes` before
believing a pass. A shape listed there shared **no** transaction id while both
arms returned rows. "100% equality on shared ids" is trivially true over an
empty intersection, which is exactly what a systematic difference in id spelling
between the two sources would produce. The tool reports that as a failure.

**`every_divergence_classified`** — `unclassified` must be `0`. Note that
**live truncation or ordering is classified only from captured live transport
evidence** (`raw_bindings_returned` against `fetch_limit`). Page saturation on
either side is recorded under `context_not_evidence` and classifies nothing: a
live page at `limit` says our own presentation limit was reached, not that the
upstream window was, and a saturated snapshot page says nothing about live at
all. With no transport evidence a divergence stays unclassified and blocks exit,
which is the fail-closed direction.

**`no_unconfirmed_classifications`** — **blocking, not advisory.**
`operator_confirmation_required` counts proposed **later A/C/D revisions**,
which cannot be evidenced from these two sources: confirming one needs the
monthly change records published after the build. While any remain proposed,
Stage 1 cannot exit on this report alone. Obtaining that external confirmation
is a separately authorised step.

**`p95_under_one_second`** — carries a `verdict` of `pass`, `fail` or
`insufficient_evidence`. It requires **exactly 390 observations and exactly 30
for every case**; anything less is `insufficient_evidence`, never a pass, and
`cases_short_of_the_required_repeats` names the shortfall. A total that happens
to come out right while one case was measured 29 times and another 31 is also
`insufficient_evidence` — the percentile would be weighted towards the
over-sampled shapes, which is a different measurement from the one the gate is
defined over. Computed by nearest rank (sorted ascending, 1-based rank
`ceil(p/100 × N)`; for N=390 and p=95 that is rank 371) — an observed value,
never an interpolation. `p50`, `p99` and `max` are reported for context;
**only p95 < 1 s is the gate.**

## Geography containment

`zero_geography_contamination` is checked **at the level each case asked at**,
on **both** arms — contamination is a defect in whichever source produced it, so
neither arm is assumed clean because the other is:

| `search_level` | a row is out of area when |
|---|---|
| `district` | its outcode differs (`B50` in a `B5` result) |
| `sector` | its outcode differs, **or its sector does** (`B5 6` in a `B5 4` result) |
| `postcode` | either of the above, **or it is a different unit in the same sector** |

An outcode-only test passes a sector case handed a neighbouring sector in the
same outcode — which is the sector-isolation trap the Definition names in its
own right (`M3 7` returns only `M3 7`).

Findings are reported at **sector and outcode granularity only**, the hygiene
rule the local rehearsal already follows. A unit-level violation inside the
requested sector is recorded as `same_sector_unit_violations: N` and the
offending postcode is never named: the count is what proves the contamination,
and the unit would be the most identifying value in the report.

## Corpus invariants

`corpus_invariants_hold` asserts Definition §3's universal invariants on the
snapshot arm of every case — the coverage-clamp warning present,
`sample_complete` false, `completeness_basis` null, `recent_period_provisional`
true, answered by the snapshot — plus each shape's own intent: S1's geography
isolation, S4's thin-market flag, S5 and S12 truncated at `limit`, S11 empty
while still flagged provisional, S13 and S14 empty. These are structural, not
situational: a case reporting `sample_complete: true` is a **defect**, not a
divergence.

The same assertions are used by the local rehearsal, from the one shared
Definition module, so the two tools cannot check different things. Each arm also
records `returned_date_from` / `returned_date_to` (Definition §9) — the bounds
that show a window was honoured. Two dates are not a transaction.

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
