---
name: add-mcp-tool
description: Use when adding a new MCP tool to the property MCP server (mcp_server/server.py). Provides the exact pattern with a copy-paste template.
---

# Add an MCP Tool

Add a new tool to `mcp_server/server.py` following the established FastMCP pattern.

## Step 1: Add the Tool Function

Add to `mcp_server/server.py`. The docstring becomes the tool description for AI hosts.

```python
@mcp.tool()
async def new_tool(
    required_param: str,
    optional_param: Optional[str] = None,
    limit: int = 50,
) -> ToolResult:
    """One-line description of what this tool does.

    Args:
        required_param: UK postcode (e.g. "SW1A 1AA")
        optional_param: Optional filter description
        limit: Maximum results (default 50)
    """
    from property_core import SomeService  # Step 2: lazy import

    # Step 3: call property_core (sync → thread)
    result = await anyio.to_thread.run_sync(
        partial(
            SomeService().method,
            param=required_param,
            limit=limit,
        )
    )

    # Step 4: build and return ToolResult
    data = result.model_dump(mode="json")
    summary = f"Found {result.count} items for {required_param}"
    return ToolResult(content=_content(summary, data), structured_content=data)
```

## Key Rules

1. **Lazy imports** — `from property_core import X` inside the function body, never at module top level
2. **Async wrapping** — use `anyio.to_thread.run_sync(partial(...))` for sync property_core calls. For already-async functions, just `await` them directly.
3. **ToolResult construction**:
   - `content` = human-readable summary + slimmed JSON (via `_content()` helper)
   - `structured_content` = full data dict for programmatic consumers
4. **Configuration-gated tools** — if the data source needs credentials, check `is_configured()` and return early with an explanatory message if not configured. See `property_epc()` for the pattern.

## Helpers Available

- `_slim(obj)` — strips `raw`, `images`, `floorplans` from dicts recursively
- `_content(summary, data)` — builds content string: summary + "\n\n" + slimmed JSON

## Checklist

- [ ] Tool added to `mcp_server/server.py` with `@mcp.tool()`
- [ ] Function is `async`
- [ ] Imports are lazy (inside function body)
- [ ] Returns `ToolResult` with both `content` and `structured_content`
- [ ] Summary line includes key metrics (count, median, etc.)
- [ ] Docstring includes `Args:` section for all parameters
