# PPD shadow-comparison corpus — Definition

**Status: ACCEPTED AND FROZEN, 2026-08-29.** Governed by
[`docs/design/ppd-source-routing.md`](ppd-source-routing.md) rev 8 §7.2, which
this document implements and never overrides.

Frozen for the duration of Stage 1, per §1 and §7.2 of the governing spec.
Amending it mid-flight restarts Stage 1. The text frozen here is **post-
rehearsal**: PR #30 wrote the Definition, and PR #31 ran it against a real
artifact and corrected four things it had wrong — the universal provisional
invariant in §3, the removal of S10, the `not_evaluable` rules in §9, and the
containment qualification moved to the Instance. Freezing the pre-rehearsal
text would have frozen those defects.

**No Instance exists yet, and that is the design, not an omission.** §0 and §10
place the artifact, its qualification and its baselines in an Instance written
**when the Stage 1 artifact is selected** — which has not happened. A rehearsal
instance is a different kind (`instance_kind: "rehearsal"`) and cannot stand in
for one.

**Scope: `comps` only.** The explicit-date coverage-refusal path on
`GET /v1/ppd/transactions` (§2.5) is covered by its own routing tests. Pulling it
in would turn a focused shadow corpus into a multi-surface programme.

---

## 0. Definition and Instance

This document is the **Definition**: request shapes, frozen parameters, semantic
assertions, the divergence taxonomy, warning-class predicates and recording
rules. It contains **no artifact, no execution date and no aggregate counts.**

Those belong to a **corpus Instance**, written when the Stage 1 artifact is
selected:

| | Definition (this file) | Instance |
|---|---|---|
| Contains | shapes, parameters, assertions, taxonomy, predicates, recording rules | selected `snapshot_version` + `bundle_sha256`, qualification date, per-case aggregate baselines, its staleness bound, the Stage 1 run it governs |
| Changes when | the contract changes — a new decision round | a new artifact is selected |
| Lifetime | stable across artifacts | one artifact, one Stage 1 run |

**A new artifact creates a new instance and restarts Stage 1.** It never
silently mutates the corpus. A monthly rebuild legitimately moves counts and
shifts `provisional_from`; under this split that is an expected instance change
rather than corpus drift, and evidence for a run already under way cannot be
rewritten beneath it.

Aggregate figures gathered while selecting the shapes below are **evidence that
each shape is selectable — not a Stage 1 baseline.** They are deliberately not
recorded here.

---

## 1. Purpose, and the explicit non-goal

The corpus is a fixed, pre-agreed set of `comps` requests that the Stage 1
shadow runs through both adapters, **returning the live result** and recording a
structured diff. It exists so that "the snapshot agrees with live" is a claim
about cases chosen in advance, rather than a summary over whatever traffic
happened to arrive. Shadow failures never affect the response.

**Non-goal: live SPARQL is not the numerical gold standard.** A divergence is a
question to answer, not automatically a snapshot defect — live is subject to its
own truncation, timeout and ordering behaviour. Exit requires explanation, not a
similarity score. No case below is written as "the snapshot should return what
live returns"; each is written as "this case exercises risk X, and a difference
must be classifiable".

The corpus is agreed before Stage 1 begins and **frozen for its duration**.
Amending it mid-flight restarts Stage 1.

---

## 2. Frozen parameters

Every case record carries all of the following. **No parameter may be left
implicit in the record**, because a default that changes silently rewrites the
corpus.

The record distinguishes what goes **on the wire** from the **effective
semantics** it selects. At the HTTP surface, omission is the only way to request
the residential default — there is no value that expresses it — so the record
must not claim to send one.

| Parameter | Wire | Effective semantics |
|---|---|---|
| `postcode` | per case | the geography |
| `search_level` | per case — `postcode` / `sector` / `district` | selects geography; **not** a prefix string |
| `months` | per case | the only window control `comps` accepts (§6) |
| `limit` | `50` | `DEFAULT_LIMIT`; caps returned rows |
| `property_type` | **intentionally omitted** | `residential_default (F/D/S/T)` — omitted is not "unfiltered"; the sentinel `ALL` is a different, wider request |
| `transaction_category` | `"A"` | standard residential sales only; excludes category B |
| `filter_outliers` | `false` | when true, drops rows from stats *and* the list |
| `auto_escalate` | `true` | compatibility only; no widening — but the warning is source-specific, so it is part of the compared surface |
| `address` | **intentionally omitted** | `None` — no subject-property lookup |
| `enrich_epc` | `false` | explicit; avoids a network dependency |

