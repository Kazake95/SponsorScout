from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from sponsorscout.core.sponsorship import detect_sponsorship_keywords
from sponsorscout.services.browser_fetcher import fetch_rendered_html
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.core.http_client import http_session, is_bot_blocked

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role keywords — expanded for European languages
# ---------------------------------------------------------------------------
ROLE_KEYWORDS = [
    # English
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
    "technician", "operator", "advisor",
    # German
    "ingenieur", "entwickler", "leiter", "mitarbeiter", "werkstudent",
    "praktikant", "berater", "spezialist", "koordinator", "assistent",
    "direktor", "chef", "fachkraft", "techniker", "kaufmann", "controller",
    "vertrieb", "einkauf", "produktion", "forschung", "entwicklung",
    "personal", "buchhaltung", "vertriebsmitarbeiter", "softwareentwickler",
    "datenanalyst", "stelle", "stellen",
    # Italian
    "ingegnere", "sviluppatore", "analista", "responsabile", "addetto",
    "impiegato", "consulente", "specialista", "coordinatore", "assistente",
    "direttore", "capo", "tecnico", "commerciale", "contabile", "ricerca",
    "sviluppo", "personale", "vendite", "posizione", "posizioni",
    # Dutch
    "ingenieur", "ontwikkelaar", "analist", "leidinggevende", "medewerker",
    "stagiair", "adviseur", "specialist", "coordinator", "assistent",
    "directeur", "chef", "technicus", "verkoper", "boekhouder", "vacature",
    # French
    "ingenieur", "developpeur", "analyste", "responsable", "employe",
    "consultant", "specialiste", "coordinateur", "assistant", "directeur",
    "chef", "technicien", "commercial", "comptable", "offre", "poste",
    # Spanish
    "ingeniero", "desarrollador", "analista", "gerente", "responsable",
    "empleado", "consultor", "especialista", "coordinador", "asistente",
    "director", "jefe", "tecnico", "comercial", "contable", "empleo",
    # Portuguese
    "engenheiro", "desenvolvedor", "analista", "gerente", "responsavel",
    "funcionario", "consultor", "especialista", "coordenador", "assistente",
    "diretor", "chefe", "tecnico", "comercial", "contabilista",
    # Swedish
    "ingenjor", "utvecklare", "analytiker", "chef", "ansvarig", "medarbetare",
    "praktikant", "konsult", "specialist", "samordnare", "assistent",
    "direktor", "tekniker", "saljare", "bokforare",
    # Polish
    "inzynier", "programista", "analityk", "menedzer", "kierownik",
    "pracownik", "stazysta", "konsultant", "specjalista", "koordynator",
    "asystent", "dyrektor", "technik", "handlowiec", "ksiegowy", "oferta",
    # Finnish
    "insinoori", "kehittaja", "analyytikko", "paallikko", "johtaja",
    "tyontekija", "harjoittelija", "konsultti", "asiantuntija", "koordinaattori",
    "assistentti", "tekninen", "myyja", "kirjanpitaja",
]

ROLE_KEYWORDS_RE = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in ROLE_KEYWORDS) + r")\b",
    re.I,
)

# ---------------------------------------------------------------------------
# Navigation / noise exclusion
# ---------------------------------------------------------------------------
NAV_TITLE_BLACKLIST = {
    "login", "sign in", "sign up", "register", "help center", "help",
    "contact", "about", "about us", "blog", "news", "press", "careers",
    "our culture", "what we do", "where we work", "how we hire",
    "diversity and inclusion", "life at", "privacy", "cookie", "cookies",
    "security", "terms", "products", "solutions", "features", "pricing",
    "customers", "skip to content", "skip to main content", "back to", "go to",
    "switch to", "view all", "see all", "show more", "show less",
    "download", "app store", "google play", "twitter", "facebook",
    "linkedin", "instagram", "youtube", "tiktok", "apply now", "view role",
    "view job", "open positions", "all jobs", "all roles", "all positions",
    "all vacancies", "search jobs", "search roles", "search positions",
    "browse jobs", "browse roles", "find jobs", "find a job", "explore jobs",
    "explore careers", "job search", "careers page", "view jobs", "view careers",
    "view all jobs", "see jobs", "join the team", "join us", "join our team",
    "current openings", "current vacancies", "book a demo", "live demo",
    "contact sales", "suppliers", "terms and conditions", "insurance",
    "community guidelines", "cookie policy", "create alert", "job alert",
    "upload cv", "upload resume", "manage preferences", "cookie settings",
    "learn more about us", "learn more", "read more", "details", "more details",
    "share", "save", "bookmark", "favorite",
}

GENERIC_CTAS = {
    "apply", "apply now", "apply online", "apply here", "apply for this job",
    "view job", "view role", "view position", "view opening", "view vacancy",
    "view all", "learn more", "read more", "see more", "show more",
    "details", "more details", "job details", "open position", "open positions",
    "open role", "open roles", "view details", "view", "more", "learn", "read",
    "join", "join us", "join team",
}

SKIP_URL_RE = re.compile(
    r"(linkedin\.com|facebook\.com|twitter\.com|instagram\.com|youtube\.com|"
    r"glassdoor|indeed\.com|\.pdf|\.docx|\.zip|\.exe|mailto:|tel:|#|javascript:|"
    r"\.jpg|\.png|\.gif|\.svg|\.ico)",
    re.I,
)

