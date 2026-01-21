"""
Vision-based UK planning portal scraper using Playwright + OpenAI Vision.

Handles the fragmented UK planning system (300+ councils, multiple software vendors)
by using vision to "read" any planning portal like a human would.

Supported council systems:
- Idox Public Access (most common)
- Arcus (NEC)
- Uniform (NEC)
- Ocella
- Agile Planning
- Custom council systems

Usage:
    from property_core.planning_scraper import scrape_planning_application

    result = scrape_planning_application(
        url="https://planning.birmingham.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=ABC123",
        output_dir=Path("./output/planning")
    )
"""
import base64
import json
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI

try:
    from playwright.sync_api import sync_playwright, Page
except ImportError:
    sync_playwright = None
    Page = None

client = OpenAI()

# Planning-specific extraction prompt
PLANNING_EXTRACTION_PROMPT = """You are a UK planning data extraction expert. Analyze these screenshots from a council planning portal and extract ALL visible planning application information into structured JSON.

IMPORTANT: Extract EVERYTHING you can see. Be thorough. Include exact reference numbers and dates.

{
    "application": {
        "reference": "planning application reference number (e.g., 2024/01234/PA)",
        "alternative_reference": "any other reference shown",
        "application_type": "Full, Outline, Householder, Prior Approval, Listed Building, Advertisement, Tree Works, etc.",
        "status": "Pending Decision, Approved, Refused, Withdrawn, Appeal, etc.",
        "decision": "Grant, Refuse, Withdrawn, etc. if decided",
        "decision_date": "date of decision if shown",
        "decision_level": "Delegated, Committee, etc.",
        "target_date": "target decision date",
        "expiry_date": "permission expiry date if approved"
    },

    "site": {
        "address": "full site address as shown",
        "postcode": "if visible",
        "easting": "OS grid reference if shown",
        "northing": "OS grid reference if shown",
        "ward": "council ward name",
        "parish": "parish council if shown",
        "conservation_area": "name if in conservation area, null if not",
        "listed_building": "grade and name if listed, null if not"
    },

    "proposal": {
        "description": "full description of the proposed development",
        "use_class": "current or proposed use class (E, F1, C3, etc.)",
        "units_existing": "number of existing units/dwellings if shown",
        "units_proposed": "number of proposed units/dwellings if shown",
        "floor_area_sqm": "floor area if shown",
        "height": "building height if shown"
    },

    "applicant": {
        "name": "applicant name",
        "company": "company name if applicable",
        "address": "applicant address if shown"
    },

    "agent": {
        "name": "agent/architect name",
        "company": "agent company",
        "address": "agent address",
        "phone": "if shown",
        "email": "if shown"
    },

    "dates": {
        "received": "date application received",
        "validated": "date application validated",
        "consultation_start": "public consultation start date",
        "consultation_end": "public consultation end/expiry date",
        "committee_date": "planning committee date if applicable",
        "decision_date": "date decision was made"
    },

    "constraints": [
        "list all planning constraints shown: Green Belt, Flood Zone 2/3, SSSI, AONB, Conservation Area, Article 4, TPO, Listed Building curtilage, etc."
    ],

    "consultations": {
        "neighbour_letters": "number sent if shown",
        "site_notice": "yes/no/date",
        "press_notice": "yes/no/date",
        "comments_for": "number of supporting comments",
        "comments_against": "number of objection comments",
        "comments_neutral": "number of neutral comments"
    },

    "documents": [
        {
            "name": "document name",
            "type": "Plans, Design Statement, Heritage Statement, etc.",
            "date": "upload date if shown"
        }
    ],

    "case_officer": {
        "name": "planning officer name",
        "phone": "if shown",
        "email": "if shown"
    },

    "conditions": [
        "list any planning conditions if decision is shown"
    ],

    "appeal": {
        "status": "if appeal lodged",
        "reference": "appeal reference",
        "decision": "appeal decision if known"
    },

    "related_applications": [
        "list any related/linked application references"
    ],

    "additional_info": "any other important information not captured above"
}

Rules:
- Use null for fields with no data visible
- Preserve exact reference numbers and dates as shown
- Include ALL constraints visible on the page
- List ALL documents if a documents tab is shown
- Note any CIL/S106 obligations if mentioned
- Extract committee report summary if visible"""


