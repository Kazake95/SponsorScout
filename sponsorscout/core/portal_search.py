from __future__ import annotations

import json
import logging
import re
from collections import deque
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from sponsorscout.core.sponsorship import detect_sponsorship_keywords
from sponsorscout.services.browser_fetcher import fetch_rendered_html
from sponsorscout.core.url_normalizer import normalize_url

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Career URL paths to probe — comma bugs FIXED, extended list
# ────────────────────────────────────────────────────────────────
CAREERS_PATHS = [
    "",
    "/careers",
    "/careers/open-positions",
    "/careers/openings",
    "/careers/positions",
    "/careers/jobs",
    "/jobs",
    "/jobs/openings",
    "/job-openings",
    "/open-positions",
    "/open-roles",
    "/positions",
    "/vacancies",
    "/work-with-us",
    "/join-us",
    "/join",
    "/en/careers",
    "/en/jobs",
    # New common paths
    "/company/careers",
    "/company/jobs",
    "/about/careers",
    "/about/jobs",
    "/about-us/careers",
    "/about-us/jobs",
    "/career",
    "/careers/#openings",
    "/careers/vacancies",
    "/working-at-us",
    "/life",
    "/opportunities",
    "/job-board",
    "/apply",
    # Search-style listing pages used by larger SPA career sites
    "/careers/search",
    "/careers/all-jobs",
    "/careers/all-roles",
    "/careers/find-a-job",
    "/jobs/search",
    "/search-jobs",
    "/find-a-job",
    "/find-jobs",
]

ROLE_KEYWORDS = [
    "engineer", "developer", "analyst", "scientist", "architect", "designer",
    "manager", "lead", "head of", "director", "specialist", "consultant",
    "product", "data", "backend", "frontend", "full stack", "devops",
    "platform", "cloud", "qa", "test", "sales", "marketing",
    "finance", "operations", "recruiter", "coordinator", "support",
    "machine learning", "ml", "ai", "artificial intelligence", "data science",
    "ux", "ui", "user experience", "sre", "site reliability",
    "principal", "staff", "senior", "junior", "graduate", "intern", "associate",
    "nursing", "nurse", "physician", "doctor", "therapist",
    "pharma", "biotech", "research", "clinical",
    "executive", "ceo", "cto", "cfo", "vp", "vice president",
    "legal", "compliance", "audit", "risk",
    "hr", "human resources", "talent", "people", "culture",
    "technician", "operator", "advisor", "analyst",
]

# Words that indicate a navigation link, NOT a job listing
NAV_TITLE_BLACKLIST = {
    "login", "sign in", "sign up", "register", "help center", "help",
    "contact", "about", "about us", "blog", "news", "press", "careers",
    "our culture", "what we do", "where we work", "how we hire",
    "diversity and inclusion", "life at bolt", "life at",
    "privacy", "cookie", "cookies", "security", "terms",
    "products", "solutions", "features", "pricing", "customers",
    "ridesharing", "scooters", "e-bikes", "ebikes",
    "rides", "scooter", "e-bike", "drive", "food", "market", "plus",
    "skip to content", "skip to main content", "back to", "go to",
    "switch to", "view all", "see all", "show more", "show less",
    "download", "app store", "google play", "twitter", "facebook",
    "linkedin", "instagram", "youtube", "tiktok",
    "let's go", "skip the line", "product principles",
    "tobi's ai memo", "apply now", "view role", "view job",
    "open positions", "all jobs", "all roles",
    # Veriff / general site nav noise
    "resources", "all resources", "view all resources",
    "kyc center", "fraud center", "onboarding center", "idv center",
    "events & webinars", "events",
    "case studies", "age estimation demo", "roi calculator",
    "financial services", "ecommerce & marketplaces", "communities",
    "igaming & video gaming", "mobility & transportation",
    "authentication", "age assurance", "tools", "for developers",
    "education",
    # Company about / general nav pages
    "company", "our story", "our people", "our locations",
    "supported countries", "trust center", "work with us",
    "book a demo", "book demo", "live demo", "idv live demo",
    "contact sales", "demo",
    # Bolt / general web noise
    "suppliers", "terms and conditions", "insurance", "community guidelines",
    "cookies & policy", "cookie policy",
}

# URL patterns that indicate a navigation/category page, NOT a job listing
NAV_URL_PATTERNS = re.compile(
    r"(/en|/de|/fr|/es|/nl|/it|/pt|/et)?/(rides|scooters?|ebikes?|e-bikes?|"
    r"drive|food|market|plus|business|products?|solutions?|features?|pricing|"
    r"customers?|about|blog|news|press|culture|diversity|inclusion|"
    r"privacy|cookies?|security|terms|contact|help|login|signup|register|"
    r"get-verified|login\.veriff|help\.veriff|x\.com|twitter|facebook|"
    r"linkedin|instagram|youtube|tiktok"
    r")(/|$|\?)",
    re.I,
)

