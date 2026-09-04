# Fly observability snapshot — `property-shared`

- **App**: `property-shared` (org `personal`)
- **Window**: `30m`
- **Collected**: 2026-09-02T00:01:16Z → 2026-09-02T00:01:27Z (UTC)
- **Schema**: `2`

`no_data` means the series has no samples — it is **not** a reading of zero. `error` means collection failed and nothing was measured.

## Readings

| Metric | Unit | Value | Status |
|---|---|---|---|
| Instance up | bool | 1 | `ok` |
| Machine identity | info | 1 | `ok` |
| Instance uptime | seconds | 5.501e+04 | `ok` |
| Metrics scrape up | bool | 1 | `ok` |
| App concurrency | connections | — | `no_data` |
| Load average (5m) | load | 0.01 | `ok` |
| Load average (5m) peak over window *(derived)* | load | 0.02 | `ok` |
| CPU busy *(derived)* | percent | 0.4234 | `ok` |
| CPU throttle | count | 0 | `ok` |
| Machine memory total | bytes | 2,064,257,024 (1.92 GiB) | `ok` |
| Machine memory available | bytes | 1,692,741,632 (1.58 GiB) | `ok` |
| Machine memory available, minimum over window *(derived)* | bytes | 1,692,741,632 (1.58 GiB) | `ok` |
| OOM exits | count | — | `no_data` |
| Root filesystem free *(derived)* | bytes | 8,038,342,656 (7.49 GiB) | `ok` |
| Root filesystem free, minimum over window *(derived)* | bytes | 8,038,342,656 (7.49 GiB) | `ok` |
| Root filesystem total *(derived)* | bytes | 8,350,298,112 (7.78 GiB) | `ok` |
| Network received *(derived)* | bytes/sec | 341.1 | `ok` |
| Network sent *(derived)* | bytes/sec | 4,237 | `ok` |
| App HTTP responses by status *(derived)* | responses | 5 series | `ok` |
| Edge HTTP responses by status *(derived)* | responses | 5 series | `ok` |
| App HTTP p95 latency *(derived)* | seconds | 0.02175 | `ok` |
| App HTTP p99 latency *(derived)* | seconds | 0.02435 | `ok` |
| Edge HTTP p95 latency *(derived)* | seconds | 0.1239 | `ok` |
| Concurrency hard limit reached *(derived)* | events | 0 | `ok` |
| Concurrency soft limit reached *(derived)* | events | 0 | `ok` |
| Process RSS | bytes | 198,901,760 (0.19 GiB) | `ok` |
| Process RSS peak over window *(derived)* | bytes | 198,901,760 (0.19 GiB) | `ok` |
| Open file descriptors | count | 10 | `ok` |
| App requests by surface/route/status class *(derived)* | requests | 8 series | `ok` |
| App-measured request p95 latency *(derived)* | seconds | 0.008212 | `ok` |
| MCP tool calls by tool and status *(derived)* | calls | 10 series | `ok` |
| MCP client handshakes by client *(derived)* | handshakes | 38 series | `ok` |
| Machine memory available over time | bytes | 1 series | `ok` |
| Root filesystem free over time *(derived)* | bytes | 1 series | `ok` |
| Process RSS over time | bytes | 1 series | `ok` |

## Breakdowns

**Machine identity**
  - app=property-shared, cpu_count=1, cpu_kind=shared, host=81e9, instance=7849207a412608, memory_mb=2048, process_group=app, region=lhr: 1

**App HTTP responses by status**
  - status=200: 88
  - status=202: 31
  - status=400: 1
  - status=404: 15
  - status=405: 4

**Edge HTTP responses by status**
  - status=200: 57
  - status=202: 22
  - status=400: 3
  - status=404: 16
  - status=405: 3

**App requests by surface/route/status class**
  - route=/.well-known/glama.json, status_class=2xx, surface=web: 0
  - route=/mcp, status_class=2xx, surface=mcp_proxy: 119
  - route=/mcp, status_class=4xx, surface=mcp_proxy: 12
  - route=/v1/health, status_class=2xx, surface=infra: 60
  - route=/v1/meta, status_class=2xx, surface=api: 0
  - route=/v1/meta/integrations, status_class=2xx, surface=api: 0
  - route=/web, status_class=2xx, surface=web: 0
  - route=/web, status_class=4xx, surface=web: 12