# Common tab selectors for different council systems
COUNCIL_TAB_SELECTORS = {
    "idox": [
        "a[href*='activeTab=summary']",
        "a[href*='activeTab=details']",
        "a[href*='activeTab=dates']",
        "a[href*='activeTab=map']",
        "a[href*='activeTab=constraints']",
        "a[href*='activeTab=documents']",
        "a[href*='activeTab=relatedCases']",
        "a[href*='activeTab=makeComment']",
    ],
    "arcus": [
        ".tab-summary",
        ".tab-details",
        ".tab-documents",
        ".tab-map",
        ".tab-comments",
    ],
    "generic": [
        "a:has-text('Summary')",
        "a:has-text('Details')",
        "a:has-text('Documents')",
        "a:has-text('Map')",
        "a:has-text('Constraints')",
        "a:has-text('Comments')",
        "a:has-text('Related')",
        "[role='tab']",
    ],
}


# Cost control defaults
DEFAULT_MAX_SCREENSHOTS = 12  # Cap total screenshots sent to Vision
DEFAULT_MAX_SCROLLS = 6       # Max scroll captures per page
DEFAULT_VIEWPORT = (1440, 900)  # Smaller viewport = less detail = cheaper
DEFAULT_IMAGE_QUALITY = 70    # JPEG quality (lower = smaller = cheaper)
DEFAULT_VISION_DETAIL = "auto"  # "low" (85 tokens), "high" (765 tokens), or "auto"


def screenshot_to_base64(screenshot_bytes: bytes, quality: int = DEFAULT_IMAGE_QUALITY) -> str:
    """Convert screenshot to base64, optionally compressing as JPEG."""
    try:
        from PIL import Image
        import io

        # Convert PNG to compressed JPEG
        img = Image.open(io.BytesIO(screenshot_bytes))
        if img.mode == 'RGBA':
            img = img.convert('RGB')

        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode()
    except ImportError:
        # PIL not available, use raw PNG
        return base64.b64encode(screenshot_bytes).decode()


def extract_with_vision(
    images: list[dict],
    prompt: str,
    detail: str = DEFAULT_VISION_DETAIL,
    max_images: int = DEFAULT_MAX_SCREENSHOTS,
) -> dict:
    """Send screenshots to OpenAI Vision using the Responses API."""
    # Limit images to control costs
    images_to_send = images[:max_images]
    if len(images) > max_images:
        print(f"  Warning: Truncated {len(images)} images to {max_images}")

    # Build content array for Responses API (input_text / input_image format)
    content: list[dict] = []
    for img in images_to_send:
        media_type = img.get('media_type', 'image/jpeg')
        data_url = f"data:{media_type};base64,{img['data']}"
        content.append({
            "type": "input_image",
            "image_url": data_url,
        })
    content.append({"type": "input_text", "text": prompt})

    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
    print(f"  Calling {model} with {len(images_to_send)} images...")

    # Use Responses API (not chat.completions)
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": content}],
    )

    response_text = response.output_text or ""
    print(f"  Response: {len(response_text)} chars")

    # Try to parse JSON from response
    try:
        # Find JSON in response (may be wrapped in markdown code blocks)
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            json_str = response_text
        return json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        return {"raw_response": response_text, "parse_error": True}


def scroll_and_screenshot(page: "Page", name: str, max_scrolls: int = DEFAULT_MAX_SCROLLS) -> list[dict]:
    """Scroll through page and capture screenshots."""
    screenshots = []
    viewport = page.viewport_size
    viewport_height = viewport["height"] if viewport else 900
    total_height = page.evaluate("document.body.scrollHeight")

    scroll_pos = 0
    idx = 0
    while scroll_pos < total_height and idx < max_scrolls:
        page.evaluate(f"window.scrollTo(0, {scroll_pos})")
        page.wait_for_timeout(500)

        screenshot = page.screenshot()
        screenshots.append({
            "name": f"{name}_scroll_{idx}",
            "media_type": "image/jpeg",
            "data": screenshot_to_base64(screenshot)
        })

        scroll_pos += viewport_height - 100
        idx += 1

    page.evaluate("window.scrollTo(0, 0)")
    return screenshots


