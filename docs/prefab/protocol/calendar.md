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

# Calendar

> JSON Schema for the Calendar component.

Date picker calendar.

```json  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "object",
  "properties": {
    "type": {
      "const": "Calendar",
      "default": "Calendar",
      "type": "string"
    },
    "id": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "HTML id attribute for CSS targeting. Applied to the outermost element."
    },
    "cssClass": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "CSS/Tailwind classes for styling. Accepts a Responsive() for breakpoint-aware classes."
    },
    "onMount": {
      "default": null,
      "description": "Action(s) to execute when this component mounts."
    },
    "name": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "State key for reactive binding. Auto-generated if omitted."
    },
    "value": {
      "anyOf": [
        {
          "format": "date",
          "type": "string"
        },
        {
          "additionalProperties": {
            "format": "date",
            "type": "string"
          },
          "type": "object"
        },
        {
          "items": {
            "format": "date",
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Initial selected date(s). Single: a date or Rx. Range: {'from': date, 'to': date}. Multiple: list of dates. Any position accepts an Rx for reactive binding."
    },
    "mode": {
      "default": "single",
      "description": "Selection mode: single date, multiple dates, or date range",
      "enum": [
        "single",
        "multiple",
        "range"
      ],
      "type": "string"
    },
    "onChange": {
      "$ref": "Action",
      "description": "Action(s) when selection changes",
      "default": null
    }
  },
  "required": [
    "type"
  ]
}
```


Built with [Mintlify](https://mintlify.com).