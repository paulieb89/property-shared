# property-shared stall, 2026-08-30

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

What remains open, and is *not* claimed as a defect here: whether
`rightmove_search` should reject a non-full-postcode input with a typed caller
error instead of raising and rendering a large traceback per call. That needs
its own valid-input controls before anything is asserted about it.
