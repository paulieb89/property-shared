# Skill Observations Log

---

### Observation 1
**Date:** 2026-05-17
**Session context:** Investigating persistent EPC bug — property_epc tool returning wrong data when house number unknown (Rightmove use case)
**Skill:** mcp-primitive-classification / fastmcp-design-review
**Type:** Design pattern — modes vs separate tools
**Issue:** A single tool (`property_epc`) with an optional `address` parameter was used to encode three fundamentally different behaviours: address-matched single cert, area aggregate summary, and (missing) postcode browse. The "mode" encoding hid the output schema instability from the LLM — different input shapes produce incompatible output shapes, which causes repeated failed fix attempts because each fix addresses one mode without accounting for the others.
**Suggested improvement:** When a tool's output schema changes significantly based on an optional parameter, that is a signal to split into separate tools. The classification rule — "LLM decides which to invoke" — works best when each tool has a stable, predictable output contract.
**Principle:** One tool, one output schema. Modes that produce incompatible output shapes belong in separate tools.
**Status:** OPEN

---

### Observation 2
**Date:** 2026-05-17
**Session context:** Same session — EPC fix investigation
**Skill:** General debugging / investigation methodology
**Type:** Investigation order — verify data availability before designing around its absence
**Issue:** Multiple rounds of fix attempts were made to the address matching and EPC tool design without first checking whether the Rightmove PAGE_MODEL `address` dict contains UPRN or a full structured address. The scraper extracts only three keys (`displayAddress`, `outcode`, `incode`) from a dict that may contain more. If UPRN is present, the entire fuzzy matching problem is bypassed via direct EPC UPRN lookup.
**Suggested improvement:** Before designing a workaround for missing data, verify the data is actually missing at the source. A single live dump of `address_info.keys()` from a real Rightmove listing detail page would have resolved the architectural question before any code was written.
**Principle:** Check the raw payload before designing around assumed data gaps. The fix may already be in the data.
**Status:** OPEN

---

### Observation 3
**Date:** 2026-05-17
**Session context:** Same session — EPC fuzzy matcher scoring analysis
**Skill:** Systematic debugging
**Type:** Bug — fuzzy matcher produces wrong-street false positives
**Issue:** `match_score` in `address_matching.py` scores "CAVENDISH CRESCENT NORTH" at 36 against "Cavendish Crescent South" — above the 30-point threshold — because `extract_street` takes only the first two words after stripping a leading number, so both map to "cavendish crescent". Word-overlap scoring adds more points on shared words. The result: the matcher returns an EPC cert from the wrong street as a confident match. Additionally, `extract_number` naively matches the flat number in "FLAT 1, 5 HIGH STREET" rather than the building number, causing all flat-format EPC addresses to score ~9 when the target has no house number.
**Suggested improvement:** `extract_street` should include directional/qualifier words (North, South, East, West, Upper, Lower) as part of the street token rather than truncating at 2 words. `extract_number` should skip "FLAT N," and "APARTMENT N," prefixes before extracting the building number. The 30-point threshold should be raised when no house number is present in the target (confidence is inherently lower).
**Principle:** Address matching edge cases must be tested with a score matrix before shipping — the failure modes are not obvious from reading the code.
**Status:** CLOSED — fixed in commit 9db9425. extract_number strips flat/apartment prefixes, extract_street takes 3 words, match_epc_address raises threshold to 50 when target has no house number. Score matrix verified: wrong-street dropped from 36→6, flat cert with building number rose from 12→62.

---

### Observation 4
**Date:** 2026-05-17
**Session context:** Same session — structured_content vs content in FastMCP ToolResult
**Skill:** fastmcp-design-review / mcp-primitive-classification
**Type:** Clarification — structured_content is a client-side channel, not guaranteed LLM context
**Issue:** There was uncertainty about whether `structured_content` in FastMCP's `ToolResult` is visible to the LLM. Investigation confirmed: `structured_content` maps to `structuredContent` in `CallToolResult` in the MCP wire protocol — it is returned alongside `content` but whether it is injected into the LLM's context window is a host implementation decision. For Prefab dashboard rendering in property_app, structured_content drives the UI components, not the LLM. For tasks where the LLM must read and reason on data, the data must be in `content` (text blocks).
**Suggested improvement:** When designing tools where the LLM needs to browse or reason on returned data, use plain dict returns (serialized to JSON text in `content`). Reserve `ToolResult` with `structured_content` for: (a) image embedding, (b) Prefab/dashboard rendering, (c) programmatic downstream consumers. Document this distinction in the MCP tool design guidelines.
**Principle:** If the LLM needs to read it, put it in `content`. `structured_content` is for machines.
**Status:** OPEN

