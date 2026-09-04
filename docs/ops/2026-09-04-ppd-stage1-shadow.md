# Stage 1 shadow comparison, attempt 2026-09-04 — aborted at S1 on an upstream 503

**This is not Stage 1 evidence.** The frozen corpus is thirteen cases with two
arms each; a report covering one case with one arm is not a smaller Stage 1
result. Stage 1 remains **not started**, and snapshot serving remains off.

What this run *did* produce is the first hard data on why the live arm keeps
failing — which is what v1.18.2's live-arm diagnostics were built for, and what
the 2026-09-02 attempt could not supply.

## Conditions

| Field | Value |
|---|---|
| Machine | `7849207a412608`, `lhr`, version 141 |
| Release | v1.18.2 |
| Artifact | `v20260828T194003Z`, `bundle_sha256 50f802b2…` |
| Instance | `docs/ops/evidence/2026-09-02-stage1-instance-v1.18.1.json`, `qualified_at 2026-09-02`, 2 days old against a 45-day bound, sha256 verified byte-identical after upload |
| Command | `compare --latency-repeats 30 --max-live-per-case 1 --live-delay-seconds 2.0 --deadline-seconds 3600` |
| Flag | `PPD_SHADOW_COMPARE_ENABLED=1`, inline for the one invocation, never a Fly secret |
| Window | 09:45:33Z – 09:51:02Z |

`--live-delay-seconds` was deliberately left at the 2026-09-02 value. Changing
it without data would have confounded the one measurement worth having.

Isolation, as recorded by the run itself:

```json
{"installed_into_server_state": false, "snapshot_routing_enabled": false,
 "artifacts_downloaded": 0, "snapshot_written_to": false}
```

## Outcome

```
aborted: "S1: the live arm failed (HTTPError: HTTP Error 503: Service
          Temporarily Unavailable); completeness is already lost, so no
          later case runs"
cases_recorded: 1   cases_compared: 0   live_calls_made: 1
cases_never_reached: S2-S9, S11-S14
```

## The finding: a slow 503, not a fast 429

```json
"live_timing": {
  "started_at":  "2026-09-04T09:45:37.817+00:00",
  "finished_at": "2026-09-04T09:50:09.599+00:00",
  "elapsed_ms":  271785.89,
  "outcome":     "error"
},
"status": 503, "reason": "Service Temporarily Unavailable", "headers": {}
```

Three things follow, and they matter more than the abort itself.

**1. The failure took 4 minutes 32 seconds.** Rate limiting is normally refused
immediately; the 2026-09-02 failure was a 429. A 503 arriving after 271.8 s of
waiting is the signature of an upstream that could not complete the work, not of
one declining to accept it. **This reopens the question of what has been
happening**: the "throttle" framing came from a single 429 and was never
established.

**2. No rate-limit headers were sent at all.** `headers: {}` is the *allow-list
result*, not an omission by the comparator — v1.18.2 captures `Retry-After`,
`RateLimit-*` and `X-RateLimit-*`, and HMLR sent none of them. So the diagnostic
worked and returned an honest negative: **there is still no published or
observed quota to pace against.** No `Retry-After` also means nothing tells us
when a retry becomes reasonable.

**3. Live latency is degrading across observations.**

| When | Request | Result |
|---|---|---|
| 2026-09-02 | Stage 1 live arm | ~58 s per call; 429 on the third |
| 2026-09-04 09:12 | `/v1/ppd/comps` `B5 4BX` | **200 in 172.95 s** |
| 2026-09-04 09:46 | Stage 1 live arm S1 | **503 after 271.79 s** |

Three points is a trend line, not a diagnosis. Candidate readings that this
evidence does **not** separate: upstream overload or degradation; a throttle
expressed as latency then 503; scheduled load on HMLR's side; or something
keyed to us that we still cannot see. The throttle key remains unknown, and it
is now unclear whether "throttle" is even the right word.

## The one comparison that did happen

The snapshot arm completed before the live arm failed:

```json
{"count": 50, "latency_ms": 314.61, "source": "snapshot",
 "outcodes_returned": ["B5"], "sectors_returned": ["B5 4","B5 5","B5 6","B5 7"],
 "saturated_at_limit": true, "sample_complete": false,
 "warning_classes": ["coverage_clamp", "freshness"]}
```

**314.61 ms against a live arm that spent 271,785 ms and then failed.** Both
figures are one observation each and neither is a p95, so this is not the
latency gate and must not be quoted as one. It is, however, the first
side-by-side on identical input, and the direction is not subtle.

Geography containment held on the arm that ran: every returned row sat inside
`B5`, across sectors `B5 4`–`B5 7`. The coverage clamp and freshness warnings
are expected for a window reaching past `coverage_to 2026-06-30`.

## Client timeout discrepancy — open, not explained

`PricePaidDataClient` declares `timeout: float = 120` (`property_core/ppd_client.py:155`),
yet this call ran 271.8 s before erroring. Two readings, neither confirmed here:
the timeout applies per socket operation rather than to the whole request, or
something retried beneath it. Worth settling on its own, because a 120 s
declared bound that permits a 272 s call misstates the worst case for anyone
sizing timeouts or health-check budgets against it.

This does **not** reopen the 2026-08-30 stall incident. That closure rests on
the event loop staying free during a 172.95 s call — 345 health beats at a
2.3 ms mean — and a longer blocking call does not weaken it. It does mean the
blocking window can be longer than the declared timeout implies.

## Stop condition honoured

The plan for this attempt set the stop condition in advance: an abort at S1
means stop, record, and do not retry until a deliberate cool-off. That is what
happened, and no second attempt was made. A re-run would spend more upstream
capacity while adding nothing until the above is understood.

## What is still true, unchanged by this run

- `PPD_SNAPSHOT_ENABLED` is absent from both apps. Snapshot serving is off, and
  nothing here is authority to enable it.
- G1a, G2 and G3 remain complete; **Stage 1 remains not started**.
- The frozen corpus is unchanged and the Instance is unchanged and still within
  its staleness bound until roughly 2026-10-17.

## Next, in order

1. **Establish what the upstream is actually doing** before any further attempt.
   A 503 after 272 s and a 429 after two calls are different failures and may
   have different causes. Nothing retained so far distinguishes them.
2. **Settle the timeout discrepancy** — cheap, local, and it changes how any
   future attempt should be bounded.
3. Only then choose a pacing strategy. `--live-delay-seconds` cannot be tuned
   against evidence that does not exist, and on this run the gap between calls
   never came into play: the run died on the first one.
