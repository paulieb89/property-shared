"""
Vision-based property scraper using Playwright + OpenAI Vision.
Handles: tabs, scrolling, PDF downloads, dynamic content.
"""
import base64
import json
import os
import tempfile
from pathlib import Path
from openai import OpenAI
from playwright.sync_api import sync_playwright, Page

client = OpenAI()

# Generic prompt that works across property listing sites (auction, agency, commercial, residential)
GENERIC_PROPERTY_PROMPT = """You are a property data extraction expert. Analyze these screenshots from a property listing website and extract ALL visible information into structured JSON.

IMPORTANT: Extract EVERYTHING you can see. Be thorough. Include exact values with units.

{
    "source_type": "auction|agency|portal|developer",

    "listing": {
        "id": "lot number, property ID, reference number",
        "url": "if visible",
        "listed_date": "",
        "auction_date": "",
        "auction_venue": ""
    },

    "price": {
        "amount": "exact figure with currency symbol",
        "qualifier": "guide price, asking price, offers over, POA, etc.",
        "price_per_sqft": "",
        "rent_amount": "if let/investment",
        "yield": "percentage if shown"
    },

    "location": {
        "address": "full address as shown",
        "postcode": "",
        "area_description": "any location/area description text"
    },

    "property": {
        "type": "office, retail, industrial, residential, mixed-use, land, etc.",
        "tenure": "freehold, leasehold, etc.",
        "lease_length": "if leasehold",
        "size_sqft": "with original units if different",
        "size_sqm": "",
        "size_acres": "for land",
        "floors": "number of floors/storeys",
        "year_built": "",
        "condition": "",
        "epc_rating": ""
    },

    "accommodation": [
        {"floor": "ground/1st/2nd/etc", "description": "", "size": "", "use": "", "vacant": true/false}
    ],

    "tenancy": {
        "status": "vacant, let, part-let",
        "tenants": [
            {
                "name": "",
                "lease_start": "",
                "lease_end": "",
                "rent": "",
                "rent_review": "",
                "break_clause": ""
            }
        ],
        "total_rent": "",
        "wault": "weighted average unexpired lease term"
    },

    "planning": {
        "current_use_class": "",
        "permitted_development": "",
        "planning_history": "",
        "development_potential": ""
    },

    "investment": {
        "net_initial_yield": "",
        "reversionary_yield": "",
        "capital_value_per_sqft": "",
        "vat_status": ""
    },

    "features": ["list of bullet points/key features"],

    "description": "main property description text",

    "contact": {
        "agent_name": "",
        "company": "",
        "phone": "",
        "email": "",
        "address": ""
    },

    "images_count": "number of photos if shown",
    "documents": ["list of available documents: legal pack, particulars, etc."],

    "additional_info": "any other important info not captured above"
}

Rules:
- Use null for fields with no data
- Keep original formatting for addresses and descriptions
- Include ALL tenancy rows if there's a schedule
- Extract EVERY floor/unit from accommodation tables
- Preserve exact figures (don't round)
- Note any special conditions, fees, or warnings"""


def screenshot_to_base64(screenshot_bytes: bytes) -> str:
    return base64.b64encode(screenshot_bytes).decode()


def extract_with_vision(images: list[dict], prompt: str) -> str:
    """Send screenshots/PDFs to OpenAI vision for extraction."""
    content = []
    for img in images:
        data_url = f"data:{img['media_type']};base64,{img['data']}"
        content.append({
            "type": "input_image",
            "image_url": data_url
        })
    content.append({"type": "input_text", "text": prompt})

    response = client.responses.create(
        model=os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini"),
        input=[{"role": "user", "content": content}],
        max_output_tokens=8192
    )
    return response.output_text


def scroll_and_screenshot(page: Page, name: str) -> list[dict]:
    """Scroll through page and capture screenshots."""
    screenshots = []
    viewport_height = page.viewport_size["height"]
    total_height = page.evaluate("document.body.scrollHeight")

    scroll_pos = 0
    idx = 0
    while scroll_pos < total_height:
        page.evaluate(f"window.scrollTo(0, {scroll_pos})")
        page.wait_for_timeout(500)  # Let content load

        screenshot = page.screenshot()
        screenshots.append({
            "name": f"{name}_scroll_{idx}",
            "media_type": "image/png",
            "data": screenshot_to_base64(screenshot)
        })

        scroll_pos += viewport_height - 100  # Overlap for continuity
        idx += 1

    # Return to top
    page.evaluate("window.scrollTo(0, 0)")
    return screenshots