---

### Observation 5
**Date:** 2026-05-17
**Session context:** Rightmove PAGE_MODEL dump to check for UPRN — live diagnostic script against real listing 88378815
**Skill:** systematic-debugging / add-data-source
**Type:** Investigation result — data availability determines architecture
**Issue:** Multiple EPC fix attempts assumed UPRN was unavailable from Rightmove without verifying. Live dump confirmed: no UPRN. But the dump also revealed `sizings` — a structured array with numeric floor area per unit (sqm, sqft) — which the scraper was throwing away entirely. `floor_area_sqm` from `sizings` is a strong EPC discriminator requiring no address matching. The field was already being fetched; we just weren't capturing it.
**Suggested improvement:** When investigating a missing-data bug, dump the full raw payload before designing a workaround. A diagnostic script (`scripts/rightmove_address_dump.py`) that prints all keys should be the first step. Also worth scanning top-level keys for promising fields (`epcGraphs`, `sizings`, `entranceFloor`, `buildingId`) — several were present and uncaptured.
**Principle:** Dump the raw payload first. The fix is often in data you're already receiving but not capturing.
**Status:** OPEN

---

### Observation 6
**Date:** 2026-05-17
**Session context:** Adding `_extract_sizings` helper to `models/rightmove.py`
**Skill:** General — code style / helper extraction heuristic
**Type:** Feedback — when to write a helper vs inline a field extraction
**Issue:** Initial instinct was to inline `floor_area_sqm`/`floor_area_sqft` extraction directly into `from_page_model`. User corrected: extraction that iterates a list, branches on unit type, guards against missing values, and returns a tuple warrants a dedicated helper — consistent with `_extract_images`, `_extract_floorplans`, `_extract_display_size`, `_extract_key_features`.
**Suggested improvement:** Apply this heuristic: if it's a single `.get()` with a type coercion, inline it (`_safe_int`/`_safe_float`/`_str_or_none` already handle this). If it iterates a structure, branches on values, or returns multiple things, write a named helper. The distinction is complexity, not line count.
**Principle:** Write a helper when extraction iterates or branches. Inline it when it's a single `.get()` with coercion — that's what the `_safe_*` helpers are already for.
**Status:** OPEN

---

### Observation 7
**Date:** 2026-05-17
**Session context:** Design review of `property_epc_search` — user questioned whether `lmk_key` in the slim response was deliberate or noise
**Skill:** fastmcp-design-review / mcp-primitive-classification
**Type:** Design pattern — every key returned by a tool must have a load-bearing consumer tool
**Issue:** `lmk_key` was included in the `property_epc_search` slim response, but the described follow-up workflow used `property_epc(postcode, address)` — not `get_certificate(lmk_key)`. So `lmk_key` was present with nowhere to go: it looked deliberate but was functionally noise. `EPCClient.get_certificate()` already existed in the client but hadn't been exposed as an MCP tool.
**Suggested improvement:** Before including a lookup key in a tool's response, verify there is a corresponding tool that accepts it. If `lmk_key` is in the response, `get_certificate(lmk_key)` must exist as a tool. If the follow-up tool uses `address` instead, drop `lmk_key`. The fix is either expose the tool or remove the key — not leave both in an inconsistent state.
**Principle:** Every key returned by a browse/list tool that is intended as a follow-up identifier must have a corresponding lookup tool that accepts it. Keys without consumers are noise.
**Status:** OPEN

---

