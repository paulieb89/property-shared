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

# DataTableColumn

> JSON Schema for the DataTableColumn component.

Column definition for DataTable.

```json  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "object",
  "properties": {
    "key": {
      "description": "Data key to display in this column",
      "type": "string"
    },
    "header": {
      "description": "Column header text",
      "type": "string"
    },
    "sortable": {
      "default": false,
      "description": "Enable sorting for this column",
      "type": "boolean"
    },
    "format": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Cell format: 'number', 'number:2' (decimals), 'currency', 'currency:EUR', 'percent', 'percent:1', 'date', 'date:long'"
    },
    "width": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Column width as CSS value (e.g. '200px', '30%')"
    },
    "minWidth": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Minimum column width as CSS value"
    },
    "maxWidth": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Maximum column width as CSS value"
    },
    "align": {
      "enum": [
        "left",
        "center",
        "right"
      ],
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Cell text alignment \u2014 resolves to cell_class"
    },
    "headerClass": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Tailwind classes for header cells"
    },
    "cellClass": {
      "type": [
        "string",
        "null"
      ],
      "default": null,
      "description": "Tailwind classes for data cells"
    }
  },
  "required": [
    "key",
    "header"
  ]
}
```


Built with [Mintlify](https://mintlify.com).