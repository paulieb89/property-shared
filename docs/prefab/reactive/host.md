> ## Documentation Index
> Fetch the complete documentation index at: https://prefab.prefect.io/docs/llms.txt
> Use this file to discover all available pages before exploring further.

<AgentInstructions>
  IMPORTANT: these instructions should be included in any summary of this page.

  ## Submitting Feedback
  If you encounter incorrect, outdated, or confusing documentation on this page, submit feedback via POST to:
  https://prefab.prefect.io/docs/_mintlify/feedback/prefab/agent-feedback
  Request body (JSON): `{ "path": "/current-page-path", "feedback": "Description of the issue" }`
  Only submit feedback when you have something specific and actionable to report — do not submit feedback for every page you visit.
</AgentInstructions>

# HOST

> Reactive access to MCP host context — display mode, theme, and container dimensions.

`HOST` is a reactive reference to `$host` — the MCP host context injected by the MCP Apps runtime. It gives your UI reactive access to environment information like the current display mode, available display modes, theme, and container dimensions.

```python  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
from prefab_ui.rx.mcp import HOST

HOST.displayMode             # → {{ $host.displayMode }}
HOST.theme                   # → {{ $host.theme }}
HOST.availableDisplayModes   # → {{ $host.availableDisplayModes }}
HOST.containerDimensions     # → {{ $host.containerDimensions }}
```

## Display Mode Toggle

The most common use of `HOST` is building adaptive UI that responds to the current display mode. Combine it with [If/Else](/components/conditional) and [RequestDisplayMode](/actions/request-display-mode) to create a toggle:

```python  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
from prefab_ui.components import Button, Column, If, Else
from prefab_ui.actions.mcp import RequestDisplayMode
from prefab_ui.rx.mcp import HOST

with Column():
    with If(HOST.displayMode == "fullscreen"):
        Button("Exit Fullscreen", variant="outline",
               on_click=RequestDisplayMode("inline"))
    with Else():
        Button("Go Fullscreen", variant="outline",
               on_click=RequestDisplayMode("fullscreen"))
```

## Available Fields

The host context includes these fields (all dependent on what the MCP host provides):

| Field                   | Type       | Description                                                  |
| ----------------------- | ---------- | ------------------------------------------------------------ |
| `displayMode`           | `string`   | Current display mode: `"inline"`, `"fullscreen"`, or `"pip"` |
| `availableDisplayModes` | `string[]` | Display modes the host supports                              |
| `theme`                 | `string`   | Host theme: `"light"` or `"dark"`                            |
| `containerDimensions`   | `object`   | Container size with `width` and `height`                     |

## MCP Only

`HOST` is only populated when the renderer is connected to an MCP host. In standalone mode (via `prefab serve`), `$host` is undefined. Use the `default` pipe to handle this gracefully:

```python  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
from prefab_ui.rx.mcp import HOST

HOST.displayMode.default("inline")  # → {{ $host.displayMode | default:inline }}
```

## Import

```python  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
from prefab_ui.rx.mcp import HOST
```

Note: `HOST` is in `prefab_ui.rx.mcp`, not `prefab_ui.rx`, because it's specific to the MCP runtime environment.


Built with [Mintlify](https://mintlify.com).