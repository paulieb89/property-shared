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
        "button:has-text('AGREE')",
        "#ccc-notify-accept",
        ".cookie-accept",
        # Quantcast CMP (common on UK sites)
        "button.css-47sehv",
        "#qc-cmp2-ui button[mode='primary']",
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
            // Remove Quantcast CMP specifically
            const qcContainer = document.getElementById('qc-cmp2-container');
            if (qcContainer) qcContainer.remove();

            // Remove Agile Applications cookie overlay (Islington etc.)
            document.querySelectorAll('.sas-cookie-consent-overlay, .sas-cookie-consent').forEach(el => el.remove());

            // Remove generic consent/cookie overlays
            document.querySelectorAll('[class*="consent"], [class*="cookie"], [id*="consent"], [id*="cookie"]').forEach(el => {
                if (getComputedStyle(el).position === 'fixed' || getComputedStyle(el).position === 'sticky') {
                    el.remove();
                }
            });
            document.body.style.overflow = 'auto';
        """)
    except Exception:
        pass


def dismiss_blocking_elements(page: "Page") -> None:
    """Dismiss all common blocking elements on council sites.

    Handles:
    - Cookie consent popups
    - Survey/feedback modals
    - Announcement banners
    - Chat widgets
    - Loading overlays
    - Newsletter popups
    """
    # First handle consent popups
    dismiss_consent_popup(page)

    # Survey/feedback popup buttons to click
    survey_dismiss_selectors = [
        "button:has-text('No thanks')",
        "button:has-text('No, thanks')",
        "button:has-text('Not now')",
        "button:has-text('Maybe later')",
        "button:has-text('Close')",
        "button:has-text('Dismiss')",
        "button:has-text('Skip')",
        "[aria-label='Close']",
        "[aria-label='Dismiss']",
        ".modal-close",
        ".popup-close",
        ".survey-close",
        ".feedback-close",
    ]

    for selector in survey_dismiss_selectors:
        try:
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible():
                btn.click(timeout=1000)
                page.wait_for_timeout(300)
        except Exception:
            pass

    # Nuclear option: Remove blocking elements via JavaScript
    try:
        page.evaluate("""
            // Remove survey/feedback widgets
            const surveySelectors = [
                '[class*="survey"]',
                '[class*="feedback"]',
                '[class*="hotjar"]',
                '[class*="qualtrics"]',
                '[id*="survey"]',
                '[id*="feedback"]',
                '[id*="hotjar"]',
            ];
            surveySelectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => el.remove());
            });

            // Remove chat widgets
            const chatSelectors = [
                '[class*="zendesk"]',
                '[class*="intercom"]',
                '[class*="livechat"]',
                '[class*="chat-widget"]',
                '[id*="zendesk"]',
                '[id*="intercom"]',
                '[id*="livechat"]',
                'iframe[title*="chat"]',
                'iframe[title*="Chat"]',
            ];
            chatSelectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => el.remove());
            });

            // Remove announcement/alert banners (fixed position)
            const bannerSelectors = [
                '[class*="announcement"]',
                '[class*="alert-banner"]',
                '[class*="notice-banner"]',
                '[class*="site-banner"]',
                '[role="alert"]',
            ];
            bannerSelectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => {
                    const style = getComputedStyle(el);
                    if (style.position === 'fixed' || style.position === 'sticky') {
                        el.remove();
                    }
                });
            });

            // Remove loading overlays that might be stuck
            const loadingSelectors = [
                '[class*="loading-overlay"]',
                '[class*="spinner-overlay"]',
                '[class*="page-loading"]',
                '.overlay:not([class*="content"])',
            ];
            loadingSelectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => {
                    const style = getComputedStyle(el);
                    if (style.position === 'fixed' && style.zIndex > 100) {
                        el.remove();
                    }
                });
            });

            // Remove modal backdrops
            document.querySelectorAll('.modal-backdrop, .overlay-backdrop').forEach(el => el.remove());

            // Ensure body is scrollable
            document.body.style.overflow = 'auto';
            document.documentElement.style.overflow = 'auto';

            // Remove any blur effects on main content
            const main = document.querySelector('main, #main, .main-content, #content');
            if (main) {
                main.style.filter = 'none';
                main.style.pointerEvents = 'auto';
            }
        """)
    except Exception:
        pass


def detect_hard_blockers(page: "Page") -> Optional[str]:
    """Detect blocking elements we cannot automatically bypass.

    Returns:
        String describing the blocker type, or None if no hard blocker detected.
    """
    try:
        html = page.content().lower()

        # reCAPTCHA - cannot be bypassed automatically
        if "recaptcha" in html or "g-recaptcha" in html:
            return "reCAPTCHA"

        # hCaptcha
        if "hcaptcha" in html or "h-captcha" in html:
            return "hCaptcha"

        # Cloudflare challenge
        if "cloudflare" in html and ("challenge" in html or "ray id" in html):
            return "Cloudflare challenge"

        # Generic CAPTCHA
        if "captcha" in html and ("verify" in html or "human" in html):
            return "CAPTCHA verification"

        # Bot detection messages
        bot_indicators = [
            "detected unusual traffic",
            "please verify you are human",
            "access denied",
            "you have been blocked",
            "automated access",
            "bot detection",
        ]
        for indicator in bot_indicators:
            if indicator in html:
                return f"Bot detection: {indicator}"

        # Check for challenge iframes
        captcha_iframe = page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[title*='challenge']")
        if captcha_iframe.count() > 0:
            return "CAPTCHA iframe detected"

    except Exception:
        pass

    return None


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


def _get_proxy_config() -> Optional[dict]:
    """Get proxy configuration from environment."""
    proxy_url = os.getenv("PLAYWRIGHT_PROXY_URL")
    if not proxy_url:
        return None

    # Support full URL format: http://user:pass@host:port
    return {"server": proxy_url}


def probe_connectivity(
    url: str,
    timeout_ms: int = 30000,
    use_proxy: bool = True,
) -> dict:
    """
    Quick connectivity probe to diagnose blocking/access issues.

    Returns screenshot and HTML on success or failure for diagnosis.
    """
    if sync_playwright is None:
        raise ImportError("playwright not installed")

    proxy_config = _get_proxy_config() if use_proxy else None

    result = {
        "url": url,
        "success": False,
        "page_title": None,
        "status_code": None,
        "load_time_ms": None,
        "screenshot_base64": None,
        "html_snippet": None,
        "blocking_indicators": [],
        "error": None,
        "proxy_used": proxy_config["server"] if proxy_config else None,
    }

    import time
    start = time.time()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                proxy=proxy_config,
            )
            page = context.new_page()

            # Capture response status
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            result["status_code"] = response.status if response else None
            result["load_time_ms"] = int((time.time() - start) * 1000)

            # Wait a bit for JS
            page.wait_for_timeout(2000)

            # Capture page info
            result["page_title"] = page.title()

            # Get HTML snippet (first 5000 chars)
            html = page.content()
            result["html_snippet"] = html[:5000] if html else None

            # Take screenshot
            screenshot = page.screenshot()
            result["screenshot_base64"] = base64.b64encode(screenshot).decode()

            # Check for blocking indicators
            html_lower = html.lower() if html else ""
            title_lower = result["page_title"].lower() if result["page_title"] else ""

            blocking_checks = [
                ("captcha" in html_lower or "recaptcha" in html_lower, "CAPTCHA detected"),
                ("blocked" in title_lower or "blocked" in html_lower[:500], "Blocked message detected"),
                ("access denied" in html_lower[:500], "Access denied"),
                ("403" in title_lower or "forbidden" in html_lower[:500], "403 Forbidden"),
                ("cloudflare" in html_lower, "Cloudflare protection"),
                ("just a moment" in html_lower, "Cloudflare challenge page"),
                ("verify you are human" in html_lower, "Human verification required"),
                ("bot" in html_lower[:1000] and "detect" in html_lower[:1000], "Bot detection"),
                (result["status_code"] == 403, "HTTP 403 status"),
                (result["status_code"] == 429, "HTTP 429 rate limited"),
                (result["status_code"] and result["status_code"] >= 500, f"HTTP {result['status_code']} server error"),
            ]

            for check, message in blocking_checks:
                if check:
                    result["blocking_indicators"].append(message)

            # Check if we actually got planning content
            planning_indicators = [
                "planning" in html_lower,
                "application" in html_lower,
                "reference" in html_lower,
                "applicant" in html_lower,
            ]
            if sum(planning_indicators) >= 2:
                result["success"] = True
            elif not result["blocking_indicators"]:
                result["blocking_indicators"].append("No planning content found - may be blocked or wrong URL")

            browser.close()

    except Exception as e:
        result["error"] = str(e)
        result["load_time_ms"] = int((time.time() - start) * 1000)
        if "timeout" in str(e).lower():
            result["blocking_indicators"].append("Page load timeout - likely blocked or very slow")

    return result


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
        proxy_url: Optional proxy URL (e.g., from Apify proxy or PLAYWRIGHT_PROXY_URL env)

    Returns:
        dict with extracted planning data
    """
    if sync_playwright is None:
        raise ImportError("playwright not installed. Run: pip install playwright && playwright install chromium")

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    # Get proxy from parameter or environment
    proxy_url = proxy_url or os.getenv("PLAYWRIGHT_PROXY_URL")
    proxy_config = {"server": proxy_url} if proxy_url else None

    all_images = []

    with sync_playwright() as p:
        # Configure proxy if provided
        if proxy_config:
            print(f"Using proxy: {proxy_url[:60] if proxy_url else 'none'}...")
            browser = p.chromium.launch(headless=True)
        else:
            browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            viewport={"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
            proxy=proxy_config,
        )
        page = context.new_page()

        print(f"Loading {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)  # Give dynamic content time to load

        # Dismiss blocking elements (cookies, surveys, chat widgets, etc.)
        dismiss_blocking_elements(page)

        # Check for hard blockers we can't bypass
        hard_blocker = detect_hard_blockers(page)
        if hard_blocker:
            print(f"WARNING: Hard blocker detected: {hard_blocker}")

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


def _vision_find_form_action(images: list[dict], postcode: str) -> dict:
    """Ask Vision how to fill and submit the search form."""
    prompt = f"""Analyze this planning portal search page. I need to search for postcode "{postcode}".

Return JSON with instructions:
{{
    "has_search_form": true/false,
    "has_results": true/false,
    "search_field_placeholder": "text shown in search input if visible",
    "search_button_text": "text on the search button (e.g., 'Search', 'Find', 'Go')",
    "field_selector_hint": "CSS-like description of the input field (e.g., 'input near Search button', 'text input below postcode label')",
    "notes": "any other observations about the page"
}}

If the page already shows search results (list of applications), set has_results=true.
If it shows a search form, set has_search_form=true and describe how to fill it."""

    return extract_with_vision(images, prompt, max_images=2)


def search_planning_by_postcode(
    portal_url: str,
    postcode: str,
    max_results: int = 20,
    output_dir: Optional[Path] = None,
    system: Optional[str] = None,
) -> list[dict]:
    """
    Search a planning portal by postcode using vision-guided form filling.

    This function can handle both:
    - Pages that show a search form (will fill and submit)
    - Pages that already show results (will extract directly)

    Args:
        portal_url: Planning portal search page URL
        postcode: UK postcode to search for
        max_results: Maximum applications to extract
        output_dir: Where to save results
        system: Optional system type hint (idox, lar, agile, northgate, etc.)

    Returns:
        list of application summaries with links
    """
    if sync_playwright is None:
        raise ImportError("playwright not installed")

    all_images = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        print(f"Loading planning portal: {portal_url}")
        page.goto(portal_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        dismiss_blocking_elements(page)

        # Take initial screenshot to understand the page
        initial_screenshot = [{
            "name": "initial",
            "media_type": "image/jpeg",
            "data": screenshot_to_base64(page.screenshot())
        }]

        # Ask Vision what to do
        print("Analyzing page with Vision...")
        form_analysis = _vision_find_form_action(initial_screenshot, postcode)
        print(f"  Analysis: {form_analysis}")

        # Check if we need to fill a form
        if form_analysis.get("has_search_form") and not form_analysis.get("has_results"):
            print(f"Filling search form with postcode: {postcode}")

            # Priority order: try postcode-specific fields before generic fallback
            # This handles LAR, Northgate, Agile and custom multi-field forms
            search_filled = False
            postcode_field_selectors = [
                # Explicit postcode fields (LAR systems like Liverpool/Hackney, Northgate)
                "input[name*='postcode' i]",
                "input[id*='postcode' i]",
                "input[id*='Postcode']",
                "input[placeholder*='Postcode']",
                # Search-specific inputs (Agile platform like Islington)
                "input[name='searchInput']",
                "input[type='search']",
                # Idox-specific selectors
                "input[name='searchCriteria']",
                "input#simpleSearchString",
                "input.search-input",
                # Generic fallback (last resort - first text input)
                "input[type='text']",
            ]

            for selector in postcode_field_selectors:
                try:
                    field = page.locator(selector).first
                    if field.count() > 0 and field.is_visible():
                        field.fill(postcode)
                        search_filled = True
                        print(f"  Filled field: {selector}")
                        break
                except Exception:
                    continue

            # Click search button
            if search_filled:
                # Dismiss any late-loading overlays (SPAs like Agile load consent after initial render)
                dismiss_blocking_elements(page)
                button_clicked = False
                button_selectors = [
                    "button:has-text('Search')",
                    "button:has-text('Quick search')",
                    "button[type='search']",
                    "input[type='submit'][value*='Search']",
                    "input[value='Search']",
                    "input[type='submit']",
                    "button[type='submit']",
                    ".button:has-text('Search')",
                    "a:has-text('Search')",
                    "button:has-text('Find')",
                    "button:has-text('Go')",
                ]

                for selector in button_selectors:
                    try:
                        btn = page.locator(selector).first
                        if btn.count() > 0 and btn.is_visible():
                            btn.click()
                            button_clicked = True
                            print(f"  Clicked: {selector}")
                            break
                    except Exception:
                        continue

                if button_clicked:
                    # Wait for results to load
                    print("Waiting for results...")
                    page.wait_for_timeout(3000)
                    # Wait for either results table or "no results" message
                    try:
                        page.wait_for_selector("table, .searchresults, .results, .no-results", timeout=10000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1000)

        # Now capture results
        print("Capturing results...")
        all_images.extend(scroll_and_screenshot(page, "results", max_scrolls=5))

        # Extract links from the page before closing browser
        print("Extracting application links...")
        page_links = []  # List of (text, href) tuples
        try:
            # Get all links that look like application detail links
            links = page.locator("a[href*='applicationDetails'], a[href*='keyVal'], a[href*='ApplicationNumber'], a[href*='refval']").all()
            for link in links:
                try:
                    href = link.get_attribute("href")
                    text = link.inner_text().strip()
                    if href:
                        page_links.append((text, href))
                except Exception:
                    continue
            print(f"  Found {len(page_links)} application links")
            if page_links:
                print(f"  Sample: {page_links[0]}")
        except Exception as e:
            print(f"  Could not extract links: {e}")

        # Get base URL for relative links
        base_url = page.url.rsplit('/', 1)[0] if '/' in page.url else page.url

        browser.close()

    # Extract applications from results
    search_prompt = f"""Extract planning application summaries from these search results.

Return JSON array with up to {max_results} applications:
[
    {{
        "reference": "application reference (e.g., 12/02736/HOARD)",
        "address": "site address",
        "description": "short description",
        "status": "status if shown (Decided, Pending, etc.)"
    }}
]

Only extract applications visible in the screenshots. Return empty array if no results shown or if this is still showing a search form."""

    extracted = extract_with_vision(all_images, search_prompt)

    # Match extracted applications with links we found
    if isinstance(extracted, list):
        import re
        for idx, app in enumerate(extracted):
            ref = app.get("reference", "")
            link = None

            # Try to find matching link by:
            # 1. Exact reference match in link text
            # 2. Reference appears in link text
            # 3. Reference appears in href (URL encoded)
            # 4. Position-based match (nth application = nth link)
            for link_text, href in page_links:
                # Normalize reference for comparison
                ref_normalized = ref.replace("/", "").replace(" ", "").upper()
                text_normalized = link_text.replace("/", "").replace(" ", "").upper()

                if ref in link_text or ref_normalized in text_normalized:
                    link = href
                    break
                # Check if reference is in the URL (often URL-encoded)
                if ref.replace("/", "%2F") in href or ref.replace("/", "") in href:
                    link = href
                    break

            # Fallback: match by position if we have same number of links as results
            if not link and idx < len(page_links):
                link = page_links[idx][1]

            # Make absolute URL if relative
            if link:
                if link.startswith("/"):
                    link = base_url.split("/online-applications")[0] + link
                elif not link.startswith("http"):
                    link = base_url + "/" + link
            app["link"] = link

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "search_results.json", "w") as f:
            json.dump(extracted, f, indent=2)

    return extracted if isinstance(extracted, list) else []


def scrape_planning_search(
    search_url: str,
    max_results: int = 20,
    output_dir: Optional[Path] = None,
) -> list[dict]:
    """
    Scrape planning search results page to get list of applications.

    Note: This assumes the URL already shows results. For form-based search,
    use search_planning_by_postcode() instead.

    Args:
        search_url: Planning search results URL
        max_results: Maximum applications to extract
        output_dir: Where to save results

    Returns:
        list of application summaries with links
    """
    if sync_playwright is None:
        raise ImportError("playwright not installed")

    all_images = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        print(f"Loading search results: {search_url}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        dismiss_blocking_elements(page)
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
