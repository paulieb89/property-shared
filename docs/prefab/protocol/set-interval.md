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

# SetInterval

> JSON Schema for the SetInterval action.

Execute actions on a repeating schedule.

```json  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "object",
  "properties": {
    "action": {
      "const": "setInterval",
      "default": "setInterval",
      "type": "string"
    },
    "duration": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "string"
        }
      ],
      "description": "Interval between ticks, in milliseconds. Accepts Rx for reactive values."
    },
    "while": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Condition expression re-evaluated each tick. When falsy, the interval stops."
    },
    "count": {
      "type": [
        "integer",
        "null"
      ],
      "default": null,
      "description": "Maximum number of ticks. The interval stops after this many."
    },
    "onTick": {
      "$ref": "Action",
      "description": "Action(s) to run each tick. $event is the tick number (1, 2, \u2026).",
      "default": null
    },
    "onComplete": {
      "$ref": "Action",
      "description": "Action(s) to run when the interval finishes.",
      "default": null
    }
  },
  "required": [
    "action",
    "duration"
  ]
}
```


Built with [Mintlify](https://mintlify.com).