### Observation 8
**Date:** 2026-05-17
**Session context:** Tightening `property_epc_search` docstring — cross-reference instruction was suggestive, not imperative
**Skill:** fastmcp-design-review
**Type:** Tool description language — imperative vs suggestive for required steps
**Issue:** The original docstring said "Match by floor_area proximity (within ~5 sqm) and property_type" — phrased as a suggestion. LLMs treat suggestive phrasing as optional guidance they can override with their own reasoning. For a required cross-referencing step (the whole point of the tool), this is too weak: the LLM may skip or loosen the constraint depending on context.
**Suggested improvement:** Use "You MUST" for steps that are non-negotiable. The updated docstring reads "You MUST cross-reference each cert's floor_area against the listing's floor_area_sqm (accept within ±5 sqm) AND property_type must match." Also explicitly handle the fallback: "If floor_area is unavailable on the listing, filter by property_type only and return all candidates." Covering the fallback prevents the LLM from guessing when the discriminator is missing.
**Principle:** Required cross-referencing steps in tool descriptions must use imperative language ("MUST", "must match"). Suggestive phrasing ("match by", "use X to") is treated as optional. Always cover the fallback case explicitly.
**Status:** OPEN

---

### Observation 9
**Date:** 2026-05-17
**Session context:** Porting `property_epc_search` docstring from plain MCP server to MCP app `epc_search`
**Skill:** General — docstring porting across consumers
**Type:** Bug — workflow tool names not updated when porting docstrings between consumers
**Issue:** When porting the EPC browse workflow docstring from `app/mcp/server.py` to `property_app/tools.py`, step 1 was copied as "Call `rightmove_search`..." but the correct tool in the MCP app context is `rightmove_listing`. The plain server had `rightmove_listing` correctly; the MCP app copy introduced the wrong tool name. This directs the LLM to call a tool that returns listing summaries without `floor_area_sqm` — the exact field the workflow depends on.
**Suggested improvement:** When porting a multi-step workflow docstring from one consumer to another, treat every tool name in the workflow as a variable that must be verified against the target consumer's tool inventory. A quick grep for each named tool confirms it exists in that server before committing.
**Principle:** Tool names in workflow docstrings are consumer-specific. Copy-pasting a workflow description without auditing each tool reference against the target consumer's tool list is a latent functional bug.
**Status:** CLOSED — fixed in commit 23a2c57.

---

### Observation 10
**Date:** 2026-05-17
**Session context:** Writing unit test for `property_epc_search` None-value stripping
**Skill:** General — testing patterns with mocked Pydantic models
**Type:** Bug — test asserting behavior that mocks cannot exercise
**Issue:** A test was written to verify that `exclude_none=True` in `model_dump()` strips None values from the cert list. The mock returned None values in `model_dump.return_value` and the test asserted those keys were absent in the output. But `model_dump` is a MagicMock — it ignores the `exclude_none=True` kwarg and returns whatever was set as `return_value`. The test was asserting Pydantic's own behavior through a path that bypasses Pydantic entirely, so it failed immediately.
**Suggested improvement:** When testing code that calls `model_dump(exclude_none=True)`, either (a) use a real Pydantic model instance so `exclude_none` actually takes effect, or (b) have the mock return a dict that already omits None keys (simulating what a real model produces), and test the surrounding logic rather than Pydantic's serialisation. For this codebase, option (b) is simpler.
**Principle:** Mocks ignore keyword arguments. Never write a test that asserts the effect of a kwarg passed to a mocked method — the assertion will reflect the mock's `return_value`, not the kwarg's effect.
**Status:** CLOSED — test rewritten to verify keep-field filtering (what our code does) rather than `exclude_none` behavior (what Pydantic does).

---

### Observation 9
**Date:** 2026-05-17
**Session context:** Pre-push code review of 3 unpushed commits — epc_search docstring bug found
**Skill:** fastmcp-design-review / code-review
**Type:** Bug class — tool workflow docstrings referencing wrong tool names
**Issue:** `epc_search` in `property_app/tools.py` step 1 said "Call rightmove_search to obtain floor_area_sqm" — but `rightmove_search` returns listing summaries with no floor area. `rightmove_listing` (the detail tool) is what returns `floor_area_sqm`. The plain MCP server version of the same tool correctly named `rightmove_listing`. The bug was introduced because the two surfaces were written separately and the docstring wasn't cross-checked against the tool list.
**Suggested improvement:** Before committing, verify every tool name mentioned in a docstring workflow exists at the same MCP surface and accepts the described inputs. When the same workflow is implemented on two surfaces (plain server + MCP app), diff the docstrings to confirm they name the same tools. The wrong tool name won't raise an error — it will silently cause the LLM to call the wrong tool and return incomplete data.
**Principle:** Workflow tool names in docstrings are executable instructions to the LLM — verify them against the actual tool list at the same surface before committing. Wrong tool names are silent bugs.
**Status:** OPEN

