# property-shared stall, 2026-08-30

**Status: OPEN.** It closes when the hotfix is deployed and client
responsiveness is verified against the running service — not when the fix
merges. The regression tests, PR #34 and this note are the durable record.

Timestamped observations from the read-only diagnosis. Every figure here was
read from the running system at the stated UTC time. This records evidence, not
gate completion.

## Symptom

From 22:00Z, `property-shared.fly.dev` stopped answering. TLS completed at Fly's
edge in ~54 ms — the edge terminates TLS, so that proved only edge reachability
— then no HTTP response arrived. `propertydata` and an independent control both
returned 200 throughout.

## Cause

`PPDService.comps` is synchronous, and both `GET /v1/ppd/comps`
(`app/api/v1/ppd.py`) and the MCP `property_comps` tool (`app/mcp/server.py`)
called it directly from inside `async def`. The single uvicorn worker's event
loop was therefore parked in a blocking socket read for the whole upstream
SPARQL round trip, unable to run any other task — including `/v1/health`, a
constant-returning coroutine that performs no I/O.

Fly's health check allows 5 s. Live PPD queries observed during v1.15.0
release testing took 60–120 s. The check timed out, the Machine was dropped
from the proxy's candidate set, and requests then failed upstream with
`could not find a good candidate within 40 attempts at load balancing`.

`app/api/v1/rightmove.py` already offloaded its synchronous calls with
`anyio.to_thread.run_sync`; the PPD router never did.

## Evidence, with timestamps

| UTC | Observation |
|---|---|
| 22:00:09 | Edge `/v1/health`: TLS 0.054 s, **ttfb 0.000**, timeout at 25 s. `propertydata` 200 in 0.076 s |
| 22:00:41 | Machine `started`, check `passing`, `{"status":"ok"}`, updated 20 s prior |
| 22:00:44–22:00:57 | Proxy `could not find a good candidate` from `iad`, `fra` |
| 22:01:05 | `Health check 'servicecheck-00-http-8080' has failed` |
| 22:02:10 | Check `is now passing` — flapping, not a hard failure |
| 22:02:12 | Four `CallToolRequest` in flight, then 34 s of no application output |
| 22:02:46 | Check fails again |
| 22:05:38 | Check `passing` 38 s prior, while only 4 requests arrived in 80 s |
| 22:08:58–22:13:58 | **45** proxy `no candidate` errors in one 5-minute window |
| 22:10:44–22:11:40 | **8/8** probes to `127.0.0.1:8080/v1/health` **from inside the Machine** timed out at 6 s |
| ~22:10 | `loadavg 0.00 0.00 0.00`; `MemFree` 1.74 GB of 2 GB; uptime 8885 s, idle 8802 s |
| ~22:10 | `uvicorn` PID 635, **2 threads**, `state=S`; tid 635 `do_poll`, tid 785 `futex_wait_queue` |
| ~22:10 | Listening socket `0.0.0.0:8080` accept queue **12**, draining to 1 by 22:12 |
| 22:13:45 | App served `GET /v1/health 200` and `GET /metrics 200` — intermittent, not wedged |

Zero CPU while serving nothing is the signature of a blocked event loop, not of
saturation. No OOM, no restart, no exit: the process ran from boot throughout.

## Worker count — evidence for property-shared only

`Dockerfile` runs `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0",
"--port", "8080"]` with no `--workers`, so **`property-shared` ran a single
uvicorn worker on one shared vCPU** at 2026-08-30T22:10Z, on image
`deployment-01M1A31WVKD5S0QQ9XJ2CDG0NC`.

**This is not G2.** It is one observation of one app at one time, read from the
checked-in Dockerfile and the running Machine. G2 asks for the worker count to
be verified as a rollout precondition across the targets it governs; nothing
here establishes that for `propertydata`, and nothing here pins a count against
future change. G2 remains open.

## Fly configuration, unchanged by v1.15.0

`property-shared` sets `[http_service.concurrency] type="requests",
hard_limit=10, soft_limit=5`; `propertydata` sets no concurrency block. Both
values predate this work — `hard_limit = 10` dates from `ff21f31`, 2026-01-21 —
and `git diff v1.14.2 v1.15.0` over both Dockerfiles and both fly configs is
empty. **No Fly limit, worker count or Machine count was changed**, so the
hotfix can be assessed against an unchanged baseline. Whether the concurrency
limit is right is a separate question, to be reassessed once the loop no longer
blocks; it is backpressure and should not be removed blindly.

## Rightmove — claim narrowed after an input control

An earlier note in this diagnosis claimed Rightmove's location lookup was
"broken globally". **That was wrong**, and the control that disproves it:

| Input | Result |
|---|---|
| `SW1A 1AA` (full postcode) | `POSTCODE^837246`, 0.1 s |
| `B5 4BX` (full postcode) | `POSTCODE^4991456`, 0.1 s |
| `B5 7` (sector) | `None` |

`lookup_postcode` resolves full postcodes correctly. The original observation
used a **sector**, which it is not designed to resolve. The production failures
seen at 22:00:32Z were `LocationLookupError` for `'BB12 1AA'` — consistent with
an unresolvable input rather than an outage.

## Sibling endpoints — checked, not defective

A first pass listed seven further call sites as "the identical defect" purely
because they call synchronous code. **That was wrong.** A synchronous call is
not the defect; a synchronous call from an `async def` handler is, because only
then does it occupy the loop thread.

