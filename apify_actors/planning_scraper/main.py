"""
UK Planning Portal Scraper - Apify Actor

Scrapes planning applications from any UK council portal using vision AI.
Handles 300+ different council systems (Idox, Arcus, NEC, etc.) with a single scraper.

Input:
    {
        "url": "https://planning.council.gov.uk/application/12345",
        "mode": "single|search|batch",
        "urls": ["url1", "url2"],  # for batch mode
        "searchUrl": "https://...",  # for search mode
        "maxResults": 20,
        "saveScreenshots": false
    }

Output:
    Planning application data including reference, address, proposal,
    status, decision, constraints, documents, and more.
"""
import asyncio
import json
import os
from pathlib import Path

# Apify SDK import (available when running on Apify platform)
try:
    from apify import Actor
    APIFY_AVAILABLE = True
except ImportError:
    APIFY_AVAILABLE = False
    Actor = None

# Import the planning scraper (local copy for Apify deployment)
from planning_scraper import (
    scrape_planning_application,
    scrape_planning_search,
    EXAMPLE_COUNCILS,
)


async def main():
    """Apify Actor main entry point."""

    if not APIFY_AVAILABLE:
        print("Running in local mode (Apify SDK not available)")
        # Local test mode
        test_input = {
            "url": "https://eplanning.birmingham.gov.uk/Northgate/PlanningExplorer/Generic/StdDetails.aspx?PT=Planning%20Applications",
            "mode": "single",
        }
        await run_scraper(test_input, local_mode=True)
        return

    async with Actor:
        # Get input from Apify
        actor_input = await Actor.get_input() or {}

        mode = actor_input.get("mode", "single")
        save_screenshots = actor_input.get("saveScreenshots", False)

        if mode == "single":
            # Single application scrape
            url = actor_input.get("url")
            if not url:
                raise ValueError("url is required for single mode")

            await Actor.set_status_message(f"Scraping: {url[:50]}...")

            output_dir = Path("./output") if save_screenshots else None
            result = await asyncio.to_thread(
                scrape_planning_application,
                url=url,
                output_dir=output_dir,
                save_screenshots=save_screenshots,
            )

            await Actor.push_data(result)
            await Actor.set_status_message(f"Complete: {result['data'].get('application', {}).get('reference', 'N/A')}")

        elif mode == "search":
            # Search results scrape
            search_url = actor_input.get("searchUrl")
            if not search_url:
                raise ValueError("searchUrl is required for search mode")

            max_results = actor_input.get("maxResults", 20)

            await Actor.set_status_message(f"Searching: {search_url[:50]}...")

            results = await asyncio.to_thread(
                scrape_planning_search,
                search_url=search_url,
                max_results=max_results,
            )

            for result in results:
                await Actor.push_data(result)

            await Actor.set_status_message(f"Found {len(results)} applications")

        elif mode == "batch":
            # Batch scrape multiple URLs
            urls = actor_input.get("urls", [])
            if not urls:
                raise ValueError("urls array is required for batch mode")

            output_dir = Path("./output") if save_screenshots else None

            for i, url in enumerate(urls):
                await Actor.set_status_message(f"Scraping {i+1}/{len(urls)}: {url[:40]}...")

                try:
                    result = await asyncio.to_thread(
                        scrape_planning_application,
                        url=url,
                        output_dir=output_dir,
                        save_screenshots=save_screenshots,
                    )
                    await Actor.push_data(result)
                except Exception as e:
                    await Actor.push_data({
                        "url": url,
                        "error": str(e),
                    })

            await Actor.set_status_message(f"Complete: {len(urls)} applications processed")

        else:
            raise ValueError(f"Unknown mode: {mode}. Use 'single', 'search', or 'batch'")


async def run_scraper(input_data: dict, local_mode: bool = False):
    """Run scraper in local mode for testing."""
    url = input_data.get("url")
    if url:
        result = scrape_planning_application(
            url=url,
            output_dir=Path("./output"),
            save_screenshots=True,
        )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