JOB_URL_RE = re.compile(
    r"(/|=)(job|jobs|career|careers|position|positions|role|roles|opening|"
    r"openings|vacancy|vacancies|apply|requisition|posting|postings|offer|opportunit)"
    r"(/|=|-|_|$|\?|#|\d)",
    re.I,
)
# Broadened URL pattern — catch numeric IDs after any path segment (many portals use /{id} or /slug/{id})
JOB_ID_URL_RE = re.compile(
    r"[a-z0-9_-]+/\d{2,}",
    re.I,
)
SKIP_URL_RE = re.compile(
    r"(linkedin\.com|facebook\.com|twitter\.com|instagram\.com|youtube\.com|"
    r"glassdoor|indeed\.com|"
    r"\.pdf|\.docx|\.zip|\.exe|mailto:|tel:|#|javascript:|"
    r"\.jpg|\.png|\.gif|\.svg|\.ico)",
    re.I,
)
ATS_LINK_RE = re.compile(
    r"(boards\.greenhouse\.io|jobs\.lever\.co|api\.lever\.co|jobs\.ashbyhq\.com|"
    r"apply\.workable\.com|myworkdayjobs\.com|jobs\.personio\.|teamtailor\.com|"
    r"smartrecruiters\.com|bamboohr\.com|recruitee\.com|jobvite\.com|icims\.com|"
    r"breezy\.hr|freshteam\.com|run\.homerun\.co|welcometothejungle\.com|manatal\.com)",
    re.I,
)


@dataclass(frozen=True)
class PortalJob:
    title: str
    url: str
    location: str = ""
    description: str = ""


# ────────────────────────────────────────────────────────────────
# URL generation
# ────────────────────────────────────────────────────────────────

def likely_careers_urls(base_url: str, is_verified: bool = False) -> list[str]:
    """Return robust candidate careers/listing URLs for a company site.

    When *is_verified* is True the caller has told us the exact careers URL,
    so we return it without probing sub-paths (avoids root-URL overwrite bugs).
    Use ``careers_path_fallbacks`` to get additional candidate sub-paths for
    the same root domain when the verified URL turns out to yield no jobs.
    """
    base = (base_url or "").strip()
    if not base:
        return []
    if not re.match(r"^https?://", base, re.I):
        base = f"https://{base}"

    parsed = urlparse(base)
    root = f"{parsed.scheme}://{parsed.netloc}"
    base_normalized = normalize_url(base)

    # If the caller already knows this is the correct careers URL, trust it.
    if is_verified:
        return [base_normalized]

    path_lower = parsed.path.lower()
    starts_on_careers = any(
        part in path_lower
        for part in ("career", "job", "join", "vacanc", "position", "opportunity")
    )

    urls = [base_normalized]

    if starts_on_careers:
        # Already on a careers path — also probe the root to pick up additional sub-paths
        urls.append(normalize_url(root))
    else:
        urls.extend(
            normalize_url(urljoin(root, path))
            for path in CAREERS_PATHS
            if path
        )
    return _dedupe(urls)


def careers_path_fallbacks(base_url: str, exclude: set[str] | None = None) -> list[str]:
    """Return standard ``CAREERS_PATHS`` candidate URLs for *base_url*'s root domain.

    Used as a second-pass fallback when a curated/"verified" careers URL is
    actually a marketing landing page with no job listings of its own (e.g.
    ``shopify.com/careers`` linking out to ``/careers/search``), so the
    crawler doesn't dead-end at 0 jobs just because that one page had no
    "next" links to follow.
    """
    base = (base_url or "").strip()
    if not base:
        return []
    if not re.match(r"^https?://", base, re.I):
        base = f"https://{base}"

    parsed = urlparse(base)
    root = f"{parsed.scheme}://{parsed.netloc}"
    exclude = exclude or set()

    urls = [
        normalize_url(urljoin(root, path))
        for path in CAREERS_PATHS
        if path
    ]
    return [u for u in _dedupe(urls) if u not in exclude]


# ────────────────────────────────────────────────────────────────
# ATS link extraction
# ────────────────────────────────────────────────────────────────