An omitted parameter is recorded as `omitted` on the wire together with the
effective semantics it selects, never as a literal `null` query value.

`transaction_category="all"` is the REST spelling that disables category
filtering (`app/api/v1/ppd.py`, which maps `""` and `"all"` to `None`); a core
caller passes `transaction_category=None`. Core callers additionally inherit
`thin_market_threshold=5` and `coverage_policy=GUARANTEED`, which the REST
surface does not expose. **The corpus is specified at the REST surface.**

---

## 3. Universal invariants

`comps` never sends `to_date`. Routing therefore takes the clamp branch
unconditionally, `fully_contained` is always false, and the completeness basis
is discarded. On **every** snapshot-side case, whatever the artifact, date or
row count:

* the **coverage clamp** warning class is **present**;
* **`sample_complete` is `false`** — including where the returned page is
  plainly exhausted, far below `limit`. Exhausting a page is not completeness
  when the requested interval extends past what the snapshot holds;
* **`completeness_basis` is `null`**;
* **`recent_period_provisional` is `true`**. The resolved upper bound is always
  `coverage_to`, and `provisional_from` never exceeds `coverage_to`, so **every**
  comps window intersects the provisional period. This was originally written as
  a property of two particular cases; a rehearsal against a real artifact showed
  it holding on all fourteen, for the same structural reason as the clamp.

These are structural, not situational. A case reporting `sample_complete: true`
is a **defect**, not a divergence.

**`sample_complete` carries no comparative signal** and is asserted as an
invariant rather than compared between adapters: the live path reaches it
through transport-exhaustion evidence (§2.7.3), so agreement would be
coincidence rather than confirmation.

---

## 4. Case shapes

Parameters and intent only. Geographies written as placeholders are selected by
the Instance against the stated qualification rule; `B5`/`B50` are named here
because that boundary is a definitional choice rather than an artifact property,
though an Instance must still qualify them and may substitute with recorded
justification.

**On S1's rule.** "Comparable or greater volume" is qualitative, and it stays
qualitative: tooling checks it literally and, where an artifact falls below it,
**refers the judgement rather than deciding it**. A threshold weaker than the
words — an implementation quietly reading "comparable" as, say, a tenth — would
be a downward revision of a frozen qualification rule made inside code, and is
forbidden. The two ways to settle a below-threshold artifact are the ones this
section already gives: accept it for that artifact with the decision recorded,
or substitute with recorded justification. Substitution moves `B5`, `B50` and
`B5 4` **together**: S3 and S9 are a sector inside S1's district and S2 is its
neighbouring outcode, so moving one alone leaves the containment relation the
baselines establish silently false.

| # | Request shape | Intent | Instance qualifies by verifying |
|---|---|---|---|
| S1 | `postcode=B5`, `search_level=district` | contamination boundary | the longer neighbouring outcode holds comparable or greater volume |
| S2 | `postcode=B50`, `search_level=district` | reverse boundary | non-empty under frozen parameters |
| S3 | `postcode=B5 4`, `search_level=sector` | sector isolation | its **full aggregate count** is a strict subset of S1's — see §9 on why a paged result cannot show this |
| S4 | `postcode=<sector>`, `search_level=sector` | thin market | falls below `thin_market_threshold` under frozen parameters |
| S5 | `postcode=<sector>`, `search_level=sector` | dense market and truncation | matching rows greatly exceed `limit` |
| S6 | `postcode=<unit>`, `search_level=postcode` | exact-postcode geography | aggregate-dense, so not individually identifying |
| S7 | `postcode=<sector>`, `search_level=sector`, `property_type=F` | type filter that barely bites | at least 90% of the base is `F` |
| S8 | `postcode=<sector>`, `search_level=sector`, `property_type=F` | type filter that genuinely bites | a real spread across `F/D/S/T` |
| S9 | S3's geography, `transaction_category=all` | category filtering | its **full aggregate count** materially exceeds S3's on identical geography and window |
| S11 | `postcode=<sector>`, `search_level=sector`, `months=6` | **the provisional flag is a property of the window** | window intersects the provisional period; **returns zero rows** |
| S12 | `postcode=B5`, `search_level=district`, `months=120` | widest window, deepest history | matching rows greatly exceed `limit` |
| S13 | `postcode=<unit>`, `search_level=postcode`, `property_type=D` | expected empty | geography non-empty under defaults, that type absent |
| S14 | S3's geography, `property_type=T` | expected empty, sector shape | as S13 |

