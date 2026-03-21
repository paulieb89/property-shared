---
paths:
  - "mcp_server/**"
---

# MCP Server Rules

The MCP server wraps property_core for AI hosts (ChatGPT, Claude Desktop, Claude.ai). Uses `fastmcp>=3.0.0`.

## Tool Pattern

```python
@mcp.tool()
async def tool_name(param: str, optional: Optional[str] = None) -> ToolResult:
    """One-line description for AI hosts.

    Args:
        param: Description
        optional: Description
    """
    from property_core import SomeService  # lazy import

    result = await anyio.to_thread.run_sync(
        partial(SomeService().method, param=param)
    )
    data = result.model_dump(mode="json")
    summary = f"Found {result.count} items for {param}"
    return ToolResult(content=_content(summary, data), structured_content=data)
```

## Key Rules

- **All tools are async** — use `@mcp.tool()` decorator
- **Lazy imports** — `from property_core import X` inside the function body, not at module top
- **Sync wrapping** — `await anyio.to_thread.run_sync(partial(fn, **kwargs))` for sync property_core calls
- **ToolResult** — always return `ToolResult(content=..., structured_content=...)`

## Response Contract

- `_slim(obj)` — strips `raw`, `images`, `floorplans` keys recursively
- `_content(summary, data)` — builds: summary line + `\n\n` + slimmed JSON
- `content` field = summary + JSON — **all LLM hosts read this** (Claude.ai only reads `content[]`, not `structuredContent`)
- `structured_content` = full data dict — for MCP Apps, Claude Code, programmatic consumers
- Include `data_quality` where meaningful (good/low/insufficient)
- Include source counts (`sale_count`, `rental_count`) for transparency

## Host Quirks (ChatGPT)

- **Skips `ontoolinput`** — goes straight to `ontoolresult`. UI infers params from result data.
- **No serverTools proxy** — `callServerTool()` fails ("MCP proxy not enabled"). Use `sendMessage()` fallback.
- **Model Context Sync works** — `updateModelContext()` supported with capability guard.

## MCP App Contract

- Local state changes affecting model interpretation must fire `updateModelContext` on commit (mouseup, apply, selection change) — not continuously
- Capability guard required: `const caps = app.getHostCapabilities(); if (!caps?.updateModelContext) return;`
- Payload format: YAML frontmatter + markdown body

## References

- `mcp_server/MCP_APPS_REFERENCE.md` — Full SDK patterns documentation
- `mcp_server/GOLD.md` — Production readiness checklist
- Use `/create-mcp-app` skill for MCP App scaffolding
- Use `/add-mcp-tool` skill for adding new tools
