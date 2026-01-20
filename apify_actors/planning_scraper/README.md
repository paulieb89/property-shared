# UK Planning Portal Scraper

Scrape planning applications from **any UK council planning portal** using vision AI.

## The Problem

The UK has 300+ local planning authorities, each with their own planning portal. They use different software systems:
- **Idox Public Access** (most common)
- **Arcus / NEC Uniform**
- **Northgate**
- **Ocella**
- **Custom systems**

Building traditional scrapers requires maintaining 300+ different parsers.

## The Solution

This actor uses **Playwright + OpenAI Vision** to "read" any planning portal like a human would:

1. Loads the planning application page
2. Scrolls through and captures screenshots
3. Clicks through tabs (Summary, Details, Documents, etc.)
4. Sends screenshots to GPT-4 Vision
5. Extracts structured data

**One scraper handles all 300+ councils.**

## Input

### Single Application
```json
{
    "mode": "single",
    "url": "https://eplanning.birmingham.gov.uk/..."
}
```

### Search Results
```json
{
    "mode": "search",
    "searchUrl": "https://planning.council.gov.uk/search?postcode=B1",
    "maxResults": 20
}
```

### Batch
```json
{
    "mode": "batch",
    "urls": [
        "https://planning.council1.gov.uk/app/123",
        "https://planning.council2.gov.uk/app/456"
    ]
}
```

## Output

```json
{
    "url": "https://...",
    "council_system": "idox",
    "screenshots_captured": 8,
    "data": {
        "application": {
            "reference": "2024/01234/PA",
            "application_type": "Full Planning",
            "status": "Pending Decision",
            "decision": null,
            "target_date": "2024-03-15"
        },
        "site": {
            "address": "123 High Street, Birmingham, B1 1AA",
            "ward": "Ladywood",
            "conservation_area": null
        },
        "proposal": {
            "description": "Change of use from retail to restaurant",
            "use_class": "E(b)"
        },
        "dates": {
            "received": "2024-01-15",
            "consultation_end": "2024-02-15"
        },
        "constraints": ["Flood Zone 2", "City Centre"],
        "documents": [
            {"name": "Site Plan", "type": "Plans"},
            {"name": "Design Statement", "type": "Statement"}
        ]
    }
}
```

## Supported Councils

Works with any UK council planning portal. Tested with:
- Birmingham, Manchester, Leeds, Bristol, Liverpool
- Sheffield, Newcastle, Westminster, Camden, Islington
- And 290+ more...

## Cost

Uses OpenAI Vision API:
- ~$0.01-0.03 per application (depending on page length)
- Cheaper than maintaining 300 separate scrapers!

## Environment Variables

Set your OpenAI API key:
```
OPENAI_API_KEY=sk-...
```

Optional:
```
OPENAI_VISION_MODEL=gpt-4o-mini  # or gpt-4o for better accuracy
```