**S10 was removed.** It asserted "provisional tail, non-empty", which
discriminates nothing now that §3 records every comps case as provisional — it
was redundant with all thirteen others. **S11 is retained:** an empty result
that must still be flagged provisional is the control with teeth.

**S11 is the case a naive implementation gets wrong.** `recent_period_provisional`
is computed from the resolved *requested window* before any row is examined, so
an empty result whose window intersects the provisional period must still report
`true`.

**S12 makes no coverage-floor claim.** `months` is capped at 120 and its lower
bound moves *forward* over time, away from `coverage_from` — it does not descend
toward it. S12 probes depth and truncation. **No `comps` case can exercise the
coverage-floor narrowing path** (§9).

---

## 5. Warning classes — executable predicates

**Compare class presence and semantics. Never compare warning text.** Snapshot
and live warnings are deliberately worded differently by source, so comparing
strings would fail the corpus on a wording change and would encode prose as
contract.

Two classes are **structured fields** and need no string matching at all — the
field is the contract and the warning is its human rendering:

| Class | Predicate | Sources |
|---|---|---|
| provisional | `provenance.recent_period_provisional is True` | both |
| thin market | `response.thin_market is True` | both |

The remainder match a narrow substring, each quoted from the call site that
emits it:

| Class | Predicate — warning contains | Sources |
|---|---|---|
| coverage clamp | `beyond snapshot coverage` **and** `are not included` | snapshot |
| coverage-floor narrowing | `narrowed to` **and** `coverage` | snapshot |
| freshness | `days behind its coverage end` | snapshot |
| escalation containment | starts with `auto-escalation not applied:` | both |
| live incompleteness | `the upstream window was not exhausted` | live |
| geography containment | `removed by geography containment` | live |

**Escalation containment is the one class whose marker is shared and whose tail
is deliberately source-specific**, which is why it is matched prefix-anchored.

**Geography containment is a first-class signal for S1 and S2.** Its presence on
the live side means live received out-of-area rows and filtered them — evidence
about live's behaviour, not a snapshot divergence.

Divergence in **which classes appear** is a finding. Divergence in **how a class
is worded** is not, and must not be recorded as one.
`tests/snapshot/test_shadow_corpus_definition.py` pins every substring above
against its emitting module, so a reworded warning fails loudly here instead of
silently reclassifying observations.

---

## 6. Recording rules

`comps` accepts only `months`, and derives `from_date` internally as
`today − months × 30 days`. There is no public way to pass an absolute window,
and **no clock seam is proposed** — introducing one would be a new surface with
its own design and authorisation.

Recorded per observation, **computed by the harness**:

| Field | Source |
|---|---|
| `observed_at_before` / `observed_at_after` | the calendar date, captured immediately before and after each shadow pair |
| `derived_from_date` | computed by the harness as `observed_at − months × 30 days` |
| `resolved_to_date` | `provenance.coverage_to` — comps always clamps |
| artifact identity | `snapshot_version`, `bundle_sha256`, `coverage_from`, `coverage_to`, `provisional_from` |
| warning classes | per §5, per source |

**The resolved window is not in provenance.** That block carries `source`,
`source_release`, `snapshot_imported_at`, `coverage_from`, `coverage_to`,
`freshness_days`, `recent_period_provisional`, `older_records_exist`,
`sample_count`, `sample_limit`, `sample_complete`, `completeness_basis`,
`attribution_ref` and `warnings` — no resolved `from_date` or `to_date`. So
`derived_from_date` is a **reconstruction**, recorded as such: it mirrors the
service's arithmetic rather than observing it, and would diverge silently if
that arithmetic changed. The guard test pins it behaviourally.