**MCP tool calls by tool and status**
  - status=error, tool=epc_certificate: 0
  - status=error, tool=ppd_transactions: 0
  - status=error, tool=rental_analysis: 0
  - status=error, tool=rightmove_search: 0
  - status=ok, tool=epc_certificate: 0
  - status=ok, tool=ppd_transactions: 0
  - status=ok, tool=property_comps: 0
  - status=ok, tool=property_epc_summaries: 0
  - status=ok, tool=rightmove_search: 0
  - status=ok, tool=stamp_duty: 0

**MCP client handshakes by client**
  - client_name=AgentIndexBot: 0
  - client_name=Anthropic/ClaudeAI: 1
  - client_name=Kelivo MCP: 0
  - client_name=acton-probe: 0
  - client_name=acton-skill-extractor: 0
  - client_name=agent-tools.cloud: 1
  - client_name=agent-world-probe: 0
  - client_name=agentage-mcp-catalog-health: 1
  - client_name=aisec-registry-probe: 0
  - client_name=avp1-scan: 0
  - client_name=chathome-skills-probe: 0
  - client_name=claude-ai (via mcp-remote 0.8.3): 0
  - client_name=claude-code: 2
  - client_name=codex-mcp-client: 3
  - client_name=factanker-probe: 0
  - client_name=forge-registry-probe: 0
  - client_name=glama: 1
  - client_name=glimind-probe: 4
  - client_name=golemreach-trust: 0
  - client_name=hultra-link: 0
  - client_name=ledgerhall: 18
  - client_name=local-agent-mode-property (via mcp-remote 0.8.3): 0
  - client_name=mcp: 0
  - client_name=mcp-checker: 0
  - client_name=mcp-ledger-probe: 0
  - client_name=mcp-remote-fallback-test: 0
  - client_name=mcp-rugpull-research: 0
  - client_name=mcp2-research: 0
  - client_name=mcpbeat: 1
  - client_name=mcphq-probe: 0
  - client_name=mcpindex-trust: 0
  - client_name=mcpscan: 0
  - client_name=policylayer-crawler: 0
  - client_name=probe: 0
  - client_name=proofbench-probe: 0
  - client_name=sheet-add-in: 0
  - client_name=test: 0
  - client_name=unreached-probe: 0

## Transient disk (corroborating, not authoritative)

| Mount | Instance | Baseline free | Minimum free | Delta | Status |
|---|---|---|---|---|---|
| /.fly-upper-layer | 7849207a412608 | 8,038,342,656 (7.49 GiB) | 8,038,342,656 (7.49 GiB) | 0 | `ok` |

- Method: delta_bytes = baseline_free - minimum_free, on one mount. Not total_bytes - minimum_free, which measures total occupancy.
- Resolution: Fly stores one sample per 15s. A materialisation lasting ~20 s produces one or two samples, so this delta may understate the true peak or miss it entirely.
- Authoritative source: /app/boot_only_verify.py, which samples the verifier directory every 0.2 s, is the authoritative transient-disk measurement; this delta only corroborates it.

## Not measured

| Metric | Status | Detail |
|---|---|---|
| App concurrency | `no_data` | query matched no series. Verified absent for property-shared and propertydata on 2026-09-01 while present for five other fleet apps. Expect no_data, and do not read it as zero. |
| OOM exits | `no_data` | query matched no series. Absent unless an OOM kill has occurred; no_data here is the healthy reading. |

## Commands

- `fly status --json -a property-shared` → `ok`
- `fly checks list --json -a property-shared` → `ok`
- `fly image show --json -a property-shared` → `ok`

## Notes

