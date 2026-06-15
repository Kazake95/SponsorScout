"""
Lightweight page fetcher used by verification and career-page scanning.

It prefers a normal HTTP fetch, then optionally upgrades to a rendered
browser snapshot via Playwright for JavaScript-heavy pages.
"""
from __future__ import annotations

import json
import logging
import random
import re
import sys
from typing import Any
from urllib.parse import urlparse

from sponsorscout.core.http_client import http_session, is_bot_blocked

logger = logging.getLogger(__name__)

_DYNAMIC_HINTS = (
    "__NEXT_DATA__",
    "__NUXT__",
    "__INITIAL_DATA__",
    "__PRELOADED_STATE__",
    "window.__DATA__",
    "window.__APP__",
    'id="root"',
    'id="app"',
    "ng-version",
    "data-reactroot",
    "application/ld+json",
)

# Job listing CSS selectors to wait for — common across career portals
_JOB_LISTING_SELECTORS = (
    "a[href*='/jobs/']",
    "a[href*='/careers/']",
    "a[href*='/position/']",
    "a[href*='/positions/']",
    "a[href*='/opportunity/']",
    "a[href*='/job/']",
    "[data-job-id]",
    "[data-position-id]",
    '[class*="job-card"]',
    '[class*="JobCard"]',
    '[class*="job-listing"]',
    '[class*="job-item"]',
    '[class*="position-card"]',
    '[class*="vacancy-item"]',
)


def _looks_dynamic(html: str) -> bool:
    html = html or ""
    if len(html) < 5000:
        return True
    low = html.lower()
    return any(hint.lower() in low for hint in _DYNAMIC_HINTS)


def _looks_like_careers_url(url: str) -> bool:
    """Heuristic: official career portals usually contain one of these paths."""
    try:
        parsed = urlparse(url or "")
    except Exception:
        return False
    path = (parsed.path or "").lower()
    if not path:
        return False
    return any(part in path for part in ("career", "careers", "jobs", "join", "open-roles", "open-positions", "vacanc", "opportunit"))