**Warning prose must never be parsed as an API contract.** The warnings state
the clamp in English for humans; treating them as a machine-readable window
would couple the corpus to wording that is explicitly allowed to differ by
source.

### Midnight guard

`comps` derives its window internally from `date.today()`, so two sequential
adapter calls can straddle midnight and compare windows a day apart.

**If `observed_at_before != observed_at_after`, the observation is excluded from
corpus evidence and re-run.** Exclusions are counted and reported: a run
discarding many observations is a signal about the harness, not free of
consequence.

**Comparability holds within an observation** — one process, one instant, one
clock, so both adapters derive the same window. It does **not** hold across
observations on different days, and counts are read against each observation's
own recorded window.

---

## 7. Divergence taxonomy — these four only

1. **Provisional-tail lag** — the window intersects the provisional period and
   live has received rows the build predates.
2. **Later A/C/D revision** — rows revised by monthly change records after the
   build's source release.
3. **Live truncation or ordering** — live returned fewer or differently ordered
   rows through its own `fetch_limit`, timeout or ordering behaviour. **This
   class must be evidenced** (`raw_bindings_returned`, `fetch_limit`), never
   assumed because the snapshot returned more.
4. **Unclassified — blocking.** Never downgraded to "acceptable variance".

**Geography contamination is not a class.** A B50 row in a B5 result is a defect
in whichever source produced it.

---

## 8. Stage 1 exit criteria

Carried forward from rev 7 §7.2, unchanged by rev 8, and changed by **rev 10 in
exactly one criterion — p95 — before Stage 1 started**. All must hold. **No
percentage threshold.**

* **Zero unexplained false empties** — no case where the snapshot returns empty
  and live returns rows within coverage without a classified explanation.
* **Zero geography contamination** — no B50-in-B5 class error, no sector or
  outcode bleed, in the entire corpus.
* **100% field equality on shared transaction IDs.**
* **Every divergence classified** into §7's classes; an unclassified divergence
  blocks exit.
* **Zero snapshot errors** in the agreed corpus — no unhandled exception, no
  typed error where the request was in-coverage and well-formed.
* **p95 < 1 second on the deployed production Machine and selected artifact,
  measured across the frozen corpus request mix** (rev 10). The governing
  §7.2 carries the reasoning; in short, organic `comps` traffic here is sparse
  and uncontrolled, so a percentile over it measures the callers rather than the
  adapter, while this corpus is risk-shaped, repeatable and attributable.
  **The request mix is chosen, not observed** — a corpus run is never to be
  described as organic traffic.

  Latency recorded by any run that is **not** on the deployed Machine and the
  selected artifact — a local rehearsal above all — is `controlled_synthetic`
  and is excluded from this percentile. The two are separate fields in a report
  and no code path merges them.

---

## 9. Local rehearsal protocol

Validates that each case is well-formed, routes as intended and produces the
expected shape — before any production shadow.

1. Point `PPD_SNAPSHOT_DIR` at the Instance's artifact; materialize into a
   scratch `PPD_SNAPSHOT_CACHE_DIR`. `LocalDirectorySource`, no network.
2. Run each case **through the snapshot adapter only**, passing every frozen
   parameter of §2 explicitly. The live adapter is not constructed, patched or
   called.
3. Record everything in §6, plus row count, returned geography membership
   (sector and outcode only), the **date bounds of returned rows**, the
   provenance block, warning classes, and **per-case latency**. Record any
   **midnight exclusion and retry**; an observation that cannot be obtained
   within a single calendar date **fails the run** rather than being recorded
   against a window that does not describe it. **The failure is written to
   the report before the run exits** — an aggregate-only report carrying
   `midnight.unrecoverable`, the retry count and the reason. A traceback
   with no report is not "clearly", and leaves nothing to review.