def click_tabs_and_capture(page: "Page", tab_selectors: list[str]) -> list[dict]:
    """Click through tabs and screenshot each."""
    screenshots = []

    for selector in tab_selectors:
        try:
            tab = page.locator(selector).first
            if tab.count() == 0:
                continue
            tab.wait_for(state="visible", timeout=2000)
            tab_text = tab.inner_text()
            tab.click(timeout=5000)
            page.wait_for_timeout(1000)

            screenshot = page.screenshot(full_page=True)
            screenshots.append({
                "name": f"tab_{tab_text.strip().lower().replace(' ', '_')[:20]}",
                "media_type": "image/jpeg",
                "data": screenshot_to_base64(screenshot)
            })
        except Exception:
            pass

    return screenshots


def dismiss_consent_popup(page: "Page") -> None:
    """Dismiss cookie consent popups."""
    selectors = [
        "button:has-text('Accept')",
        "button:has-text('Accept All')",
        "button:has-text('I Accept')",
        "button:has-text('OK')",
        "button:has-text('Agree')",
        "#ccc-notify-accept",
        ".cookie-accept",
    ]

    for selector in selectors:
        try:
            btn = page.locator(selector).first
            if btn.count() > 0:
                btn.click(timeout=2000)
                page.wait_for_timeout(500)
                return
        except Exception:
            pass

    # Nuclear option: remove overlays via JS
    try:
        page.evaluate("""
            document.querySelectorAll('[class*="consent"], [class*="cookie"], [id*="consent"], [id*="cookie"]').forEach(el => {
                if (getComputedStyle(el).position === 'fixed' || getComputedStyle(el).position === 'sticky') {
                    el.remove();
                }
            });
            document.body.style.overflow = 'auto';
        """)
    except Exception:
        pass


def detect_council_system(url: str, page: "Page") -> str:
    """Detect which planning system the council uses."""
    url_lower = url.lower()

    if "publicaccess" in url_lower or "online-applications" in url_lower:
        return "idox"
    if "arcus" in url_lower:
        return "arcus"

    # Check page content
    try:
        html = page.content().lower()
        if "idox" in html or "public access" in html:
            return "idox"
        if "arcus" in html:
            return "arcus"
    except Exception:
        pass

    return "generic"