# ---------------------------------------------------------------------------
# ATS URL detection
# ---------------------------------------------------------------------------
ATS_LINK_RE = re.compile(
    r"(boards\.greenhouse\.io|jobs\.lever\.co|api\.lever\.co|jobs\.ashbyhq\.com|"
    r"apply\.workable\.com|myworkdayjobs\.com|jobs\.personio\.|teamtailor\.com|"
    r"smartrecruiters\.com|bamboohr\.com|recruitee\.com|jobvite\.com|icims\.com|"
    r"breezy\.hr|freshteam\.com|run\.homerun\.co|welcometothejungle\.com|manatal\.com|"
    r"successfactors\.(com|eu|cn)|\.taleo\.net|oraclecloudhcm\.com|"
    r"eightfold\.ai|phenom\.com|phenompeople\.com|"
    r"jobs\.workday\.com|wd\d+\.myworkdayjobs\.com|"
    r"apply\.workday\.com|careers\.peoplesoft\.com|hrcloud\.com|"
    r"ultipro\.com|ukg\.com|wise\.jobs|jobs\.babbel\.com|jobs\.booking\.com)",
    re.I,
)

# ---------------------------------------------------------------------------
# Job URL patterns — high confidence path segments
# ---------------------------------------------------------------------------
JOB_PATH_SEGMENTS_RE = re.compile(
    r"/(job|jobs|career|careers|position|positions|role|roles|opening|openings|"
    r"vacancy|vacancies|apply|requisition|posting|postings|offer|opportunit|"
    r"stelle|stellen|vacature|vacatures|offre|offres|poste|postes|posizione|posizioni|"
    r"empleo|empleos|oferta|ofertas|oferty|praca|praca|offene-stellen|"
    r"stellenangebote|posizioni-aperte|offres-emploi|vacatures|"
    r"join-us|work-with-us|current-openings|job-search|job-openings)/",
    re.I,
)