def click_tabs_and_capture(page: Page, tab_selectors: list[str]) -> list[dict]:
    """Click through tabs and screenshot each."""
    screenshots = []

    for selector in tab_selectors:
        try:
            tab = page.locator(selector).first
            tab.wait_for(state="visible", timeout=2000)
            tab_text = tab.inner_text()
            tab.click(timeout=5000)
            page.wait_for_timeout(1000)  # Wait for tab content

            # Screenshot the tab content
            screenshot = page.screenshot(full_page=True)
            screenshots.append({
                "name": f"tab_{tab_text.strip().lower().replace(' ', '_')}",
                "media_type": "image/png",
                "data": screenshot_to_base64(screenshot)
            })
            print(f"  Captured tab: {tab_text.strip()}")
        except Exception as e:
            print(f"  Tab {selector} skipped: {type(e).__name__}")

    return screenshots


def download_pdf_and_capture(page: Page, button_selector: str, download_path: Path) -> dict | None:
    """Click download button, save PDF, convert first pages to images."""
    try:
        btn = page.locator(button_selector).first
        btn.wait_for(state="visible", timeout=3000)
        with page.expect_download(timeout=15000) as download_info:
            btn.click(timeout=5000)
        download = download_info.value
        print(f"  Downloaded: {download.suggested_filename}")

        pdf_path = download_path / download.suggested_filename
        download.save_as(pdf_path)

        # For PDF extraction, we can either:
        # 1. Use pdf2image to convert pages to images
        # 2. Use PyMuPDF to extract text directly
        # 3. Just pass PDF path for separate processing

        return {
            "name": download.suggested_filename,
            "path": str(pdf_path),
            "type": "pdf"
        }
    except Exception as e:
        print(f"Download failed: {e}")
        return None


def dismiss_consent_popup(page: Page) -> None:
    """Dismiss cookie consent popups (Quantcast CMP and others)."""
    try:
        # Try Quantcast "Agree" button first
        agree_btn = page.locator("button.css-47sehv, button:has-text('Agree'), button:has-text('AGREE')")
        if agree_btn.count() > 0:
            agree_btn.first.click(timeout=3000)
            page.wait_for_timeout(500)
            return
    except:
        pass

    try:
        # Try generic accept buttons
        accept_btn = page.locator("button:has-text('Accept All'), button:has-text('Accept all'), button:has-text('Accept')")
        if accept_btn.count() > 0:
            accept_btn.first.click(timeout=3000)
            page.wait_for_timeout(500)
            return
    except:
        pass

    # Nuclear option: remove the overlay via JavaScript
    try:
        page.evaluate("""
            // Remove Quantcast CMP
            const qcContainer = document.getElementById('qc-cmp2-container');
            if (qcContainer) qcContainer.remove();

            // Remove any fixed/sticky overlays
            document.querySelectorAll('[class*="consent"], [class*="cookie"], [id*="consent"], [id*="cookie"]').forEach(el => {
                if (getComputedStyle(el).position === 'fixed' || getComputedStyle(el).position === 'sticky') {
                    el.remove();
                }
            });

            // Re-enable scrolling on body
            document.body.style.overflow = 'auto';
        """)
        page.wait_for_timeout(300)
    except:
        pass


