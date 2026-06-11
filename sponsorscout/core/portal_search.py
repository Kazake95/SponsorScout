from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from sponsorscout.core.sponsorship import detect_sponsorship_keywords
from sponsorscout.core.url_normalizer import normalize_url

logger = logging.getLogger(__name__)


CAREERS_PATHS = [
    "",
    "/careers",
    "/jobs",
    "/careers/jobs",
    "/careers/open-positions",
    "/careers/openings",
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
]

ROLE_KEYWORDS = [
    "engineer", "developer", "analyst", "scientist", "architect", "designer",
    "manager", "lead", "head of", "director", "specialist", "consultant",
    "product", "data", "backend", "frontend", "full stack", "devops",
    "platform", "cloud", "security", "qa", "test", "sales", "marketing",
    "finance", "operations", "recruiter", "coordinator", "support",
]

JOB_URL_RE = re.compile(
    r"(/|=)(job|jobs|career|careers|position|positions|role|roles|opening|"
    r"openings|vacancy|vacancies|apply|requisition|posting|postings|offer)"
    r"(/|=|-|_|$)",
    re.I,
)
SKIP_URL_RE = re.compile(
    r"(linkedin|facebook|twitter|instagram|youtube|glassdoor|indeed|"
    r"\.pdf|\.docx|mailto:|tel:|#|javascript:|privacy|cookie|legal|"
    r"login|signup|register|about|news|blog|press|contact|sitemap|terms|gdpr)",
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


def likely_careers_urls(base_url: str) -> list[str]:
    """Return robust candidate careers/listing URLs for a company site."""
    base = (base_url or "").strip()
    if not base:
        return []
    if not re.match(r"^https?://", base, re.I):
        base = f"https://{base}"
    parsed = urlparse(base)
    root = f"{parsed.scheme}://{parsed.netloc}"
    starts_on_careers = any(part in parsed.path.lower() for part in ("career", "job", "join", "vacanc"))

    urls = [normalize_url(base)]
    if not starts_on_careers:
        urls.extend(normalize_url(urljoin(root, path)) for path in CAREERS_PATHS if path)
    return _dedupe(urls)


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


def extract_jobs_from_html(
    base_url: str,
    html: str,
    query: str = "",
    country: str = "",
    sponsorship_only: bool = False,
    remote_filter: str = "All",
    limit: int = 300,
) -> list[PortalJob]:
    """Extract likely job detail links from one HTML listing page."""
    soup = BeautifulSoup(html or "", "lxml")
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        full_url = normalize_url(urljoin(base_url, href))
        if not _is_candidate_url(full_url) or full_url in seen:
            continue

        container = _nearest_job_container(a)
        text = _clean_text(container.get_text(" ", strip=True) if container else a.get_text(" ", strip=True))
        title = _best_title(a, text)
        if len(title) < 6 or not _looks_like_job(title, full_url, text):
            continue
        if not _matches_filters(text, title, full_url, query, country, sponsorship_only, remote_filter):
            continue

        seen.add(full_url)
        jobs.append(PortalJob(title=title[:200], url=full_url, location=_guess_location(text, country), description=text[:2000]))
        if len(jobs) >= limit:
            break
    return jobs


def crawl_official_careers(
    session,
    careers_url: str,
    query: str = "",
    country: str = "",
    sponsorship_only: bool = False,
    remote_filter: str = "All",
    max_pages: int = 8,
    limit: int = 300,
) -> tuple[list[PortalJob], list[str]]:
    """Probe likely careers URLs and return extracted jobs plus embedded ATS links."""
    jobs: list[PortalJob] = []
    ats_links: list[str] = []
    seen_jobs: set[str] = set()

    for url in likely_careers_urls(careers_url)[:max_pages]:
        try:
            resp = session.get(url, timeout=20, allow_redirects=True)
            if resp.status_code >= 400 or len(resp.text or "") < 200:
                continue
        except Exception as exc:
            logger.debug("Portal probe failed for %s: %s", url, exc)
            continue

        final_url = normalize_url(getattr(resp, "url", url) or url)
        ats_links.extend(extract_ats_links(final_url, resp.text))
        for job in extract_jobs_from_html(final_url, resp.text, query, country, sponsorship_only, remote_filter, limit):
            if job.url in seen_jobs:
                continue
            seen_jobs.add(job.url)
            jobs.append(job)
            if len(jobs) >= limit:
                break
        if len(jobs) >= limit:
            break

    return jobs, _dedupe(ats_links)


def _is_candidate_url(url: str) -> bool:
    return bool(url and not SKIP_URL_RE.search(url))


def _nearest_job_container(node):
    for parent in node.parents:
        if getattr(parent, "name", "") in {"li", "article", "section", "tr", "div"}:
            text = _clean_text(parent.get_text(" ", strip=True))
            cls = " ".join(parent.get("class", [])).lower() if hasattr(parent, "get") else ""
            if len(text) >= 12 and ("job" in cls or "position" in cls or "role" in cls or len(text) <= 900):
                return parent
    return node


def _best_title(anchor, fallback_text: str) -> str:
    aria = anchor.get("aria-label", "") if hasattr(anchor, "get") else ""
    title_attr = anchor.get("title", "") if hasattr(anchor, "get") else ""
    anchor_text = _clean_text(anchor.get_text(" ", strip=True))
    for candidate in (anchor_text, title_attr, aria, fallback_text):
        candidate = _clean_text(candidate)
        if 6 <= len(candidate) <= 200:
            return candidate
    return anchor_text[:200]


def _looks_like_job(title: str, url: str, text: str) -> bool:
    low = f"{title} {url} {text}".lower()
    return bool(JOB_URL_RE.search(url) or any(keyword in low for keyword in ROLE_KEYWORDS))


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
    for label in ("Location", "Office", "Based in"):
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
