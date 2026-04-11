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

# DataTable

> JSON Schema for the DataTable component.

High-level data table with sorting, filtering, and pagination.

```json  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "object",
  "properties": {
    "type": {
      "const": "DataTable",
      "default": "DataTable",
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
    "columns": {
      "description": "Column definitions",
      "items": {
        "$ref": "DataTableColumn"
      },
      "type": "array"
    },
    "rows": {
      "anyOf": [
        {
          "items": {
            "additionalProperties": true,
            "type": "object"
          },
          "type": "array"
        },
        {
          "type": "string"
        }
      ],
      "description": "Row data, `{{ interpolation }}` reference, or DataFrame"
    },
    "search": {
      "default": false,
      "description": "Show search input",
      "type": "boolean"
    },
    "paginated": {
      "default": false,
      "description": "Show pagination controls",
      "type": "boolean"
    },
    "pageSize": {
      "default": 10,
      "description": "Rows per page when paginated",
      "type": "integer"
    },
    "onRowClick": {
      "$ref": "Action",
      "description": "Action(s) when a row is clicked. $event is the row data dict.",
      "default": null
    }
  },
  "required": [
    "type",
    "columns"
  ]
}
```


Built with [Mintlify](https://mintlify.com).