def scrape_allsop_lot(url: str, output_dir: Path) -> dict:
    """Scrape an Allsop auction lot with full tab/scroll/download support."""

    output_dir.mkdir(parents=True, exist_ok=True)
    all_images = []
    downloaded_files = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True
        )
        page = context.new_page()

        print(f"Loading {url}")
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000)  # Extra wait for dynamic content

        # Dismiss cookie consent popup (Quantcast CMP)
        dismiss_consent_popup(page)

        # 1. Capture main page with scroll
        print("Capturing main page...")
        all_images.extend(scroll_and_screenshot(page, "main"))

        # 2. Click through content tabs (Allsop uses data-tab attributes)
        print("Capturing tabs...")
        tab_selectors = [
            "[data-tab='description']",
            "[data-tab='tenancy']",  # "Accommodation and Tenancy Schedule"
            "[data-tab='map']",
            "[data-tab='street']",   # Street View
            "[data-tab='floorplan']",
            "[data-tab='epc']",
        ]
        all_images.extend(click_tabs_and_capture(page, tab_selectors))

        # 3. Download PDFs (Particulars, Legal Pack, etc.)
        print("Downloading documents...")
        download_buttons = [
            "button:has-text('PARTICULARS OF SALE')",
            "button:has-text('LEGAL PACK')",
            "a:has-text('Download PDF')",
        ]
        for btn in download_buttons:
            pdf = download_pdf_and_capture(page, btn, output_dir)
            if pdf:
                downloaded_files.append(pdf)

        browser.close()

    # 4. Extract data using vision
    print(f"Extracting data from {len(all_images)} screenshots...")

    extraction_prompt = GENERIC_PROPERTY_PROMPT

    extracted_data = extract_with_vision(all_images, extraction_prompt)

    # Save results
    result = {
        "url": url,
        "screenshots_captured": len(all_images),
        "pdfs_downloaded": [f["name"] for f in downloaded_files],
        "extracted_data": extracted_data
    }

    output_file = output_dir / "extracted_data.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Saved to {output_file}")
    return result


def scrape_rightmove_property(url: str, output_dir: Path) -> dict:
    """Scrape a Rightmove property listing."""

    output_dir.mkdir(parents=True, exist_ok=True)
    all_images = []

    with sync_playwright() as p:
        # Use stealth settings for Rightmove
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        print(f"Loading {url}")
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        # Handle cookie consent
        try:
            page.locator("button:has-text('Accept')").click(timeout=3000)
        except:
            pass

        # Capture with scroll
        all_images.extend(scroll_and_screenshot(page, "main"))

        # Click through image gallery
        try:
            page.locator(".gallery, [data-test='gallery']").first.click()
            page.wait_for_timeout(1000)
            screenshot = page.screenshot(full_page=True)
            all_images.append({
                "name": "gallery",
                "media_type": "image/png",
                "data": screenshot_to_base64(screenshot)
            })
        except:
            pass

        browser.close()

    # Extract with vision (same generic prompt works for any site)
    extracted_data = extract_with_vision(all_images, GENERIC_PROPERTY_PROMPT)

    result = {
        "url": url,
        "screenshots_captured": len(all_images),
        "extracted_data": extracted_data
    }

    output_file = output_dir / "extracted_data.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    return result


def scrape_generic(url: str, output_dir: Path, click_selectors: list[str] = None) -> dict:
    """
    Generic scraper that works on any property site.

    Args:
        url: Property listing URL
        output_dir: Where to save results
        click_selectors: Optional list of CSS selectors to click (tabs, expandable sections)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    all_images = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True
        )
        page = context.new_page()

        print(f"Loading {url}")
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)

        # Dismiss any consent popups
        dismiss_consent_popup(page)

        # Capture main page with full scroll
        print("Capturing main page...")
        all_images.extend(scroll_and_screenshot(page, "main"))

        # Click through any provided selectors (tabs, accordions, etc.)
        if click_selectors and len(click_selectors) > 0:
            print("Capturing additional sections...")
            all_images.extend(click_tabs_and_capture(page, click_selectors))

        browser.close()

    # Extract with generic prompt
    print(f"Extracting data from {len(all_images)} screenshots...")
    extracted_data = extract_with_vision(all_images, GENERIC_PROPERTY_PROMPT)

    result = {
        "url": url,
        "screenshots_captured": len(all_images),
        "extracted_data": extracted_data
    }

    output_file = output_dir / "extracted_data.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Saved to {output_file}")
    return result


if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Default: Allsop auction lot
    if len(sys.argv) > 1:
        url = sys.argv[1]
        output_name = url.split("/")[-1].split("?")[0] or "property"
    else:
        url = "https://www.allsop.co.uk/lot-overview/freehold-officemedical-investment-and-residential-development-opportunity-in-kings-lynn/c250611-010"
        output_name = "allsop"

    # Use site-specific scraper if recognized, otherwise generic
    if "allsop.co.uk" in url:
        result = scrape_allsop_lot(url, Path(f"./output/{output_name}"))
    elif "rightmove.co.uk" in url:
        result = scrape_rightmove_property(url, Path(f"./output/{output_name}"))
    else:
        # Generic scraper - just scroll and capture
        result = scrape_generic(url, Path(f"./output/{output_name}"))

    print(json.dumps(result, indent=2))