def extract_ats_links(base_url: str, html: str) -> list[str]:
    """Extract embedded official ATS board links from a careers page."""
    soup = BeautifulSoup(html or "", "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        full_url = normalize_url(urljoin(base_url, href))
        if ATS_LINK_RE.search(full_url):
            links.append(full_url)

    for match in ATS_LINK_RE.finditer(html or ""):
        start = max(0, match.start() - 120)
        end = min(len(html), match.end() + 220)
        snippet = html[start:end]
        url_match = re.search(r"https?://[^\s\"'<>]+", snippet)
        if url_match:
            links.append(normalize_url(url_match.group(0)))

    return _dedupe(links)


def _extract_pagination_links(base_url: str, html: str) -> list[str]:
    """Return likely pagination URLs from a careers page."""
    soup = BeautifulSoup(html or "", "lxml")
    links: list[str] = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        text = _clean_text(a.get_text(" ", strip=True)).lower()
        rels = {str(r).lower() for r in (a.get("rel") or [])}
        full_url = normalize_url(urljoin(base_url, href))
        if not _is_candidate_url(full_url):
            continue

        is_pager = (
            "next" in rels
            or text in {"next", "older", "newer", "more", "more jobs", "show more", "see more", "load more"}
            or "next" in text
            or "more jobs" in text
            or re.search(r"(?:[?&](?:page|p|offset|start)=\d+|/page/\d+|/p/\d+)", full_url, re.I)
        )
        if is_pager:
            links.append(full_url)

    return _dedupe(links)


# ────────────────────────────────────────────────────────────────
# Embedded JSON extraction (SPA job boards often embed data in <script>)
# ────────────────────────────────────────────────────────────────

def _extract_json_jobs(
    base_url: str,
    html: str,
    limit: int = 300,
    extra_blobs: list | None = None,
) -> list[PortalJob]:
    """Try to pull job data from embedded JSON inside <script> tags.

    Many modern career-page frameworks (Greenhouse API embeds, custom React/
    Vue SPAs, and even Teamtailor/Workable widgets) inject a JSON blob into
    a <script> tag.  We scan for common shapes like:
        - { "jobs": [ { "title": …, "url": … } ] }
        - [ { "title": …, "absolute_url": … } ]

    *extra_blobs* (optional) is a list of already-parsed JSON objects, e.g.
    captured from XHR/fetch network responses while rendering the page with
    Playwright. Many SPA job boards (Bolt, Shopify, etc.) never inline their
    job data into the HTML at all — they fetch it from a JSON/GraphQL API
    after the page loads — so the DOM/script-tag scan above finds nothing
    even after rendering. Walking these captured responses through the same
    heuristics catches that case.
    """
    found: list[PortalJob] = []

    if html:
        soup = BeautifulSoup(html, "lxml")

        for script in soup.find_all("script"):
            raw = script.string or ""
            # Quick guard: skip tiny or empty scripts
            if len(raw) < 50:
                continue

            # Strategy 1: look for assignment patterns like  __NEXT_DATA__ = {...}  or  window.__DATA__ = {...}
            for pattern in (
                r"(?:__NEXT_DATA__|__INITIAL_DATA__|__PRELOADED_STATE__|window\.\w+)\s*=\s*(\{.+?\})\s*;?\s*</script>",
                r"JSON\.parse\((.+?)\)\s*[;)]",
                r"application/ld\+json[^>]*>\s*(\{.+?\})\s*</script>",
            ):
                m = re.search(pattern, raw, re.S)
                if not m:
                    continue
                try:
                    blob = json.loads(m.group(1))
                except (json.JSONDecodeError, ValueError):
                    continue

                _collect_jobs_from_json(blob, base_url, found, limit)
                if len(found) >= limit:
                    return found[:limit]

            # Strategy 2: just try parsing the whole script content as JSON
            stripped = raw.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    blob = json.loads(stripped)
                    _collect_jobs_from_json(blob, base_url, found, limit)
                except (json.JSONDecodeError, ValueError):
                    pass
                if len(found) >= limit:
                    return found[:limit]

    # Strategy 3: JSON blobs captured from network XHR/fetch responses.
    for blob in (extra_blobs or []):
        if len(found) >= limit:
            break
        try:
            _collect_jobs_from_json(blob, base_url, found, limit)
        except Exception:
            continue

    return found[:limit]


def _collect_jobs_from_json(
    blob,
    base_url: str,
    out: list[PortalJob],
    limit: int,
) -> None:
    """Walk a (possibly nested) JSON structure looking for job-like dicts."""
    if isinstance(blob, dict):
        # If this dict itself looks like a single job, collect it
        if _is_job_dict(blob):
            _add_json_job(blob, base_url, out, limit)
            return
        # Otherwise recurse into values
        for v in blob.values():
            _collect_jobs_from_json(v, base_url, out, limit)
            if len(out) >= limit:
                return
    elif isinstance(blob, list):
        for item in blob:
            _collect_jobs_from_json(item, base_url, out, limit)
            if len(out) >= limit:
                return


def _is_job_dict(d: dict) -> bool:
    """Heuristic: does this dict represent a single job listing?"""
    keys_lower = {k.lower() for k in d.keys()}
    has_title = bool(keys_lower & {"title", "name", "job_title", "position_title", "role"})
    has_url = bool(keys_lower & {"url", "absolute_url", "job_url", "link", "href", "apply_url", "external_url"})
    return has_title and has_url


def _add_json_job(
    d: dict,
    base_url: str,
    out: list[PortalJob],
    limit: int,
) -> None:
    if len(out) >= limit:
        return
    title_key = None
    for k in ("title", "name", "job_title", "position_title", "role"):
        if k in d:
            title_key = k
            break
    url_key = None
    for k in ("url", "absolute_url", "job_url", "link", "href", "apply_url", "external_url"):
        if k in d:
            url_key = k
            break
    if not title_key or not url_key:
        return

    title = str(d.get(title_key, "")).strip()
    url_raw = str(d.get(url_key, "")).strip()
    if not title or not url_raw:
        return
    url = normalize_url(urljoin(base_url, url_raw))

    location = ""
    for k in ("location", "location_name", "office", "city", "country", "region"):
        if k in d and d[k]:
            location = str(d[k]).strip()
            break

    description = ""
    for k in ("description", "description_html", "summary", "snippet", "short_description"):
        if k in d and d[k]:
            description = str(d[k]).strip()
            break

    out.append(PortalJob(title=title[:200], url=url, location=location, description=description[:2000]))


# ────────────────────────────────────────────────────────────────
# HTML job extraction (the main workhorse)
# ────────────────────────────────────────────────────────────────

def extract_jobs_from_html(
    base_url: str,
    html: str,
    query: str = "",
    country: str = "",
    sponsorship_only: bool = False,
    remote_filter: str = "All",
    limit: int = 300,
    extra_json_blobs: list | None = None,
) -> list[PortalJob]:
    """Extract likely job detail links from one HTML listing page.

    Strategy (in order of preference):
      1. Embedded JSON inside <script> tags (SPA / Next.js / React portals),
         plus any *extra_json_blobs* captured from network responses
      2. Anchor tags → container text → title extraction
      3. Non-anchor job-card containers with click-target <div>/<button>
    """
    soup = BeautifulSoup(html or "", "lxml")
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    # ── Strategy 1: Embedded JSON ───────────────────────────────
    json_jobs = _extract_json_jobs(base_url, html, limit, extra_blobs=extra_json_blobs)
    for job in json_jobs:
        if job.url in seen:
            continue
        if not _matches_filters(job.description, job.title, job.url, query, country, sponsorship_only, remote_filter):
            continue
        seen.add(job.url)
        jobs.append(job)
    if len(jobs) >= limit:
        return jobs[:limit]

    # ── Strategy 2: Anchor tags (original approach, improved) ──
    full_page_text = soup.get_text(" ", strip=True).lower()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        full_url = normalize_url(urljoin(base_url, href))
        if not _is_candidate_url(full_url) or full_url in seen:
            continue

        container = _nearest_job_container(a)
        text = _clean_text(
            container.get_text(" ", strip=True)
            if container
            else a.get_text(" ", strip=True)
        )
        title = _best_title(a, text, full_page_text)

        if len(title) < 3:
            logger.debug("Skipped short title on %s: %r", full_url, title)
            continue
        if not _looks_like_job(title, full_url, text, full_page_text):
            logger.debug("Skipped non-job link on %s: %r", full_url, title)
            continue
        if not _matches_filters(text, title, full_url, query, country, sponsorship_only, remote_filter):
            logger.debug("Skipped filtered link on %s: %r", full_url, title)
            continue

        seen.add(full_url)
        jobs.append(
            PortalJob(
                title=title[:200],
                url=full_url,
                location=_guess_location(text, country),
                description=text[:2000],
            )
        )
        if len(jobs) >= limit:
            break

    # ── Strategy 3: Non-anchor job containers (button, div, li) ──
    if len(jobs) < limit:
        _extract_div_job_cards(soup, base_url, full_page_text, seen, jobs, query, country, sponsorship_only, remote_filter, limit)

    return jobs[:limit]


def _extract_div_job_cards(
    soup,
    base_url: str,
    full_page_text: str,
    seen: set[str],
    out: list[PortalJob],
    query: str,
    country: str,
    sponsorship_only: bool,
    remote_filter: str,
    limit: int,
) -> None:
    """Extract jobs from non-anchor containers (e.g. <div> cards with buttons).

    Many SPA career boards (Vue/React) render job "cards" as plain <div>/<li>
    elements with a client-side router click handler instead of a real
    ``<a href>`` — the destination only lives in an ``onclick``/``data-*``
    attribute or is built from a ``data-job-id``. This function tries several
    progressively looser ways of recovering a usable URL and title from such
    cards so those listings aren't silently dropped.
    """
    # Common CSS selector patterns for job cards
    card_selectors = [
        '[data-job-id]',
        '[data-position-id]',
        '[data-vacancy-id]',
        '[data-employment-id]',
        '[data-testid*="job"]',
        '[data-cy*="job"]',
        '[class*="job-card"]',
        '[class*="JobCard"]',
        '[class*="position-card"]',
        '[class*="job-listing"]',
        '[class*="job-item"]',
        '[class*="JobItem"]',
        '[class*="vacancy-item"]',
        '[class*="vacancy-card"]',
        '[class*="career-item"]',
        '[class*="opening-item"]',
        '[class*="role-card"]',
        '[class*="opportunity"]',
        '[class*="search-result"]',
        '[class*="job-result"]',
        '[role="listitem"]',
        'li[class*="job"]',
        'li[class*="position"]',
        'li[class*="vacancy"]',
        'article[class*="job"]',
    ]

    # Patterns used to dig a destination URL out of click-handler attributes
    # like onclick="window.location.href='/jobs/12345'" or a router push.
    _HREF_IN_JS_RE = re.compile(
        r"""(?:location(?:\.href)?|window\.open|router\.push|navigate|to)\s*"""
        r"""[=(]\s*['"]([^'"]+)['"]""",
        re.I,
    )

    def _url_from_onclick(el) -> str:
        for attr_name in ("onclick", "onmousedown"):
            val = el.get(attr_name, "") if hasattr(el, "get") else ""
            if not val:
                continue
            m = _HREF_IN_JS_RE.search(val)
            if m:
                return m.group(1)
        return ""

    for selector in card_selectors:
        if len(out) >= limit:
            break
        try:
            containers = soup.select(selector)
        except Exception:
            continue

        for container in containers:
            if len(out) >= limit:
                break

            # Try to find a link or heading inside the container
            link = container.find("a", href=True)
            heading = container.find(["h1", "h2", "h3", "h4", "h5", "h6", "a"])

            title = ""
            if heading is not None:
                title = _clean_text(heading.get_text(" ", strip=True)) if hasattr(heading, "get_text") else ""
            if len(title) < 3:
                title = _clean_text(container.get_text(" ", strip=True))[:120]
            if len(title) < 3:
                continue

            # Build URL from link, click-handler JS, data attributes, or job id.
            url = ""
            if link and link.get("href"):
                url = normalize_url(urljoin(base_url, link["href"].strip()))
            else:
                # data-* attributes that hold a full URL or path
                for attr in (
                    "data-job-url", "data-url", "data-apply-url", "data-link",
                    "data-href", "data-target", "data-redirect", "data-path",
                ):
                    val = container.get(attr, "").strip()
                    if val:
                        url = normalize_url(urljoin(base_url, val))
                        break

                # onclick / onmousedown JS handlers (Vue/React custom routers)
                if not url:
                    js_target = _url_from_onclick(container)
                    if not js_target:
                        for child in container.find_all(True, recursive=True):
                            js_target = _url_from_onclick(child)
                            if js_target:
                                break
                    if js_target:
                        url = normalize_url(urljoin(base_url, js_target))

                # Synthesize from a job/position/vacancy id attribute as a
                # last resort — common slug shapes across ATS-style boards.
                if not url:
                    job_id = (
                        container.get("data-job-id", "")
                        or container.get("data-position-id", "")
                        or container.get("data-vacancy-id", "")
                        or container.get("data-employment-id", "")
                    )
                    job_id = re.sub(r"[^A-Za-z0-9_-]", "", job_id or "")
                    if job_id:
                        url = normalize_url(urljoin(base_url, f"/jobs/{job_id}"))

            if not url or url in seen or not _is_candidate_url(url):
                continue
            if not _looks_like_job(title, url, _clean_text(container.get_text(" ", strip=True)), full_page_text):
                continue

            text = _clean_text(container.get_text(" ", strip=True))
            if not _matches_filters(text, title, url, query, country, sponsorship_only, remote_filter):
                continue

            seen.add(url)
            out.append(
                PortalJob(
                    title=title[:200],
                    url=url,
                    location=_guess_location(text, country),
                    description=text[:2000],
                )
            )


# ────────────────────────────────────────────────────────────────
# Crawler
# ────────────────────────────────────────────────────────────────

def crawl_official_careers(
    session,
    careers_url: str,
    query: str = "",
    country: str = "",
    sponsorship_only: bool = False,
    remote_filter: str = "All",
    max_pages: int = 8,
    limit: int = 300,
    is_verified: bool = False,
) -> tuple[list[PortalJob], list[str]]:
    """Probe likely careers URLs and return extracted jobs plus embedded ATS links."""
    jobs: list[PortalJob] = []
    ats_links: list[str] = []
    seen_jobs: set[str] = set()
    seen_pages: set[str] = set()
    state = {"last_valid_url": "", "last_valid_html": ""}

    def _crawl_queue(pending: deque, page_budget: int) -> None:
        """Process a queue of candidate pages, mutating jobs/ats_links in place."""
        while pending and len(seen_pages) < page_budget and len(jobs) < limit:
            url = pending.popleft()
            if url in seen_pages:
                continue
            seen_pages.add(url)

            try:
                resp = session.get(url, timeout=20, allow_redirects=True)
                if resp.status_code >= 400 or len(resp.text or "") < 200:
                    continue
            except Exception as exc:
                logger.debug("Portal probe failed for %s: %s", url, exc)
                continue

            final_url = normalize_url(getattr(resp, "url", url) or url)
            static_html = resp.text or ""
            page_html = static_html
            state["last_valid_url"] = final_url
            state["last_valid_html"] = static_html

            ats_links.extend(extract_ats_links(final_url, page_html))

            page_jobs = extract_jobs_from_html(
                final_url, page_html, query, country, sponsorship_only, remote_filter, limit
            )

            # JS-rendered page fallback: try a browser snapshot whenever the static
            # HTML does not yield jobs. Many modern portals hide listings behind a
            # hydrated React/Next.js shell with no useful markup until JS runs.
            # Also trigger fallback for large SPA-like pages (> 30KB static HTML with no jobs)
            # that are clearly React/Angular/Vue shells waiting for JavaScript.
            large_spa = (len(page_html) > 30000 and len(page_jobs) == 0)
            if len(page_jobs) == 0 or large_spa:
                rendered = fetch_rendered_html(final_url, wait_ms=2500, timeout=25, force_browser=True)
                rendered_html = rendered.get("html") or ""
                rendered_url = normalize_url(rendered.get("url") or final_url)
                captured_json = rendered.get("captured_json") or []
                if rendered_html and rendered_html != page_html:
                    page_html = rendered_html
                    final_url = rendered_url
                    state["last_valid_url"] = final_url
                    state["last_valid_html"] = rendered_html
                    ats_links.extend(extract_ats_links(final_url, page_html))
                    page_jobs = extract_jobs_from_html(
                        final_url, page_html, query, country, sponsorship_only, remote_filter, limit,
                        extra_json_blobs=captured_json,
                    )
                elif captured_json:
                    # The DOM didn't change but the SPA's API calls returned
                    # job data we can parse directly (Bolt/Shopify-style
                    # boards that fetch listings client-side).
                    page_jobs = extract_jobs_from_html(
                        final_url, page_html, query, country, sponsorship_only, remote_filter, limit,
                        extra_json_blobs=captured_json,
                    )

            for job in page_jobs:
                if job.url in seen_jobs:
                    continue
                seen_jobs.add(job.url)
                jobs.append(job)
                if len(jobs) >= limit:
                    break

            # Queue pagination URLs discovered on the current page.
            for next_url in _extract_pagination_links(final_url, page_html):
                if next_url in seen_pages or next_url in pending:
                    continue
                if len(seen_pages) + len(pending) >= page_budget:
                    break
                pending.append(next_url)

            if len(jobs) >= limit:
                break

    probe_urls = likely_careers_urls(careers_url, is_verified=is_verified)[:max_pages]
    _crawl_queue(deque(probe_urls), max_pages)

    # Fallback pass: a curated/"verified" careers_url is sometimes a
    # marketing landing page with no job listings of its own and no "next"
    # links (e.g. shopify.com/careers linking out to /careers/search). If
    # the verified page yielded nothing, retry the standard CAREERS_PATHS for
    # the same domain before giving up.
    if not jobs and is_verified:
        fallback_urls = careers_path_fallbacks(careers_url, exclude=seen_pages)[:max_pages]
        if fallback_urls:
            _crawl_queue(deque(fallback_urls), len(seen_pages) + max_pages)

    # Final rescue pass: if static crawling failed entirely, render the last
    # valid page one more time and parse the browser DOM.
    if not jobs and state["last_valid_url"]:
        rendered = fetch_rendered_html(state["last_valid_url"], wait_ms=3500, timeout=30, force_browser=True)
        rendered_html = rendered.get("html") or ""
        rendered_url = normalize_url(rendered.get("url") or state["last_valid_url"])
        captured_json = rendered.get("captured_json") or []
        if (rendered_html and rendered_html != state["last_valid_html"]) or captured_json:
            ats_links.extend(extract_ats_links(rendered_url, rendered_html))
            for job in extract_jobs_from_html(
                rendered_url, rendered_html, query, country, sponsorship_only, remote_filter, limit,
                extra_json_blobs=captured_json,
            ):
                if job.url in seen_jobs:
                    continue
                seen_jobs.add(job.url)
                jobs.append(job)
                if len(jobs) >= limit:
                    break

    return jobs, _dedupe(ats_links)


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def _is_candidate_url(url: str) -> bool:
    return bool(url and not SKIP_URL_RE.search(url))


# ── Strong CSS class indicators for job containers ───
# Removed generic terms like "card", "item", "row" which match nav/footer
# wrappers on modern sites and pollute the extracted container text.
_CONTAINER_CLASS_INDICATORS = [
    "job", "position", "role", "opening", "vacancy", "listing", "posting",
    "career", "work", "opportunity", "employment", "recruit",
    "JobCard", "JobList", "JobItem", "JobRow",
    "PositionCard", "OpeningCard", "VacancyItem",
]


def _nearest_job_container(node):
    for parent in node.parents:
        if getattr(parent, "name", "") in {"li", "article", "section", "tr", "div", "span", "td"}:
            cls = " ".join(parent.get("class", [])).lower() if hasattr(parent, "get") else ""
            # Only accept parents with a strong class indicator to avoid greedy matching
            if any(ind in cls for ind in _CONTAINER_CLASS_INDICATORS):
                text = _clean_text(parent.get_text(" ", strip=True))
                if len(text) >= 10 and len(text) <= 1200:
                    return parent
    return node


def _best_title(anchor, fallback_text: str, full_page_text: str = "") -> str:
    """Extract the best job title from an anchor element.

    Priority: aria-label → title attr → anchor text → data attributes → fallback.
    Now also accepts titles as short as 3 characters (e.g. CTO, CIO).
    """
    # Check data-* attributes first — many portals put the job title there
    data_title = ""
    if hasattr(anchor, "get"):
        for attr in ("data-title", "data-job-title", "data-position-name", "data-label"):
            val = anchor.get(attr, "")
            if val:
                data_title = val
                break

    aria = ""
    title_attr = ""
    if hasattr(anchor, "get"):
        aria = anchor.get("aria-label", "")
        title_attr = anchor.get("title", "")

    anchor_text = _clean_text(anchor.get_text(" ", strip=True))

    for candidate in (aria, title_attr, anchor_text, data_title, fallback_text):
        candidate = _clean_text(candidate)
        if 3 <= len(candidate) <= 200:
            return candidate
    return anchor_text[:200]


def _looks_like_job(title: str, url: str, text: str, full_page_text: str = "") -> bool:
    """Determine if a link + surrounding context represents a job listing.

    Uses URL pattern matching, role keyword matching (against both the link
    text AND the full page text), and structural signals from the URL path.
    """
    title_lower = title.lower().strip()

    junk_titles = {
        "",
        "learn more",
        "read more",
        "apply now",
        "view job",
        "view role",
        "open roles",
        "open positions",
        "open vacancies",
        "all jobs",
        "all roles",
        "all positions",
        "all vacancies",
        "show more",
        "see more",
        "search jobs",
        "search roles",
        "search positions",
        "search vacancies",
        "search open roles",
        "search open positions",
        "browse jobs",
        "browse roles",
        "browse positions",
        "browse vacancies",
        "browse careers",
        "browse open roles",
        "find jobs",
        "find a job",
        "find your role",
        "find a role",
        "explore jobs",
        "explore roles",
        "explore careers",
        "explore positions",
        "job search",
        "careers page",
        "view jobs",
        "view careers",
        "view all jobs",
        "view all roles",
        "view all positions",
        "view openings",
        "view open roles",
        "view open positions",
        "view open vacancies",
        "see jobs",
        "see roles",
        "see open roles",
        "see open positions",
        "see open vacancies",
        "see all jobs",
        "see all roles",
        "see all positions",
        "join the team",
        "join us",
        "join our team",
        "current openings",
        "current vacancies",
        "current job openings",
    }

    if title_lower in junk_titles:
        return False

    if ATS_LINK_RE.search(url):
        return True

    if JOB_URL_RE.search(url):
        return True

    if JOB_ID_URL_RE.search(urlparse(url).path):
        return True


    # ── Noise filtering: reject navigation links, social links, etc. ──
    title_lower = title.lower().strip()
    # Check against navigation title blacklist
    if title_lower in NAV_TITLE_BLACKLIST:
        return False
    # Check if title contains a blacklisted phrase (word-boundary matching
    # to avoid false positives like "market" matching "Marketing").
    for blacklisted in NAV_TITLE_BLACKLIST:
        if re.search(r'\b' + re.escape(blacklisted) + r'\b', title_lower):
            # If the blacklisted term makes up most of the title, reject it
            if len(title_lower) - len(blacklisted) < 5:
                return False
            # If the title also contains a role keyword, it's likely a real
            # job title (e.g. "Security Engineer", "Food Scientist")
            if any(kw in title_lower for kw in ROLE_KEYWORDS):
                continue
            # Otherwise reject — nav/footer links don't have role keywords
            return False
    # Check for language switcher URLs like /es/, /pt-br/, /et/
    parsed = urlparse(url)
    if re.search(r"^/(?:es|pt|pt-br|et|lt|lv|pl|it|fr|de|nl|sv|fi|da|no)($|/)", parsed.path):
        return False
    # Check for industry pages, use-cases, and other non-job URLs
    if re.search(r"/(industry|use-cases|case-studies|solutions|resources|news|events|blog|about)/[^/]+$", parsed.path, re.I):
        return False
    # Check for language switcher in title
    if "language switcher" in title_lower or "switch to " in title_lower:
        return False
    # Check URL against navigation patterns
    if NAV_URL_PATTERNS.search(url):
        return False
    # Skip very short titles that are likely nav items (e.g. "Rides", "Food")
    if len(title_lower) < 5 and not any(kw in title_lower for kw in ROLE_KEYWORDS):
        return False

    low = f"{title} {url} {text}".lower()

    # Keyword match against title + url + container text
    if any(keyword in low for keyword in ROLE_KEYWORDS):
        return True


    # Structural signal: the URL path segment after /jobs/ or /careers/ looks like a slug
    path_parts = urlparse(url).path.strip("/").split("/")
    for i, part in enumerate(path_parts):
        if part.lower() in ("jobs", "positions", "careers", "openings", "vacancies") and i + 1 < len(path_parts):
            slug = path_parts[i + 1]
            # Slugs typically contain hyphens and are multi-word
            if "-" in slug and len(slug) >= 5:
                return True

    return False


def _matches_filters(
    text: str,
    title: str,
    url: str,
    query: str,
    country: str,
    sponsorship_only: bool,
    remote_filter: str,
) -> bool:
    haystack = f"{title} {text} {url}".lower()
    terms = [t for t in re.split(r"[\s,;/]+", (query or "").lower()) if len(t) >= 3]
    if terms and not any(term in haystack for term in terms):
        return False

    if country and country.lower() not in haystack:
        signals = detect_sponsorship_keywords(haystack)
        if signals.get("remote_type") not in {"remote_eu", "remote_emea", "remote_global", "remote"}:
            return False

    signals = detect_sponsorship_keywords(haystack)
    if sponsorship_only and not (signals.get("visa_sponsorship") or signals.get("relocation") or signals.get("eu_blue_card")):
        return False

    remote = (remote_filter or "All").lower()
    remote_type = signals.get("remote_type", "onsite")
    if remote not in {"", "all"}:
        allowed = {
            "remote eu": {"remote_eu"},
            "remote emea": {"remote_eu", "remote_emea"},
            "remote global": {"remote_eu", "remote_emea", "remote_global", "remote"},
            "remote only": {"remote_eu", "remote_emea", "remote_global", "remote"},
            "hybrid": {"hybrid"},
        }.get(remote)
        if allowed and remote_type not in allowed:
            return False

    return True


def _guess_location(text: str, fallback_country: str = "") -> str:
    cleaned = _clean_text(text)
    for label in ("Location", "Office", "Based in", "Where", "Place"):
        match = re.search(rf"{label}\s*:?\s*([^|•\n]{2,80})", cleaned, re.I)
        if match:
            return match.group(1).strip()
    return fallback_country or ""


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


# ── Playwright fallback for JS-rendered career pages ──
# Delegates to browser_fetcher.py which has full stealth mode and anti-bot
# detection. This avoids duplicating Playwright launch logic.

def _render_with_playwright(url: str, timeout: int = 15) -> str | None:
    """Return the full HTML of a page after JS execution, or None on failure.

    This is an *optional* fallback used when a career page renders its job
    listings entirely with client-side JavaScript (e.g. Bolt, some Workday
    embeds). Delegates to ``fetch_rendered_html`` for stealth patches and
    anti-bot detection.

    If ``playwright`` is not installed the function silently returns ``None``
    and the caller continues with the normal flow.
    """
    try:
        from sponsorscout.services.browser_fetcher import fetch_rendered_html
        result = fetch_rendered_html(url, wait_ms=3000, timeout=timeout, force_browser=True)
        if result and result.get("html"):
            return result["html"]
        return None
    except Exception as exc:
        logger.debug("Playwright render failed for %s: %s", url, exc)
        return None
