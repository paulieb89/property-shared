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

# Alert

> JSON Schema for the Alert component.

An alert container for important messages.

```json  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "object",
  "properties": {
    "type": {
      "const": "Alert",
      "default": "Alert",
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
    "variant": {
      "anyOf": [
        {
          "enum": [
            "default",
            "destructive",
            "success",
            "warning",
            "info"
          ],
          "type": "string"
        },
        {
          "type": "string"
        }
      ],
      "default": "default",
      "description": "Visual variant: default, destructive, success, warning, info"
    },
    "icon": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Lucide icon name (kebab-case, e.g. 'circle-alert')"
    }
  },
  "required": [
    "type"
  ]
}
```


Built with [Mintlify](https://mintlify.com).