4. Assert §3's invariants on every case, plus each shape's intent: S1 contains
   no row from the neighbouring outcode; S4 trips the thin-market threshold;
   S5 and S12 return exactly `limit` rows; **S11 reports
   `recent_period_provisional: true` while returning zero rows**; S13 and S14
   are empty.

   **Containment between cases is asserted on counts, not on pages.** A paged
   result ordered most-recent-first is not a subset of a wider page: S1's fifty
   most recent rows across a district need not contain S3's fifty most recent
   within one of its sectors, and S9's page with category B included pushes
   category-A rows off the equivalent S3 page. Set containment over
   transaction ids is therefore **only meaningful when neither side is
   saturated**. Accordingly:

   * **Instance qualification uses full aggregate counts** — that is where
     "S3 is a strict subset of S1" and "S9 exceeds S3" are established, against
     the whole artifact rather than a page.
   * **The rehearsal reports `not_evaluable`, with its reason, whenever either
     paged result is saturated at `limit`.** A saturated comparison is an
     unanswerable question, and reporting it as a failure would blame the
     artifact for the corpus asking it.
   * **Geography containment is always checked**, because it remains meaningful
     on a page: every row S3 returns must lie inside S1's outcode however the
     page was truncated.

   **`not_evaluable` is never counted as a passing assertion.** It is recorded
   explicitly with its reason, counted separately from passes and failures, and
   a run may still exit 0 with `not_evaluable` assertions present — but it may
   never exit 0 with a failed one.

   **The declared baselines are carried in the rehearsal instance**, as
   `aggregate_baselines` (`S1_full`, `S3_full`, `S9_full`), validated before
   anything is materialized: they must be counts, `S3_full` may not exceed
   `S1_full`, and `S9_full` must exceed `S3_full`. A baseline set contradicting
   the relation it exists to establish is refused — it would look like evidence
   while qualifying nothing. The report records them as **declared, not
   measured**: a paged rehearsal cannot re-derive a full aggregate count and
   must not imply it did.
5. Sockets hard-failed throughout, with a self-check proving the block is
   armed, so an accidental network call fails the run rather than making it
   non-deterministic.
6. **Pre-existing `PPD_SNAPSHOT_*` environment values and installed snapshot
   state are captured and restored**, not deleted. A rehearsal is a guest in
   whatever process runs it: unsetting a variable the caller had set, or
   dropping an adapter the caller had installed, would leave that process
   quietly different afterwards.

**A rehearsal is neither a production-Machine measurement nor a comparison.** It
runs on a workstation against a local artifact, so it satisfies no p95 criterion,
and it has no live arm, so it satisfies no divergence criterion.
Its output is labelled a rehearsal result and is **never filed as Stage 1
evidence**.

---

## 10. Instance schema

An Instance records: the selected `snapshot_version` and `bundle_sha256`; its
qualification date; per case, the aggregate baseline and the qualification rule
it satisfied — including the **full aggregate counts** establishing S3's
containment in S1 and S9's excess over S3, which a paged rehearsal cannot show; any substituted geography with justification; its staleness bound;
and the Stage 1 run it governs.

---

## 11. Known limits

* **`older_records_exist` cannot be validated against a coverage-bounded
  artifact** — it asserts something about rows before `coverage_from`.
  Confirming it needs the bounded existence probe (§2.4) or a full-history
  artifact.
* **Postcode validity is not established by the snapshot.** A zero-row postcode
  cannot be distinguished from an invalid one without an external source, so
  S13 and S14 use geographies with confirmed activity and an empty *filter*.
* **Rows with no geography** — a small share of PPD rows carry no postcode, and
  so can never be returned by a geography-filtered query while still counting
  toward snapshot totals. **Decided before Stage 1 began:** a row *returned* by
  a geography-filtered query while carrying no usable postcode is a
  **containment failure**, on whichever arm produced it, and blocks exit. This
  is about what a query returns, not about rows sitting un-returnable in the
  artifact — the limit above is unchanged.

  Leaving it open in the implementation would have settled it in the weakest
  direction: skipping such rows means a source could return arbitrary rows with
  the postcode blanked and every containment check would still pass. Only the
  count reaches a report (`rows_without_postcode`); the row is by definition the
  one whose geography cannot be stated, so there is nothing else safe to record.
* **All shape expectations are snapshot-side.** Live counts are unknown by
  construction; establishing them would require live queries, which are
  separately authorised.
* **The coverage-floor narrowing path is unexercised by design** (§4). It
  belongs to `/transactions` and its routing tests.