`comps` was the **only** `async def` in the PPD router. `download_url`,
`transactions`, `address_search`, `transaction_record` and `blocks` are plain
`def`, which Starlette runs in its threadpool. The MCP sites — `ppd_transactions`
in `app/mcp/server.py`, `analyse_blocks` and `search_ppd_transactions` in
`property_app/tools.py` — are plain `def` tools, which FastMCP offloads the same
way.

Verified rather than reasoned: `tests/test_event_loop_not_blocked_by_comps.py`
drives a slow stub through the real `/v1/ppd/transactions` route and through
FastMCP's own tool dispatcher, asserting both that the stub actually ran for its
full duration and that the loop stayed responsive throughout. Those tests would
fail if a sibling were ever converted to `async def` without an offload.

## Rightmove, continued

What remains open, and is *not* claimed as a defect here: whether
`rightmove_search` should reject a non-full-postcode input with a typed caller
error instead of raising and rendering a large traceback per call. That needs
its own valid-input controls before anything is asserted about it.


## Recovery, 2026-08-31

### The release workflow deployed only one of the two apps

`v1.15.1` was tagged on `54ac5c7` and the GitHub Release published, triggering
`release.yml` (run `33345291490`). Results:

| Job | Outcome |
|---|---|
| Publish to PyPI | success — 1.15.1 live |
| Deploy propertydata to Fly | success — reported 1.15.1 |
| Deploy property-shared to Fly | **failure**, twice |

Both attempts (00:41Z, and a re-run at 00:52Z) failed identically, before any
build began:

```
Waiting for depot builder...
error releasing builder: deadline_exceeded: context deadline exceeded   (x2, 5 min each)
Error: failed to fetch an image or build from source: error building:
  timed out connecting to machine: failed to list workers:
  Unavailable: ... authentication handshake failed: EOF
```

Fly's status page reported all systems operational with no unresolved
incidents, `propertydata` obtained a builder on the same run, and the same
token had built this app successfully five hours earlier for v1.15.0. Treated
as transient Depot builder unavailability, not a repository or config fault.

**This left the two apps on different versions**, with the app that needed the
fix still running the stalling v1.15.0 and timing out externally at 01:03Z. The
workflow's deploy steps have no retry, and nothing reconciles a partial
release.

### Manual recovery

One authorised emergency deployment of `property-shared` only, bypassing Depot,
from a clean checkout pinned to the release commit:

```
fly deploy --app property-shared --config fly.toml \
  --remote-only --depot=false --ha=false
```

Preconditions confirmed from that checkout before running: `HEAD` =
`54ac5c7a1a8709f0a4e8119c7d6fe48a0a09182a` = tag `v1.15.1`
(`git describe --tags --exact-match` → `v1.15.1`), working tree clean and
identical to `origin/main`, versions 1.15.1 in `pyproject.toml` and both
`server.json` fields, `fly.toml` concurrency and health checks unchanged,
`Dockerfile` unchanged, and no `.env*` in the build context.

| Field | Value |
|---|---|
| Started | 2026-08-31T01:43:57Z |
| Image | `property-shared:deployment-01M1AQTD8KN05PRA2330DX68GA` |
| Digest | `sha256:2087c8970fa38a36e0687a4c7995d5d28d7ba627a72a06f5443e8f8e0c980252` |
| Image size | 480 MB |
| Machine | `7849207a412608`, version 130 → **131**, rolling update |
| Health checks | enabled throughout; smoke and machine checks passed |

Machine count, worker count, concurrency limits, secrets, Dockerfile and
snapshot flags were not touched. `propertydata` was not redeployed and PyPI was
not republished.

### Post-deployment verification

| Check | Result |
|---|---|
| Reported version | `{"serverInfo":{"name":"property-data","version":"1.15.1"}}` |
| Machine check | `passing`, `{"status":"ok"}` |
| External health | 5/5 at 200; ttfb 0.110 s then 0.046–0.051 s — no cold-start penalty |
| MCP initialize + `tools/list` | `property-data v1.15.1`, **14 tools**, 0.22 s; repeated after the comps call, 0.18 s |
| **Responsiveness during a slow comps call** | **NOT ESTABLISHED — see below** |

### Why the decisive check is still outstanding

The one bounded comps request returned **502 in 0.1 s**:

```
{"detail":"PPD comps failed: HTTP Error 429: Too Many Requests"}
```

Land Registry is rate-limiting this app. A request that fails in 0.1 s never
occupies the loop, so it cannot demonstrate the property the hotfix exists to
provide. Health stayed at 0.049 s throughout, but against a fast failure that
observation is worth nothing.

**A healthy server shortly after a restart does not establish that the stall is
fixed.** The event-loop fix is proven locally by
`tests/test_event_loop_not_blocked_by_comps.py`, which reproduces the stall
with a slow stub and shows it gone; it is not yet proven against the deployed
service under a genuinely slow upstream call. Deliberately not retried in a
loop — repeated slow-query load is what provoked the throttling.

**The incident stays OPEN** pending that check and the maintainer's Claude and
ChatGPT client testing.

### Also observed

Upstream `429` responses mean PPD surfaces are currently returning 502 to real
clients. That is an upstream throttle, not a regression from this release, but
it will affect client testing until it clears. `rightmove_search` continues to
raise `LocationLookupError` for inputs that are not resolvable full postcodes —
the narrowed finding above, unchanged.