- No Grafana dashboard titled 'BOUCH MCP Fleet' is checked in anywhere under the mcpfleet workspace; the only checked-in dashboard is monitoring/grafana-dashboard.json ('Property Shared API'), whose PromQL targets metric names that do not exist in Fly's Prometheus (http_request_duration_seconds_*, http_requests_inprogress, http_response_size_bytes_*, external_request_duration_seconds_*). That dashboard is written for a prometheus_fastapi_instrumentator naming scheme the deployed app does not use. No series here is sourced from it. The app_custom series below are taken from the live Fly label index and from the checked-in definitions in app/core/metrics.py, not from any dashboard.
- Transient disk from this collector is corroborating evidence, never the measurement. The additional space a run consumed on a mount is baseline_free - minimum_free on that same mount; total_bytes - minimum_free would instead report total disk in use at the low-water mark, including the image and everything already present. Fly stores samples every 15s, so a ~20 s materialisation yields one or two samples and its true peak can fall entirely between them. /app/boot_only_verify.py samples the verifier directory every 0.2 s and is the authoritative transient-disk measurement.
- no_data (absent series, NOT zero): app_concurrency, instance_exit_oom

## PromQL used

- **Instance up** (`fly_builtin`)
  ```
  fly_instance_up{app="property-shared"}
  ```
- **Machine identity** (`fly_builtin`)
  ```
  fly_instance_info{app="property-shared"}
  ```
- **Instance uptime** (`fly_builtin`)
  ```
  fly_instance_uptime_seconds{app="property-shared"}
  ```
- **Metrics scrape up** (`fly_builtin`)
  ```
  up{app="property-shared"}
  ```
- **App concurrency** (`fly_builtin`)
  ```
  fly_app_concurrency{app="property-shared"}
  ```
- **Load average (5m)** (`fly_builtin`)
  ```
  fly_instance_load_average{app="property-shared",minutes="5"}
  ```
- **Load average (5m) peak over window** (`fly_builtin`, derived)
  ```
  max_over_time(fly_instance_load_average{app="property-shared",minutes="5"}[30m])
  ```
  Derivation: max_over_time over the collection window of the kernel 5-minute load average.
- **CPU busy** (`fly_builtin`, derived)
  ```
  100 * (1 - sum(rate(fly_instance_cpu{app="property-shared",mode="idle"}[30m])) / sum(rate(fly_instance_cpu{app="property-shared"}[30m])))
  ```
  Derivation: 100 * (1 - idle_rate / total_rate) across all cpu modes and cpu_ids over the window.
- **CPU throttle** (`fly_builtin`)
  ```
  fly_instance_cpu_throttle{app="property-shared"}
  ```
- **Machine memory total** (`fly_builtin`)
  ```
  fly_instance_memory_mem_total{app="property-shared"}
  ```
- **Machine memory available** (`fly_builtin`)
  ```
  fly_instance_memory_mem_available{app="property-shared"}
  ```
- **Machine memory available, minimum over window** (`fly_builtin`, derived)
  ```
  min_over_time(fly_instance_memory_mem_available{app="property-shared"}[30m])
  ```
  Derivation: min_over_time of MemAvailable over the window — the Machine-wide low-water mark.
- **OOM exits** (`fly_builtin`)
  ```
  fly_instance_exit_oom{app="property-shared"}
  ```
- **Root filesystem free** (`fly_builtin`, derived)
  ```
  fly_instance_filesystem_blocks_free{app="property-shared"} * fly_instance_filesystem_block_size{app="property-shared"}
  ```
  Derivation: blocks_free * block_size, per mount. Mount label identifies the filesystem.