---

### Observation 10
**Date:** 2026-05-17
**Session context:** Pre-push code review — tool naming inconsistency across plain MCP server and MCP app
**Skill:** fastmcp-design-review
**Type:** Design pattern — cross-surface tool name consistency
**Issue:** The same lmk_key lookup tool was named `get_epc_certificate` on the plain server (`app/mcp/server.py`) and `epc_certificate` on the MCP app (`property_app/tools.py`). Additionally, the plain server's `property_epc_search` docstring referenced `get_certificate(lmk_key)` — a name that matched neither. Users and LLMs that switch between the two surfaces encounter different tool names for the same operation.
**Suggested improvement:** In a repo with two MCP surfaces, adopt a naming convention at the start: either both use `get_epc_certificate` or both use `epc_certificate`. The MCP app already has a consistent prefix-free style (`epc_search`, `epc_certificate`, `epc_lookup`) — the plain server should match. Docstring cross-references must use the exact name of the tool on that surface.
**Principle:** When a capability is implemented on multiple MCP surfaces, use the same tool name on each. Divergent names force LLMs (and developers) to maintain a mental mapping that doesn't exist anywhere in the code.
**Status:** OPEN

---

### Observation 12
**Date:** 2026-05-17
**Session context:** Adding Prometheus tool-call metrics to `app/mcp/server.py` — the plain MCP server had no `tool_calls_total` counter despite the Grafana dashboard querying for it.
**Skill:** add-mcp-tool / audit-server
**Type:** Fleet pattern — sync+async mixed MCP server instrumentation
**Issue:** Most fleet servers are fully async so a simple `async def _wrapped` decorator covers all tools. `property-shared`'s plain MCP server (`app/mcp/server.py`) has a mix: ~10 async tools and 3 sync tools (`stamp_duty`, `company_search`, `planning_search`). A decorator that always returns `async def _wrapped` would silently change sync tools to coroutines, which FastMCP may or may not handle correctly depending on version.
**Suggested improvement:** When adding a `_timed_tool` decorator to any MCP server, check with `asyncio.iscoroutinefunction(fn)` and branch to separate `async def _wrapped` / `def _wrapped` paths. Use `functools.wraps` on both so FastMCP's signature introspection (which follows `__wrapped__`) still sees the original parameter schema. The govuk-mcp reference only has async tools so it doesn't model this case.
**Principle:** MCP tool decorators must preserve both the sync/async nature and the function signature of the wrapped tool. Use `asyncio.iscoroutinefunction` + `functools.wraps` to handle mixed-mode servers safely.
**Status:** OPEN

---

### Observation 11
**Date:** 2026-05-17
**Session context:** Pre-push code review of 3 unpushed commits — false-positive bug report due to large diff misread
**Skill:** code-review / systematic-debugging
**Type:** Review methodology — verify findings in the actual file before reporting
**Issue:** During a `/review` of a 34.5KB aggregated diff (3 commits, `git diff origin/main..HEAD`), I reported that `epc_search` in `property_app/tools.py` had "Call rightmove_search" in its workflow — a genuine bug. When I then read the actual file, line 308 had "Call rightmove_listing". The committed file was correct all along. The most likely cause: the diff contained two similar docstring blocks (`property_epc_search` in `app/mcp/server.py` and `epc_search` in `property_app/tools.py`) and I attributed content from the wrong section. Large aggregated diffs with repeated patterns across files are high-noise and easy to misread.
**Suggested improvement:** After identifying a specific bug in a diff, read the actual file at the reported line before including it in the review output. A one-line `grep -n` check costs almost nothing and prevents false positives. For large diffs (>20KB), prefer reading specific sections of the files directly rather than relying on the aggregated diff text.
**Principle:** A bug reported from a diff is a hypothesis. Verify it in the actual file before stating it as a finding.
**Status:** OPEN
