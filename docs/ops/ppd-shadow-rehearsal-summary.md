# PPD shadow-corpus local rehearsal — summary of the 2026-08-28 run

**Reconstructed from commit `6f969eb` and PR #31. This is not the tool's output.**

The rehearsal writes a JSON report to an operator-chosen `--report` path. **That
file was not retained.** A search on 2026-08-29 across this repository, the home
directory and `.ppd-lab/` found no rehearsal report. What follows is a summary of
what those two sources record about the run — prose about a file, not the file.
Nothing here has been re-derived, and no figure appears below that is not stated
in one of those two sources.

**This is a rehearsal result. It can never be filed as Stage 1 evidence.** A
rehearsal has no live arm, so it satisfies no divergence criterion and no p95
criterion. The tool marks its own reports `not_stage_1_evidence`, and the
governing corpus Definition (§9) says the same. Recorded here for continuity
only: what the corpus was exercised against, and how it came out.

---

## What ran

| | |
|---|---|
| Tool | `tools.ppd_snapshot rehearse` — local operator tooling, outside the published wheel |
| Corpus | [`docs/design/ppd-shadow-corpus.md`](../design/ppd-shadow-corpus.md), Definition only |
| Path | snapshot adapter only; no live adapter constructed |
| Artifact | `v20260828T194003Z`, bundle digest `50f802b2…9072c` |
| Network | sockets hard-failed, with a self-check proving the block was armed |

The artifact is the one the build runbook records from the two byte-identical
local builds on 2026-08-28.

## Outcome

| | |
|---|---|
| Exit code | **0** |
| Cases | **13 of 13** |
| Assertions passed | **85** |
| Assertions failed | **0** |
| Assertions not evaluable | **2** |
| Midnight exclusions | none |
| Isolation | socket blocker armed and self-checked |
| Environment | `PPD_SNAPSHOT_ENABLED=0` restored intact after the run |
| Report written | 24.6 KB (the file that was not retained) |

**The two `not_evaluable` assertions are the correct answer, not a failure.**
They are the saturated containment comparisons: at `limit=50`, a paged result
ordered most-recent-first cannot demonstrate set containment, so the question is
unanswerable rather than unmet. `not_evaluable` is counted separately from passes
and never as one; a run may exit 0 with them present and may never exit 0 with a
failure.

## What the run changed

Running the Definition against a real artifact corrected four things in it, none
visible from reading it. All four were applied **before** the corpus was frozen,
so the frozen text is post-rehearsal:

1. **`recent_period_provisional` is universal, not per-case** — it held on all
   fourteen cases then defined, for the same structural reason as the coverage
   clamp. S10 was removed as discriminating nothing; S11 was retained, because an
   empty result that must still be flagged provisional is the control with teeth.
2. **Page-set containment is unanswerable at `limit=50`** — 39 of S3's ids sat
   outside S1's page. Containment moved to full aggregate counts declared in the
   Instance; the rehearsal reports `not_evaluable` with a reason when either side
   is saturated; geography containment, which stays meaningful on any page, is
   always checked.
3. **`not_evaluable` is never a pass.**
4. **The recorded midnight-failure state could not occur** — the exception was
   re-raised before the report was written, making that state unreachable. It now
   writes a failed aggregate-only report.

## Report hygiene

The report carried counts, geography membership, provenance, warning classes,
latency, returned date bounds and invariant outcomes. Transaction-id sets existed
in memory for the containment checks and were discarded. No id, address or sale
value reached the report, and none appears in this summary.

## Status

Rollout step 6 (corpus and local rehearsal) is complete. **Stage 1 is not
started**, and needs three things this run does not provide: a production
dual-read shadow implementation, which does not exist; a Stage 1 corpus Instance
bound to a selected artifact, which is written only when that artifact is
selected; and an artifact materialized on a deployed Machine, which depends on
distribution and gate G1a.
