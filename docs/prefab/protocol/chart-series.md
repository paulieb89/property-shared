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

# ChartSeries

> JSON Schema for the ChartSeries component.

Series definition for cartesian charts (Bar, Line, Area).

```json  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "object",
  "properties": {
    "dataKey": {
      "description": "Data field to plot",
      "type": "string"
    },
    "label": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Display label (defaults to dataKey)"
    },
    "color": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "CSS color override"
    }
  },
  "required": [
    "dataKey"
  ]
}
```


Built with [Mintlify](https://mintlify.com).