def _extract_title(html: str) -> str:
    if "<title" not in html.lower():
        return ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _playwright_available() -> bool:
    """Check if Playwright can be imported, with one-time warning."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _apply_stealth_patches(page) -> None:
    """Apply anti-detection patches to the Playwright page.

    Modern bot protection (Cloudflare, DataDome, Akamai) checks for:
      - navigator.webdriver flag
      - Missing Chrome runtime/plugins
      - Missing languages and other navigator properties
    """
    page.add_init_script("""
        // Override navigator.webdriver (the most commonly checked property)
        Object.defineProperty(navigator, 'webdriver', {get: () => false});

        // Override plugins to appear as a real Chrome browser
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' },
            ]
        });

        // Override languages for realistic fingerprint
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

        // Add chrome.runtime to simulate real Chrome
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: { isInstalled: false },
        };

        // Override permissions query to hide automation context
        if (window.Permissions && window.Permissions.prototype) {
            const origQuery = Permissions.prototype.query;
            Permissions.prototype.query = function(desc) {
                if (desc && desc.name === 'notifications') {
                    return Promise.resolve({state: 'prompt'});
                }
                return origQuery.call(this, desc);
            };
        }

        // Remove webdriver attributes from document
        Object.defineProperty(document, 'hidden', {get: () => false});
        Object.defineProperty(document, 'visibilityState', {get: () => 'visible'});
    """)


def _wait_for_job_elements(page, timeout_ms: int = 8000) -> bool:
    """Wait for job listing elements to appear on the page.

    Returns True if any job-like elements were found within the timeout.
    """
    for selector in _JOB_LISTING_SELECTORS:
        try:
            el = page.wait_for_selector(selector, timeout=timeout_ms)
            if el:
                logger.debug("Found job element with selector: %s", selector)
                return True
        except Exception:
            continue
    return False


# URL fragments that suggest an XHR/fetch response carries job-listing data
# (used to decide which network responses are worth capturing as JSON).
_JOB_API_URL_HINTS = re.compile(
    r"(job|career|position|vacanc|opening|role|posting|requisition|"
    r"graphql|search|listing|board)",
    re.I,
)

# Buttons/links that trigger more results to load on infinite-scroll /
# paginated SPA job boards.
_LOAD_MORE_TEXT_RE = re.compile(
    r"^(load more|show more|more jobs|more roles|more positions|more results|"
    r"view more|see more|see all|next)\b",
    re.I,
)


def _register_json_capture(page, max_items: int = 25, max_bytes: int = 500_000) -> list:
    """Attach a response listener that captures small-ish JSON API payloads.

    Many SPA career portals (Bolt, Shopify, custom React/Vue boards) never
    inline job data into the HTML/DOM at all — they fetch it from a JSON or
    GraphQL endpoint after the page loads. Capturing those response bodies
    lets ``portal_search`` run the same job-extraction heuristics against
    them even when the rendered DOM has nothing useful.

    Returns a list that is appended to in place as matching responses arrive.
    """
    captured: list = []

    def _on_response(response):
        try:
            if len(captured) >= max_items:
                return
            url = response.url or ""
            if not _JOB_API_URL_HINTS.search(url):
                return
            ctype = (response.headers or {}).get("content-type", "")
            if "json" not in ctype.lower():
                return
            body = response.body()
            if not body or len(body) > max_bytes:
                return
            blob = json.loads(body.decode("utf-8", errors="ignore"))
            captured.append(blob)
        except Exception:
            # Response bodies for redirected/aborted/streaming requests can
            # raise — never let capture failures break the main render.
            return

    try:
        page.on("response", _on_response)
    except Exception:
        pass

    return captured


def _scroll_and_expand(page, max_rounds: int = 8) -> None:
    """Scroll through the page and click "load more"-style controls.

    Repeats until the document height stops growing (or *max_rounds* is
    reached), which handles both infinite-scroll job boards and ones gated
    behind a "Load more" / "Show more jobs" button.
    """
    try:
        last_height = page.evaluate("document.body.scrollHeight")
    except Exception:
        return

    for _ in range(max_rounds):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            break
        page.wait_for_timeout(700)

        # Try clicking a "load more" style button/link if one is visible.
        try:
            for el in page.locator("button, a, [role='button']").all()[:60]:
                try:
                    text = (el.inner_text(timeout=200) or "").strip()
                except Exception:
                    continue
                if text and _LOAD_MORE_TEXT_RE.match(text):
                    try:
                        if el.is_visible():
                            el.click(timeout=1000)
                            page.wait_for_timeout(800)
                    except Exception:
                        pass
                    break
        except Exception:
            pass

        try:
            new_height = page.evaluate("document.body.scrollHeight")
        except Exception:
            break
        if new_height <= last_height:
            break
        last_height = new_height

    try:
        page.evaluate("window.scrollTo(0, 0);")
        page.wait_for_timeout(400)
    except Exception:
        pass


def _render_with_playwright(url: str, wait_ms: int = 2500, timeout: int = 30) -> dict[str, Any] | None:
    """Return a rendered snapshot using Playwright, or None if unavailable.

    Uses stealth patches to bypass common bot detection systems
    (Cloudflare, DataDome, PerimeterX, etc.).
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
    except Exception as exc:
        logger.warning(
            "Playwright is not available (%s); SPA / JS-rendered career "
            "pages will return 0 jobs. Install with: pip install playwright "
            "&& playwright install chromium",
            exc.__class__.__name__,
        )
        return None

    browser = None
    try:
        with sync_playwright() as p:
            # Anti-detection launch args
            launch_args = [
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-web-security",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-pings",
            ]
            if sys.platform.startswith("linux"):
                launch_args.extend(["--no-sandbox", "--disable-setuid-sandbox"])

            browser = p.chromium.launch(
                headless=True,
                args=launch_args,
            )

            # Realistic viewport with common variation
            viewport_width = random.choice([1366, 1440, 1536, 1920])
            viewport_height = random.choice([768, 900, 1080])
            page = browser.new_page(
                viewport={"width": viewport_width, "height": viewport_height},
                locale="en-US",
                timezone_id="America/New_York",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    f"Chrome/{random.choice(['120', '121', '122', '123', '124', '125', '126', '127', '128', '129', '130', '131'])}.0.0.0 "
                    "Safari/537.36"
                ),
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Sec-CH-UA": f'"Chromium";v="{random.choice(["120", "122", "124", "126", "128", "130", "131"])}", "Google Chrome";v="{random.choice(["120", "122", "124", "126", "128", "130", "131"])}"',
                    "Sec-CH-UA-Mobile": "?0",
                    "Sec-CH-UA-Platform": '"Windows"',
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                },
            )

            # Apply stealth patches to hide automation
            _apply_stealth_patches(page)

            # Start capturing job-like JSON/XHR responses before navigation,
            # so we don't miss anything fired during initial page load.
            captured_json = _register_json_capture(page)

            # Navigate with realistic timing
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

            # Randomize initial wait to appear more human-like
            initial_wait = max(wait_ms, random.randint(1500, 3000))
            page.wait_for_timeout(initial_wait)

            # Wait for job listing elements to appear (with fallback)
            found_jobs = _wait_for_job_elements(page, timeout_ms=min(timeout * 1000 // 2, 5000))

            if not found_jobs:
                # Trigger lazy-loaded listings / infinite scroll content, and
                # click through any "load more"-style controls.
                _scroll_and_expand(page)

                # Check again for job elements after scroll/expand
                found_jobs = _wait_for_job_elements(page, timeout_ms=3000)

            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

            # Give any in-flight XHR/fetch job-data requests a moment to land.
            page.wait_for_timeout(500)

            html = page.content() or ""

            # Check if we got a bot challenge page
            if is_bot_blocked(html):
                logger.warning("Bot challenge detected on %s — page may be blocked", url)

            return {
                "url": page.url or url,
                "title": page.title() or _extract_title(html),
                "html": html,
                "status": 200,
                "rendered_by": "playwright",
                "bot_blocked": is_bot_blocked(html),
                "found_jobs": found_jobs,
                "captured_json": captured_json,
            }
    except Exception as exc:
        logger.debug("Playwright render failed for %s: %s", url, exc)
        return {"url": url, "title": "", "html": "", "status": 0, "error": str(exc), "bot_blocked": False, "found_jobs": False, "captured_json": []}
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def fetch_rendered_html(
    url: str,
    wait_ms: int = 2500,
    timeout: int = 25,
    force_browser: bool = False,
) -> dict[str, Any]:
    """Fetch a URL and return {url, title, html, status}.

    The normal path uses requests first. For JS-heavy pages, the function
    upgrades to Playwright when available. When *force_browser* is True,
    the browser snapshot is attempted first.
    """
    if force_browser:
        rendered = _render_with_playwright(url, wait_ms=wait_ms, timeout=timeout)
        if rendered and rendered.get("html"):
            return rendered

    try:
        with http_session() as session:
            response = session.get(url, timeout=timeout)
            html = response.text or ""
            title = _extract_title(html)

            # Check if the static response is a bot challenge page
            blocked = is_bot_blocked(html, response.status_code)

            static = {
                "url": response.url,
                "title": title,
                "html": html,
                "status": response.status_code,
                "rendered_by": "requests",
                "bot_blocked": blocked,
                "found_jobs": False,
                "captured_json": [],
            }

            # If bot-blocked, immediately try Playwright fallback
            if blocked:
                logger.info("Bot-blocked response from %s — upgrading to Playwright", url)
                rendered = _render_with_playwright(url, wait_ms=wait_ms, timeout=timeout)
                if rendered and rendered.get("html"):
                    return rendered
                return static

            # Career pages are often SPA shells even when they do not look
            # obviously dynamic. Prefer rendering them rather than returning
            # a static shell that yields zero jobs.
            should_render = (
                not response.ok
                or _looks_dynamic(html)
                or _looks_like_careers_url(url)
            )

            if not should_render:
                return static

            rendered = _render_with_playwright(url, wait_ms=wait_ms, timeout=timeout)
            if rendered and rendered.get("html"):
                rendered_html = rendered.get("html") or ""
                # When the browser snapshot yields materially more content, or
                # the page is a career portal, trust the rendered DOM.
                if len(rendered_html) >= len(html) or _looks_like_careers_url(url):
                    return rendered

            return static
    except Exception as exc:
        fallback = _render_with_playwright(url, wait_ms=wait_ms, timeout=timeout)
        if fallback and fallback.get("html"):
            return fallback
        return {"url": url, "title": "", "html": "", "status": 0, "error": str(exc), "rendered_by": "error", "bot_blocked": False, "found_jobs": False, "captured_json": []}