JOB_QUERY_PARAMS_RE = re.compile(
    r"[?&](gh_jid|lever-job-id|req_id|job_id|jobId|p_job_id|requisitionId)=[^&]+",
    re.I,
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PortalJob:
    title: str
    url: str
    location: str = ""
    description: str = ""
    company: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def crawl_official_careers(
    careers_url: str,
    query: str = "",
    country: str = "",
    sponsorship_only: bool = False,
    remote_filter: str = "All",
    max_pages: int = 1,
    limit: int = 300,
    is_verified: bool = False,
) -> tuple[list[PortalJob], list[str], dict]:
    """Crawl a single company career page and extract job listings."""
    jobs: list[PortalJob] = []
    ats_links: list[str] = []
    seen_jobs: set[str] = set()
    render_meta: dict = {"accordion_expanded": 0, "bot_blocked": False}

    target_url = normalize_url(careers_url)

    # Step 1: Try static fetch first
    try:
        with http_session() as session:
            r = session.get(target_url, timeout=15)
            if r.ok:
                static_html = r.text or ""
                static_ats = extract_ats_links(target_url, static_html)
                static_jobs = extract_jobs_from_html(
                    target_url, static_html, query, country,
                    sponsorship_only, remote_filter, limit,
                )
                if static_jobs and not is_bot_blocked(static_html):
                    for job in static_jobs:
                        if job.url in seen_jobs:
                            continue
                        seen_jobs.add(job.url)
                        jobs.append(job)
                    return jobs, _dedupe(static_ats), render_meta
    except Exception as exc:
        logger.debug("Static fetch for %s failed: %s", target_url, exc)

    # Step 2: Playwright render for JS-heavy pages
    rendered = fetch_rendered_html(target_url, wait_ms=4500, timeout=90, force_browser=True)
    rendered_html = rendered.get("html") or ""
    final_url = normalize_url(rendered.get("url") or target_url)
    captured_json = rendered.get("captured_json") or []
    render_meta["accordion_expanded"] += rendered.get("accordion_expanded", 0)
    render_meta["bot_blocked"] = bool(rendered.get("bot_blocked"))

    if rendered_html and not render_meta["bot_blocked"]:
        ats_links.extend(extract_ats_links(final_url, rendered_html))
        page_jobs = extract_jobs_from_html(
            final_url, rendered_html, query, country, sponsorship_only, remote_filter, limit,
            extra_json_blobs=captured_json,
        )
        for job in page_jobs:
            if job.url in seen_jobs:
                continue
            seen_jobs.add(job.url)
            jobs.append(job)

    return jobs, _dedupe(ats_links), render_meta


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
def _detect_platform(soup: BeautifulSoup, url: str) -> str:
    """Detect the ATS/platform from DOM fingerprints. Returns platform name or empty string."""
    html_text = str(soup)[:50000].lower()
    url_lower = url.lower()

    # Meta generator
    meta_generator = soup.find("meta", attrs={"name": "generator"})
    if meta_generator:
        content = (meta_generator.get("content") or "").lower()
        if "teamtailor" in content:
            return "teamtailor"

    # Footer / body text
    body_text = soup.get_text(" ", strip=True).lower()
    if "powered by personio" in body_text:
        return "personio"
    if "powered by smartrecruiters" in body_text:
        return "smartrecruiters"

    # URL patterns
    if "greenhouse.io" in url_lower:
        return "greenhouse"
    if "jobs.lever.co" in url_lower:
        return "lever"
    if "jobs.ashbyhq.com" in url_lower:
        return "ashby"
    if "myworkdayjobs.com" in url_lower:
        return "workday"
    if "apply.workable.com" in url_lower:
        return "workable"
    if "teamtailor.com" in url_lower:
        return "teamtailor"
    if "smartrecruiters.com" in url_lower:
        return "smartrecruiters"
    if "bamboohr.com" in url_lower:
        return "bamboohr"
    if "recruitee.com" in url_lower:
        return "recruitee"
    if "icims.com" in url_lower:
        return "icims"
    if "successfactors" in url_lower:
        return "sap"
    if ".taleo.net" in url_lower:
        return "taleo"

    # DOM class fingerprints
    if soup.find("div", class_=re.compile(r"opening\b")):
        return "greenhouse"
    if soup.find("div", class_=re.compile(r"posting\b")) or soup.find(attrs={"data-qa": "posting"}):
        return "lever"
    if soup.find(attrs={"data-automation-id": "jobTitle"}):
        return "workday"
    if soup.find("table", class_=re.compile(r"iCIMS")):
        return "icims"
    if soup.find("article", class_=re.compile(r"job-card")):
        return "smartrecruiters"
    if soup.find("a", class_=re.compile(r"job-listing__link")):
        return "teamtailor"

    return ""


# ---------------------------------------------------------------------------
# Platform-specific extraction
# ---------------------------------------------------------------------------
def _extract_teamtailor(soup, base_url: str, limit: int) -> list[PortalJob]:
    """Teamtailor: job-listing__link or data-job-id anchors."""
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = normalize_url(urljoin(base_url, href))
        if url in seen:
            continue

        # Must be a job link
        if not (a.get("data-job-id") or re.search(r"/jobs/", href, re.I)):
            continue

        title = _clean_text(a.get_text(" ", strip=True))
        if len(title) < 3 or title.lower() in GENERIC_CTAS:
            continue

        # Get location from sibling div if present
        location = ""
        parent = a.find_parent("div", class_=re.compile(r"job-listing"))
        if parent:
            loc_el = parent.find("div", class_=re.compile(r"job-listing__department|location"))
            if loc_el:
                location = _clean_text(loc_el.get_text(" ", strip=True))

        seen.add(url)
        jobs.append(PortalJob(title=title[:200], url=url, location=location))
        if len(jobs) >= limit:
            break

    return jobs


def _extract_personio(soup, base_url: str, limit: int) -> list[PortalJob]:
    """Personio: numeric job IDs, simple list items."""
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = normalize_url(urljoin(base_url, href))
        if url in seen:
            continue

        # Personio URLs: /jobs/{numeric-id}
        if not re.search(r"/jobs/\d+", href, re.I):
            continue

        title = _clean_text(a.get_text(" ", strip=True))
        if len(title) < 3 or title.lower() in GENERIC_CTAS:
            continue

        location = ""
        parent = a.find_parent("div", class_=re.compile(r"job-item|position"))
        if parent:
            loc_el = parent.find("span", class_=re.compile(r"location|job-location"))
            if loc_el:
                location = _clean_text(loc_el.get_text(" ", strip=True))

        seen.add(url)
        jobs.append(PortalJob(title=title[:200], url=url, location=location))
        if len(jobs) >= limit:
            break

    return jobs


def _extract_greenhouse(soup, base_url: str, limit: int) -> list[PortalJob]:
    """Greenhouse: .opening containers with title + location."""
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    for div in soup.find_all("div", class_=re.compile(r"\bopening\b")):
        a = div.find("a", href=True)
        if not a:
            continue

        href = a.get("href", "").strip()
        url = normalize_url(urljoin(base_url, href))
        if url in seen:
            continue

        title = _clean_text(a.get_text(" ", strip=True))
        if len(title) < 3 or title.lower() in GENERIC_CTAS:
            continue

        location = ""
        loc_el = div.find("span", class_=re.compile(r"location"))
        if loc_el:
            location = _clean_text(loc_el.get_text(" ", strip=True))

        seen.add(url)
        jobs.append(PortalJob(title=title[:200], url=url, location=location))
        if len(jobs) >= limit:
            break

    return jobs


def _extract_lever(soup, base_url: str, limit: int) -> list[PortalJob]:
    """Lever: .posting containers with data-qa attributes."""
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    for div in soup.find_all("div", class_=re.compile(r"\bposting\b")):
        a = div.find("a", href=True, attrs={"data-qa": re.compile(r"posting-name|job-title")})
        if not a:
            a = div.find("a", href=True)
        if not a:
            continue

        href = a.get("href", "").strip()
        url = normalize_url(urljoin(base_url, href))
        if url in seen:
            continue

        title = _clean_text(a.get_text(" ", strip=True))
        if len(title) < 3 or title.lower() in GENERIC_CTAS:
            continue

        location = ""
        loc_el = div.find("span", class_=re.compile(r"sort-by-location|location"))
        if loc_el:
            location = _clean_text(loc_el.get_text(" ", strip=True))

        seen.add(url)
        jobs.append(PortalJob(title=title[:200], url=url, location=location))
        if len(jobs) >= limit:
            break

    return jobs


def _extract_smartrecruiters(soup, base_url: str, limit: int) -> list[PortalJob]:
    """SmartRecruiters: .job-card articles."""
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    for article in soup.find_all("article", class_=re.compile(r"\bjob-card\b")):
        a = article.find("a", href=True)
        if not a:
            continue

        href = a.get("href", "").strip()
        url = normalize_url(urljoin(base_url, href))
        if url in seen:
            continue

        title = _clean_text(a.get_text(" ", strip=True))
        if len(title) < 3 or title.lower() in GENERIC_CTAS:
            continue

        location = ""
        loc_el = article.find("span", class_=re.compile(r"job-card__location|location"))
        if loc_el:
            location = _clean_text(loc_el.get_text(" ", strip=True))

        seen.add(url)
        jobs.append(PortalJob(title=title[:200], url=url, location=location))
        if len(jobs) >= limit:
            break

    return jobs


def _extract_workday(soup, base_url: str, limit: int) -> list[PortalJob]:
    """Workday: data-automation-id="jobTitle" anchors."""
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    for a in soup.find_all("a", attrs={"data-automation-id": "jobTitle"}):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = normalize_url(urljoin(base_url, href))
        if url in seen:
            continue

        title = _clean_text(a.get_text(" ", strip=True))
        if len(title) < 3 or title.lower() in GENERIC_CTAS:
            continue

        location = ""
        parent = a.find_parent("li")
        if parent:
            loc_el = parent.find("dd", attrs={"data-automation-id": "locations"})
            if loc_el:
                location = _clean_text(loc_el.get_text(" ", strip=True))

        seen.add(url)
        jobs.append(PortalJob(title=title[:200], url=url, location=location))
        if len(jobs) >= limit:
            break

    return jobs


def _extract_sap(soup, base_url: str, limit: int) -> list[PortalJob]:
    """SAP SuccessFactors: table rows with job links."""
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    for tr in soup.find_all("tr", class_=re.compile(r"sapUiTableRow|job-row")):
        a = tr.find("a", href=True)
        if not a:
            continue

        href = a.get("href", "").strip()
        url = normalize_url(urljoin(base_url, href))
        if url in seen:
            continue

        title = _clean_text(a.get_text(" ", strip=True))
        if len(title) < 3 or title.lower() in GENERIC_CTAS:
            continue

        location = ""
        loc_el = tr.find("td", class_=re.compile(r"city|location"))
        if loc_el:
            location = _clean_text(loc_el.get_text(" ", strip=True))

        seen.add(url)
        jobs.append(PortalJob(title=title[:200], url=url, location=location))
        if len(jobs) >= limit:
            break

    return jobs


def _extract_icims(soup, base_url: str, limit: int) -> list[PortalJob]:
    """iCIMS: table rows with iCIMS classes."""
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    for table in soup.find_all("table", class_=re.compile(r"iCIMS")):
        for tr in table.find_all("tr"):
            a = tr.find("a", class_=re.compile(r"iCIMS_Anchor"), href=True)
            if not a:
                a = tr.find("a", href=True)
            if not a:
                continue

            href = a.get("href", "").strip()
            url = normalize_url(urljoin(base_url, href))
            if url in seen:
                continue

            title = _clean_text(a.get_text(" ", strip=True))
            if len(title) < 3 or title.lower() in GENERIC_CTAS:
                continue

            seen.add(url)
            jobs.append(PortalJob(title=title[:200], url=url))
            if len(jobs) >= limit:
                break

    return jobs


# ---------------------------------------------------------------------------
# Generic extraction — multi-pass fallback for unknown platforms
# ---------------------------------------------------------------------------
def _extract_json_jobs(base_url: str, html: str, limit: int, extra_blobs: list | None = None) -> list[PortalJob]:
    found: list[PortalJob] = []
    if not html:
        return found

    soup = BeautifulSoup(html, "lxml")

    # Inline script JSON blobs
    for script in soup.find_all("script"):
        raw = script.string or ""
        if len(raw) < 50:
            continue

        for pattern in (
            r"__NEXT_DATA__\s*=\s*(\{[\s\S]+?\})\s*(?:;|</script>)",
            r"__INITIAL_DATA__\s*=\s*(\{[\s\S]+?\})\s*(?:;|</script>)",
            r"__PRELOADED_STATE__\s*=\s*(\{[\s\S]+?\})\s*(?:;|</script>)",
            r"window\.__DATA__\s*=\s*(\{[\s\S]+?\})\s*(?:;|</script>)",
            r"window\.__NUXT__\s*=\s*(\{[\s\S]+?\})\s*(?:;|</script>)",
        ):
            m = re.search(pattern, raw, re.S)
            if m:
                try:
                    blob = json.loads(m.group(1))
                except (json.JSONDecodeError, ValueError):
                    try:
                        inner = m.group(1).strip().strip('"').replace('\\"', '"')
                        blob = json.loads(inner)
                    except Exception:
                        continue
                _collect_jobs_from_json(blob, base_url, found, limit)
                if len(found) >= limit:
                    return found[:limit]

        stripped = raw.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                blob = json.loads(stripped)
                _collect_jobs_from_json(blob, base_url, found, limit)
            except (json.JSONDecodeError, ValueError):
                pass
            if len(found) >= limit:
                return found[:limit]

    for blob in (extra_blobs or []):
        if len(found) >= limit:
            break
        try:
            _collect_jobs_from_json(blob, base_url, found, limit)
        except Exception:
            continue

    return found[:limit]


def _collect_jobs_from_json(blob, base_url: str, out: list[PortalJob], limit: int, _depth: int = 0) -> None:
    if _depth > 12:
        return

    if isinstance(blob, dict):
        if _is_job_dict(blob):
            _add_json_job(blob, base_url, out, limit)
            return

        for key in ("jobs", "positions", "postings", "openings", "vacancies",
                    "results", "items", "data", "job_postings", "jobPostings",
                    "edges", "nodes", "opportunities", "roles", "listings",
                    "hits", "collection", "records", "feed", "content",
                    "payload", "objects", "documents"):
            if key in blob:
                _collect_jobs_from_json(blob[key], base_url, out, limit, _depth + 1)
                if len(out) >= limit:
                    return

        if "data" in blob and isinstance(blob["data"], dict):
            for inner_key in ("jobs", "positions", "postings", "openings", "search", "career"):
                if inner_key in blob["data"]:
                    _collect_jobs_from_json(blob["data"][inner_key], base_url, out, limit, _depth + 1)
                    if len(out) >= limit:
                        return

        for v in blob.values():
            if isinstance(v, (dict, list)):
                _collect_jobs_from_json(v, base_url, out, limit, _depth + 1)
                if len(out) >= limit:
                    return

    elif isinstance(blob, list):
        for item in blob:
            if isinstance(item, dict) and _is_job_dict(item):
                _add_json_job(item, base_url, out, limit)
                if len(out) >= limit:
                    return
            elif isinstance(item, (dict, list)):
                _collect_jobs_from_json(item, base_url, out, limit, _depth + 1)
                if len(out) >= limit:
                    return


def _is_job_dict(d: dict) -> bool:
    keys_lower = {k.lower() for k in d.keys()}
    title_keys = {"title", "name", "job_title", "position_title", "role",
                  "job_name", "position_name", "opening_title", "vacancy_title",
                  "position", "opening", "text", "label", "heading"}
    url_keys = {"url", "absolute_url", "job_url", "link", "href", "apply_url",
                "external_url", "posting_url", "application_url", "apply_link",
                "detail_url", "hosted_url", "external_path"}
    nested_url_keys = {"data", "fields", "attributes", "properties"}

    has_title = bool(keys_lower & title_keys)
    has_url = bool(keys_lower & url_keys)

    if has_title and "externalpath" in keys_lower:
        return True

    if has_title and not has_url:
        for nk in nested_url_keys:
            if nk in d and isinstance(d[nk], dict):
                nested_keys = {k.lower() for k in d[nk].keys()}
                if nested_keys & url_keys:
                    return True

    return has_title and has_url


def _add_json_job(d: dict, base_url: str, out: list[PortalJob], limit: int) -> None:
    if len(out) >= limit:
        return

    title_key = None
    for k in ("title", "name", "job_title", "position_title", "role",
              "job_name", "position_name", "opening_title", "vacancy_title",
              "position", "opening", "text", "label", "heading"):
        if k in d:
            title_key = k
            break
    title = str(d.get(title_key, "")).strip() if title_key else ""
    if not title or len(title) < 2:
        return

    url_raw = ""
    for k in ("url", "absolute_url", "job_url", "link", "href", "apply_url",
              "external_url", "posting_url", "application_url", "apply_link",
              "detail_url", "hosted_url"):
        val = d.get(k)
        if val:
            url_raw = str(val).strip()
            break

    if not url_raw:
        ext_path = d.get("external_path") or d.get("externalPath")
        if ext_path:
            url_raw = str(ext_path).strip()

    if not url_raw:
        for nk in ("data", "fields", "attributes", "properties"):
            nested = d.get(nk)
            if isinstance(nested, dict):
                for k in ("url", "absolute_url", "job_url", "link", "href", "apply_url", "external_url"):
                    val = nested.get(k)
                    if val:
                        url_raw = str(val).strip()
                        break
                if url_raw:
                    break

    if not url_raw:
        return

    if url_raw.startswith("http"):
        url = normalize_url(url_raw)
    elif url_raw.startswith("/"):
        url = normalize_url(urljoin(base_url, url_raw))
    else:
        url = normalize_url(urljoin(base_url, url_raw))

    location = ""
    for k in ("location", "location_name", "office", "city", "country", "region",
              "locations_text", "locationsText", "location_str"):
        val = d.get(k)
        if val:
            if isinstance(val, list):
                location = ", ".join(str(v) for v in val[:3])
            else:
                location = str(val).strip()
            break

    description = ""
    for k in ("description", "description_html", "summary", "snippet",
              "short_description", "content", "description_text"):
        val = d.get(k)
        if val:
            if isinstance(val, dict):
                description = str(val.get("text", "") or val.get("html", "") or "")
            else:
                description = str(val).strip()
            break

    out.append(PortalJob(title=title[:200], url=url, location=location, description=description[:2000]))


def _extract_generic_cards(soup, base_url: str, seen: set[str], limit: int) -> list[PortalJob]:
    """Generic card extraction using data attributes and common class patterns."""
    jobs: list[PortalJob] = []

    selectors = [
        '[data-job-id]', '[data-position-id]', '[data-vacancy-id]', '[data-employment-id]',
        '[data-testid*="job"]', '[data-testid*="position"]', '[data-cy*="job"]',
        '[class*="job-card"]', '[class*="JobCard"]', '[class*="jobCard"]',
        '[class*="job_listing"]', '[class*="job-listing"]', '[class*="job-item"]', '[class*="JobItem"]',
        '[class*="position-card"]', '[class*="PositionCard"]', '[class*="positionCard"]',
        '[class*="vacancy-item"]', '[class*="vacancy-card"]', '[class*="VacancyCard"]',
        '[class*="career-item"]', '[class*="career-card"]', '[class*="CareerCard"]',
        '[class*="opening-item"]', '[class*="opening-card"]', '[class*="role-card"]',
        '[class*="opportunity-card"]', '[class*="opportunity-item"]', '[class*="search-result"]',
        '[class*="searchResult"]', '[class*="job-result"]', '[class*="list-item"]',
        '[role="listitem"]',
        'li[class*="job"]', 'li[class*="position"]', 'li[class*="vacancy"]',
        'li[class*="opening"]', 'li[class*="role"]', 'li[class*="opportunity"]', 'li[class*="career"]',
        'article[class*="job"]', 'article[class*="position"]', 'article[class*="vacancy"]',
        'article[class*="opening"]', 'article[class*="career"]',
        'div[class*="job"]', 'div[class*="position"]', 'div[class*="vacancy"]',
        'div[class*="opening"]', 'div[class*="role"]', 'div[class*="opportunity"]', 'div[class*="career"]',
        'section[class*="job"]', 'section[class*="position"]', 'section[class*="vacancy"]',
        'section[class*="opening"]', 'section[class*="career"]',
    ]

    for selector in selectors:
        if len(jobs) >= limit:
            break
        try:
            containers = soup.select(selector)
        except Exception:
            continue

        for container in containers:
            if len(jobs) >= limit:
                break
            if _ancestor_has_bad_class(container):
                continue

            link = container.find("a", href=True)
            heading = container.find(["h1", "h2", "h3", "h4", "h5", "h6"])

            title = ""
            if heading:
                title = _clean_text(heading.get_text(" ", strip=True))
            if not title and link:
                title = _clean_text(link.get_text(" ", strip=True))
            if not title:
                title = _clean_text(container.get_text(" ", strip=True))[:120]
            if len(title) < 3:
                continue

            url = ""
            if link and link.get("href"):
                url = normalize_url(urljoin(base_url, link["href"].strip()))
            else:
                for attr in ("data-job-url", "data-url", "data-apply-url", "data-link",
                             "data-href", "data-job-id", "data-position-id", "data-vacancy-id"):
                    val = container.get(attr, "").strip()
                    if val:
                        if attr.startswith("data-job") and not val.startswith("http") and not val.startswith("/"):
                            url = normalize_url(urljoin(base_url, f"/jobs/{val}"))
                        else:
                            url = normalize_url(urljoin(base_url, val))
                        break

            if not url or url in seen or not _is_candidate_url(url):
                continue

            text = _clean_text(container.get_text(" ", strip=True))
            if not _looks_like_job(title, url, text):
                continue

            seen.add(url)
            jobs.append(PortalJob(title=title[:200], url=url, location=_guess_location(text)))

    return jobs


def _extract_generic_lists(soup, base_url: str, seen: set[str], limit: int) -> list[PortalJob]:
    """Extract from plain ul/ol lists that contain job indicators."""
    jobs: list[PortalJob] = []

    for list_tag in soup.find_all(["ul", "ol"]):
        if len(jobs) >= limit:
            break
        if _ancestor_has_bad_class(list_tag):
            continue

        list_text = list_tag.get_text(" ", strip=True).lower()
        has_job_indicator = any(kw in list_text for kw in [
            "engineer", "analyst", "manager", "developer", "designer",
            "specialist", "consultant", "director", "lead", "head",
            "coordinator", "intern", "graduate", "senior", "junior",
            "position", "vacancy", "opening", "role", "job",
            "stelle", "stellen", "vacature", "vacatures", "posizione", "posizioni",
            "empleo", "empleos", "offre", "offres", "poste", "postes",
        ])
        list_cls = " ".join(list_tag.get("class", [])).lower()
        has_job_class = any(kw in list_cls for kw in [
            "job", "position", "vacancy", "opening", "role", "career", "opportunity"
        ])
        if not has_job_indicator and not has_job_class:
            continue

        for li in list_tag.find_all("li", recursive=False):
            if len(jobs) >= limit:
                break

            link = li.find("a", href=True)
            if not link:
                continue

            href = link.get("href", "").strip()
            url = normalize_url(urljoin(base_url, href))
            if url in seen or not _is_candidate_url(url):
                continue

            text = _clean_text(li.get_text(" ", strip=True))
            title = _best_title(link, text)

            if len(title) < 3:
                continue
            if not _looks_like_job(title, url, text):
                continue

            seen.add(url)
            jobs.append(PortalJob(title=title[:200], url=url, location=_guess_location(text)))

    return jobs


def _extract_generic_anchors(soup, base_url: str, seen: set[str], limit: int) -> list[PortalJob]:
    """Final fallback: scan all anchors with loose filtering."""
    jobs: list[PortalJob] = []
    full_page_text = soup.get_text(" ", strip=True).lower()

    for a in soup.find_all("a", href=True):
        if len(jobs) >= limit:
            break
        if _ancestor_has_bad_class(a):
            continue

        href = a.get("href", "").strip()
        url = normalize_url(urljoin(base_url, href))
        if not _is_candidate_url(url) or url in seen:
            continue

        text = _clean_text(a.get_text(" ", strip=True))
        title = _best_title(a, text)

        if len(title) < 3:
            continue
        if not _looks_like_job(title, url, text):
            continue

        seen.add(url)
        jobs.append(PortalJob(title=title[:200], url=url, location=_guess_location(text)))

    return jobs


# ---------------------------------------------------------------------------
# Main extraction dispatcher
# ---------------------------------------------------------------------------
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
    """Extract job listings from HTML using platform-aware + generic strategies."""
    soup = BeautifulSoup(html or "", "lxml")
    jobs: list[PortalJob] = []
    seen: set[str] = set()

    # Pass 1: Platform-specific extraction (fast path)
    platform = _detect_platform(soup, base_url)
    if platform:
        logger.debug("Detected platform: %s for %s", platform, base_url)
        extractor = {
            "teamtailor": _extract_teamtailor,
            "personio": _extract_personio,
            "greenhouse": _extract_greenhouse,
            "lever": _extract_lever,
            "smartrecruiters": _extract_smartrecruiters,
            "workday": _extract_workday,
            "sap": _extract_sap,
            "icims": _extract_icims,
        }.get(platform)
        if extractor:
            platform_jobs = extractor(soup, base_url, limit)
            for job in platform_jobs:
                if job.url in seen:
                    continue
                if not _matches_filters(job.description, job.title, job.url, query, country, sponsorship_only, remote_filter):
                    continue
                seen.add(job.url)
                jobs.append(job)
            if jobs:
                logger.debug("Platform extractor (%s) found %d jobs for %s", platform, len(jobs), base_url)
                return jobs[:limit]

    # Pass 2: JSON blobs from inline scripts
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

    # Pass 3: Generic card extraction
    card_jobs = _extract_generic_cards(soup, base_url, seen, limit)
    for job in card_jobs:
        if not _matches_filters(job.description, job.title, job.url, query, country, sponsorship_only, remote_filter):
            continue
        seen.add(job.url)
        jobs.append(job)
    if len(jobs) >= limit:
        return jobs[:limit]

    # Pass 4: Generic list extraction
    list_jobs = _extract_generic_lists(soup, base_url, seen, limit - len(jobs))
    for job in list_jobs:
        if not _matches_filters(job.description, job.title, job.url, query, country, sponsorship_only, remote_filter):
            continue
        seen.add(job.url)
        jobs.append(job)
    if len(jobs) >= limit:
        return jobs[:limit]

    # Pass 5: Generic anchor fallback
    anchor_jobs = _extract_generic_anchors(soup, base_url, seen, limit - len(jobs))
    for job in anchor_jobs:
        if not _matches_filters(job.description, job.title, job.url, query, country, sponsorship_only, remote_filter):
            continue
        seen.add(job.url)
        jobs.append(job)

    return jobs[:limit]


# ---------------------------------------------------------------------------
# ATS link extraction from HTML
# ---------------------------------------------------------------------------
def extract_ats_links(base_url: str, html: str) -> list[str]:
    """Extract embedded ATS board links from a careers page."""
    soup = BeautifulSoup(html or "", "lxml")
    links: list[str] = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        full_url = normalize_url(urljoin(base_url, href))
        if ATS_LINK_RE.search(full_url):
            links.append(full_url)

    for tag in soup.find_all(["iframe", "frame"]):
        src = (tag.get("src") or tag.get("data-src") or "").strip()
        if not src:
            continue
        full_url = normalize_url(urljoin(base_url, src))
        if ATS_LINK_RE.search(full_url):
            links.append(full_url)

    for tag in soup.find_all(True):
        for attr, val in (tag.attrs or {}).items():
            if not attr.startswith("data-"):
                continue
            if not isinstance(val, str):
                continue
            if ATS_LINK_RE.search(val):
                full_url = normalize_url(urljoin(base_url, val) if val.startswith("/") else val)
                links.append(full_url)

    for match in ATS_LINK_RE.finditer(html or ""):
        start = max(0, match.start() - 120)
        end = min(len(html), match.end() + 220)
        snippet = html[start:end]
        url_match = re.search(r'''https?://[^\s"'<>]+''', snippet)
        if url_match:
            links.append(normalize_url(url_match.group(0)))

    return _dedupe(links)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def _is_candidate_url(url: str) -> bool:
    return bool(url and not SKIP_URL_RE.search(url))


def _ancestor_has_bad_class(node) -> bool:
    bad_indicators = {
        "nav", "navigation", "navbar", "menu", "header", "footer", "sidebar",
        "breadcrumb", "breadcrumbs", "toolbar", "tab-bar", "tabbar",
        "mega-menu", "megamenu", "flyout", "drawer", "offcanvas",
        "hero", "banner", "cta", "call-to-action", "promo", "promotion",
        "marketing", "subscribe", "newsletter", "social", "share",
        "cookie", "disclaimer", "legal", "terms", "privacy", "policy",
        "language", "lang-switcher", "locale", "country-selector",
        "search-form", "search-bar", "filter", "facet", "sort",
        "pagination", "pager", "load-more", "show-more",
        "login", "signin", "register", "account", "user-menu",
    }
    for ancestor in node.parents:
        if not hasattr(ancestor, "get"):
            continue
        cls = " ".join(ancestor.get("class", [])).lower()
        if not cls:
            continue
        for bad in bad_indicators:
            if bad in cls:
                return True
    return False


def _best_title(anchor, fallback_text: str = "") -> str:
    """Extract the best job title from an anchor element."""
    candidates = []

    if hasattr(anchor, "get"):
        for attr in ("data-title", "data-job-title", "data-position-name", "data-label", "data-role"):
            val = anchor.get(attr, "")
            if val:
                candidates.append(val)
        aria = anchor.get("aria-label", "")
        if aria:
            candidates.append(aria)
        title_attr = anchor.get("title", "")
        if title_attr:
            candidates.append(title_attr)

    anchor_text = _clean_text(anchor.get_text(" ", strip=True))
    if anchor_text and anchor_text.lower() not in GENERIC_CTAS:
        candidates.append(anchor_text)

    # Look for heading in parent container
    if hasattr(anchor, "find_parent"):
        for parent in anchor.parents:
            if getattr(parent, "name", "") in {"li", "div", "article", "section"}:
                heading = parent.find(["h1", "h2", "h3", "h4", "h5", "h6"])
                if heading:
                    candidates.append(heading.get_text(" ", strip=True))
                    break
                strong = parent.find(["strong", "b"])
                if strong:
                    candidates.append(strong.get_text(" ", strip=True))
                    break
                if parent != anchor:
                    break

    candidates.append(fallback_text)

    for candidate in candidates:
        candidate = _clean_text(candidate)
        if 3 <= len(candidate) <= 150 and candidate.lower() not in GENERIC_CTAS:
            return candidate

    return anchor_text[:200] if anchor_text else ""


def _looks_like_job(title: str, url: str, text: str = "") -> bool:
    """Permissive validation: accept any reasonable job title on a job-like URL."""
    title_lower = title.lower().strip()
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    if len(title_lower) < 3:
        return False

    # Reject known junk titles
    junk = {
        "", "learn more", "read more", "apply now", "view job", "view role",
        "open roles", "open positions", "open vacancies", "all jobs", "all roles",
        "all positions", "all vacancies", "show more", "see more", "search jobs",
        "search roles", "search positions", "browse jobs", "browse roles",
        "find jobs", "find a job", "explore jobs", "explore careers",
        "job search", "careers page", "view jobs", "view careers",
        "view all jobs", "see jobs", "see all jobs", "join the team",
        "join us", "join our team", "current openings", "current vacancies",
        "learn more about us", "details", "more details", "share", "save",
        "bookmark", "favorite", "create alert", "job alert", "upload cv",
        "upload resume", "manage preferences", "cookie settings",
        "all locations", "all departments", "view all", "see all",
    }
    if title_lower in junk:
        return False

    if title_lower in NAV_TITLE_BLACKLIST:
        return False

    if "language switcher" in title_lower or title_lower.startswith("switch to "):
        return False

    # Reject non-job URLs
    if re.search(r"/(about|blog|news|press|privacy|terms|contact|help|login|signup|register|cookie|legal)/", path_lower, re.I):
        return False

    # Accept ATS links immediately
    if ATS_LINK_RE.search(url):
        return True

    # Accept job path segments
    if JOB_PATH_SEGMENTS_RE.search(path_lower):
        if len(title_lower) >= 3:
            return True

    # Accept query params
    if JOB_QUERY_PARAMS_RE.search(url):
        if len(title_lower) >= 3:
            return True

    # Accept numeric IDs in path
    if re.search(r"/jobs?/\d{2,}", path_lower, re.I):
        if len(title_lower) >= 3:
            return True

    # Accept UUIDs in path (Lever style)
    if re.search(r"/jobs?/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", path_lower, re.I):
        if len(title_lower) >= 3:
            return True

    # Accept if title has a role keyword
    if ROLE_KEYWORDS_RE.search(title_lower):
        path_parts = [p for p in path_lower.strip("/").split("/") if p]
        if len(path_parts) >= 1:
            return True

    # Very permissive fallback
    if len(title_lower) >= 5:
        path_parts = [p for p in path_lower.strip("/").split("/") if p]
        if len(path_parts) >= 1 and len(path_parts[-1]) >= 3:
            return True

    return False


def _matches_filters(text, title, url, query, country, sponsorship_only, remote_filter):
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


def _guess_location(text: str) -> str:
    cleaned = _clean_text(text)
    for label in ("Location", "Office", "Based in", "Where", "Place"):
        match = re.search(rf"{label}\s*:?\s*([^|•\n]{2,80})", cleaned, re.I)
        if match:
            return match.group(1).strip()

    remote_patterns = [
        r"remote\s*[-–—:|•,/]\s*([a-z\s,]{2,50})",
        r"([a-z\s,]{2,50})\s*[-–—:|•,/]\s*remote",
        r"([a-z\s,]{2,50})\s*\(\s*remote\s*\)",
    ]
    for pat in remote_patterns:
        match = re.search(pat, cleaned, re.I)
        if match:
            loc = match.group(1).strip()
            loc = re.sub(r"^(in|from|at|for)\s+", "", loc, flags=re.I)
            if len(loc) >= 2 and not any(skip in loc.lower() for skip in ("only", "allowed", "friendly", "sponsorship")):
                return f"Remote - {loc.title()}"

    common_countries = {
        "united kingdom", "uk", "london", "manchester", "birmingham",
        "germany", "berlin", "munich", "frankfurt", "hamburg", "cologne", "stuttgart",
        "netherlands", "amsterdam", "rotterdam", "utrecht", "hague",
        "france", "paris", "lyon", "marseille",
        "sweden", "stockholm", "gothenburg", "malmo",
        "spain", "madrid", "barcelona", "valencia",
        "portugal", "lisbon", "porto",
        "poland", "warsaw", "krakow",
        "ireland", "dublin", "cork",
        "denmark", "copenhagen",
        "finland", "helsinki",
        "norway", "oslo",
        "switzerland", "zurich", "geneva", "basel",
        "austria", "vienna",
        "belgium", "brussels", "antwerp", "ghent",
        "italy", "rome", "milan", "turin",
        "czech republic", "czechia", "prague",
        "romania", "bucharest",
        "estonia", "tallinn",
        "latvia", "riga",
        "lithuania", "vilnius",
        "luxembourg",
        "united states", "usa", "us", "new york", "san francisco",
        "canada", "toronto", "vancouver", "montreal",
        "singapore"
    }

    found = []
    for word in re.findall(r"\b[a-zA-Z-]{3,25}\b", cleaned):
        if word.lower() in common_countries:
            found.append(word.title())

    if found:
        if "remote" in cleaned.lower():
            return f"Remote - {found[0]}"
        return found[0]

    return ""


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