def scrape_planning_application(
    url: str,
    output_dir: Optional[Path] = None,
    custom_tab_selectors: Optional[list[str]] = None,
    save_screenshots: bool = False,
    proxy_url: Optional[str] = None,
) -> dict:
    """
    Scrape a planning application from any UK council portal.

    Args:
        url: Planning application URL
        output_dir: Where to save results (optional)
        custom_tab_selectors: Override tab selectors for specific council
        save_screenshots: Save raw screenshots to output_dir
        proxy_url: Optional proxy URL (e.g., from Apify proxy)

    Returns:
        dict with extracted planning data
    """
    if sync_playwright is None:
        raise ImportError("playwright not installed. Run: pip install playwright && playwright install chromium")

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    all_images = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Configure proxy at context level (required for authenticated proxies)
        proxy_config = None
        if proxy_url:
            # Parse proxy URL to extract credentials if present
            # Format: http://username:password@host:port
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            if parsed.username and parsed.password:
                # Authenticated proxy - extract credentials
                server_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 8000}"
                proxy_config = {
                    "server": server_url,
                    "username": parsed.username,
                    "password": parsed.password,
                }
                print(f"Proxy config: server={server_url}, username={parsed.username[:30]}...")
            else:
                # Simple proxy URL without credentials
                proxy_config = {"server": proxy_url}
                print(f"Proxy config: server={proxy_url[:60]}...")

        context = browser.new_context(
            viewport={"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
            proxy=proxy_config,
        )
        page = context.new_page()

        print(f"Loading {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)  # Give dynamic content time to load

        # Dismiss cookie popups
        dismiss_consent_popup(page)

        # Detect council system
        system = detect_council_system(url, page)
        print(f"Detected system: {system}")

        # Capture main page
        print("Capturing main page...")
        all_images.extend(scroll_and_screenshot(page, "main"))

        # Click through tabs
        tab_selectors = custom_tab_selectors or COUNCIL_TAB_SELECTORS.get(system, COUNCIL_TAB_SELECTORS["generic"])
        print(f"Capturing tabs ({len(tab_selectors)} selectors)...")
        all_images.extend(click_tabs_and_capture(page, tab_selectors))

        browser.close()

    # Save screenshots if requested
    if save_screenshots and output_dir:
        for i, img in enumerate(all_images):
            img_path = output_dir / f"{img['name']}.png"
            img_path.write_bytes(base64.b64decode(img['data']))

    # Extract with vision
    print(f"Extracting data from {len(all_images)} screenshots...")
    extracted = extract_with_vision(all_images, PLANNING_EXTRACTION_PROMPT)

    result = {
        "url": url,
        "council_system": system,
        "screenshots_captured": len(all_images),
        "data": extracted,
    }

    # Save results
    if output_dir:
        output_file = output_dir / "planning_data.json"
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Saved to {output_file}")

    return result


def scrape_planning_search(
    search_url: str,
    max_results: int = 20,
    output_dir: Optional[Path] = None,
    proxy_url: Optional[str] = None,
) -> list[dict]:
    """
    Scrape planning search results page to get list of applications.

    Args:
        search_url: Planning search results URL
        max_results: Maximum applications to extract
        output_dir: Where to save results
        proxy_url: Optional proxy URL (e.g., from Apify proxy)

    Returns:
        list of application summaries with links
    """
    if sync_playwright is None:
        raise ImportError("playwright not installed")

    all_images = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Configure proxy at context level
        proxy_config = {"server": proxy_url} if proxy_url else None
        if proxy_config:
            print(f"Proxy config: server={proxy_url[:60]}...")

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            proxy=proxy_config,
        )
        page = context.new_page()

        print(f"Loading search results: {search_url}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        dismiss_consent_popup(page)
        all_images.extend(scroll_and_screenshot(page, "search", max_scrolls=5))

        browser.close()

    # Simpler prompt for search results
    search_prompt = f"""Extract planning application summaries from these search results.

Return JSON array with up to {max_results} applications:
[
    {{
        "reference": "application reference",
        "address": "site address",
        "description": "short description",
        "status": "status if shown",
        "link": "URL or href to full application if visible"
    }}
]

Only extract applications visible in the screenshots. Return empty array if no results shown."""

    extracted = extract_with_vision(all_images, search_prompt)

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "search_results.json", "w") as f:
            json.dump(extracted, f, indent=2)

    return extracted if isinstance(extracted, list) else []


# Example council portal URLs for testing
EXAMPLE_COUNCILS = {
    "birmingham": "https://eplanning.birmingham.gov.uk/Northgate/PlanningExplorer/ApplicationSearch.aspx",
    "manchester": "https://pa.manchester.gov.uk/online-applications/",
    "leeds": "https://publicaccess.leeds.gov.uk/online-applications/",
    "bristol": "https://pa.bristol.gov.uk/online-applications/",
    "liverpool": "https://northgate.liverpool.gov.uk/PlanningExplorer17/ApplicationSearch.aspx",
    "sheffield": "https://planningapps.sheffield.gov.uk/online-applications/",
    "newcastle": "https://publicaccess.newcastle.gov.uk/online-applications/",
    "westminster": "https://idoxpa.westminster.gov.uk/online-applications/",
    "camden": "https://eplanning.camden.gov.uk/online-applications/",
    "islington": "https://planning.islington.gov.uk/online-applications/",
}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        # Default test URL (Birmingham planning)
        url = "https://eplanning.birmingham.gov.uk/Northgate/PlanningExplorer/Generic/StdDetails.aspx?PT=Planning%20Applications%20702702702702702702702702702702702On-702702702702702702702702702702Line&TYPE=PL/PL702702702702702702702702702702Full&PARAM0=681583&PARAM1=1&PARAM2=&CBESSION=0&XESSION=0"

    output_name = url.split("/")[-1].split("?")[0][:20] or "planning"
    result = scrape_planning_application(url, Path(f"./output/{output_name}"), save_screenshots=True)
    print(json.dumps(result, indent=2))
