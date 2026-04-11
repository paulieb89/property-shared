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

# Select

> JSON Schema for the Select component.

Select dropdown container.

```json  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "object",
  "properties": {
    "type": {
      "const": "Select",
      "default": "Select",
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
    "children": {
      "type": "array",
      "items": {
        "$ref": "Component"
      }
    },
    "let": {
      "additionalProperties": true,
      "type": [
        "object",
        "null"
      ],
      "default": null,
      "description": "Scoped bindings available to children. Values are template strings."
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
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Initially selected option value"
    },
    "placeholder": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Placeholder text"
    },
    "size": {
      "default": "default",
      "description": "Select size (sm, default)",
      "enum": [
        "sm",
        "default"
      ],
      "type": "string"
    },
    "side": {
      "enum": [
        "top",
        "right",
        "bottom",
        "left"
      ],
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Which side of the trigger the dropdown appears on"
    },
    "align": {
      "enum": [
        "start",
        "center",
        "end"
      ],
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Alignment of the dropdown relative to the trigger"
    },
    "disabled": {
      "default": false,
      "description": "Whether select is disabled",
      "type": "boolean"
    },
    "required": {
      "default": false,
      "description": "Whether select is required",
      "type": "boolean"
    },
    "invalid": {
      "default": false,
      "description": "Whether select shows error/invalid styling",
      "type": "boolean"
    },
    "onChange": {
      "$ref": "Action",
      "description": "Action(s) to execute when selection changes",
      "default": null
    }
  },
  "required": [
    "type"
  ]
}
```


Built with [Mintlify](https://mintlify.com).