- **Root filesystem free, minimum over window** (`fly_builtin`, derived)
  ```
  min_over_time((fly_instance_filesystem_blocks_free{app="property-shared"} * fly_instance_filesystem_block_size{app="property-shared"})[30m:15s])
  ```
  Derivation: min_over_time of (blocks_free * block_size) on the same mount, sampled at 15s (Fly's real stored resolution) over the window. This is the free-space low-water mark, nothing more. The additional space a run consumed is baseline_free - minimum_free on that mount — see summarise_transient_disk(). It is NOT total_bytes - minimum_free, which is total disk in use including the image and everything already present.
- **Root filesystem total** (`fly_builtin`, derived)
  ```
  fly_instance_filesystem_blocks{app="property-shared"} * fly_instance_filesystem_block_size{app="property-shared"}
  ```
  Derivation: blocks * block_size, per mount.
- **Network received** (`fly_builtin`, derived)
  ```
  sum(rate(fly_instance_net_recv_bytes{app="property-shared",device="eth0"}[30m]))
  ```
  Derivation: rate() of the eth0 counter over the window, summed.
- **Network sent** (`fly_builtin`, derived)
  ```
  sum(rate(fly_instance_net_sent_bytes{app="property-shared",device="eth0"}[30m]))
  ```
  Derivation: rate() of the eth0 counter over the window, summed.
- **App HTTP responses by status** (`fly_builtin`, derived)
  ```
  sum by (status) (increase(fly_app_http_responses_count{app="property-shared"}[30m]))
  ```
  Derivation: increase() of the Fly proxy app-side response counter over the window, by status.
- **Edge HTTP responses by status** (`fly_builtin`, derived)
  ```
  sum by (status) (increase(fly_edge_http_responses_count{app="property-shared"}[30m]))
  ```
  Derivation: increase() of the Fly edge response counter over the window, by status.
- **App HTTP p95 latency** (`fly_builtin`, derived)
  ```
  histogram_quantile(0.95, sum by (le) (rate(fly_app_http_response_time_seconds_bucket{app="property-shared"}[30m])))
  ```
  Derivation: histogram_quantile(0.95) over the Fly proxy app-side latency histogram.
- **App HTTP p99 latency** (`fly_builtin`, derived)
  ```
  histogram_quantile(0.99, sum by (le) (rate(fly_app_http_response_time_seconds_bucket{app="property-shared"}[30m])))
  ```
  Derivation: histogram_quantile(0.99) over the Fly proxy app-side latency histogram.
- **Edge HTTP p95 latency** (`fly_builtin`, derived)
  ```
  histogram_quantile(0.95, sum by (le) (rate(fly_edge_http_response_time_seconds_bucket{app="property-shared"}[30m])))
  ```
  Derivation: histogram_quantile(0.95) over the Fly edge latency histogram.
- **Concurrency hard limit reached** (`fly_builtin`, derived)
  ```
  sum(increase(fly_app_hard_limit_reached_count{app="property-shared"}[30m]))
  ```
  Derivation: increase() over the window.
- **Concurrency soft limit reached** (`fly_builtin`, derived)
  ```
  sum(increase(fly_app_soft_limit_reached_count{app="property-shared"}[30m]))
  ```
  Derivation: increase() over the window.
- **Process RSS** (`app_custom`)
  ```
  process_resident_memory_bytes{app="property-shared"}
  ```
- **Process RSS peak over window** (`app_custom`, derived)
  ```
  max_over_time(process_resident_memory_bytes{app="property-shared"}[30m])
  ```
  Derivation: max_over_time of the scraped RSS gauge over the window.
- **Open file descriptors** (`app_custom`)
  ```
  process_open_fds{app="property-shared"}
  ```
- **App requests by surface/route/status class** (`app_custom`, derived)
  ```
  sum by (surface, route, status_class) (increase(property_shared_http_requests_total{app="property-shared"}[30m]))
  ```
  Derivation: increase() of the app's own request counter over the window.
- **App-measured request p95 latency** (`app_custom`, derived)
  ```
  histogram_quantile(0.95, sum by (le) (rate(property_shared_http_request_duration_seconds_bucket{app="property-shared"}[30m])))
  ```
  Derivation: histogram_quantile(0.95) over the app's own request-duration histogram.
- **MCP tool calls by tool and status** (`app_custom`, derived)
  ```
  sum by (tool, status) (increase(property_shared_tool_calls_total{app="property-shared"}[30m]))
  ```
  Derivation: increase() of the MCP tool-call counter over the window.
- **MCP client handshakes by client** (`app_custom`, derived)
  ```
  sum by (client_name) (increase(property_shared_client_connections_total{app="property-shared"}[30m]))
  ```
  Derivation: increase() of the MCP initialize-handshake counter over the window.
- **Machine memory available over time** (`fly_builtin`)
  ```
  fly_instance_memory_mem_available{app="property-shared"}
  ```
- **Root filesystem free over time** (`fly_builtin`, derived)
  ```
  fly_instance_filesystem_blocks_free{app="property-shared"} * fly_instance_filesystem_block_size{app="property-shared"}
  ```
  Derivation: blocks_free * block_size, per mount, sampled across the window.
- **Process RSS over time** (`app_custom`)
  ```
  process_resident_memory_bytes{app="property-shared"}
  ```
