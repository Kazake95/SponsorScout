"""
Company Discovery Engine
Finds new companies automatically using multiple strategies:
1. ATS-specific search pages (no scraping needed — structured URLs)
2. Direct ATS board probing from known slugs
3. Search-engine fallback (Google, DuckDuckGo, and EU-oriented engines)
4. Common ATS pattern probing for a given company name
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse
from sponsorscout.core.http_client import http_session
from sponsorscout.core.persistence import save_company
from sponsorscout.core.portal_search import crawl_official_careers, extract_ats_links, likely_careers_urls
from sponsorscout.core.url_normalizer import normalize_url

logger = logging.getLogger(__name__)

SEARCH_ENGINE_ALIASES = {
    "all": ["google", "duckduckgo", "startpage", "qwant", "ecosia", "mojeek", "swisscows"],
    "eu": ["startpage", "qwant", "ecosia", "mojeek", "swisscows"],
}

SEARCH_ENGINES = {
    "google": {
        "url": "https://www.google.com/search",
        "params": lambda q, country: {"q": q, "hl": "en", "num": "20", "pws": "0"},
        "selectors": ["a[href]"],
        "source": "google",
    },
    "duckduckgo": {
        "url": "https://html.duckduckgo.com/html/",
        "params": lambda q, country: {"q": q, "kl": _ddg_region(country)},
        "selectors": ["a.result__url", "a.result__a", "a[href]"],
        "source": "duckduckgo",
    },
    # EU-oriented / Europe-based fallbacks. These are HTML result pages, so
    # they are best-effort and may change markup; extraction intentionally
    # falls back to all anchors and then filters for official ATS URLs.
    "startpage": {
        "url": "https://www.startpage.com/sp/search",
        "params": lambda q, country: {"query": q, "language": "english", "cat": "web"},
        "selectors": ["a.w-gl__result-title", "a.result-link", "a[href]"],
        "source": "startpage",
    },
    "qwant": {
        "url": "https://www.qwant.com/",
        "params": lambda q, country: {"q": q, "t": "web", "locale": _qwant_locale(country)},
        "selectors": ["a[href]"],
        "source": "qwant",
    },
    "ecosia": {
        "url": "https://www.ecosia.org/search",
        "params": lambda q, country: {"q": q},
        "selectors": ["a.result__link", "a[href]"],
        "source": "ecosia",
    },
    "mojeek": {
        "url": "https://www.mojeek.com/search",
        "params": lambda q, country: {"q": q},
        "selectors": ["a.ob", "a[href]"],
        "source": "mojeek",
    },
    "swisscows": {
        "url": "https://swisscows.com/en/web",
        "params": lambda q, country: {"query": q},
        "selectors": ["a[href]"],
        "source": "swisscows",
    },
}

ATS_SEARCH_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "smartrecruiters.com",
    "workable.com",
    "myworkdayjobs.com",
    "personio.com",
    "recruitee.com",
    "teamtailor.com",
    "bamboohr.com",
    "jobvite.com",
    "icims.com",
    "breezy.hr",
    "freshteam.com",
    "homerun.co",
    "welcometothejungle.com",
    "manatal.com",
]

# ATS fingerprints: pattern → ats_name
ATS_PATTERNS = [
    (r"greenhouse\.io|boards\.greenhouse\.io|job-boards\.greenhouse\.io", "greenhouse"),
    (r"lever\.co/[a-zA-Z0-9_-]+/jobs|jobs\.lever\.co|api\.lever\.co", "lever"),
    (r"workable\.com|apply\.workable\.com", "workable"),
    (r"ashbyhq\.com|jobs\.ashbyhq\.com", "ashby"),
    (r"teamtailor\.com", "teamtailor"),
    (r"personio\.(?:com|de)", "personio"),
    (r"smartrecruiters\.com", "smartrecruiters"),
    (r"myworkdayjobs\.com", "workday"),
    (r"bamboohr\.com", "bamboohr"),
    (r"recruitee\.com", "recruitee"),
    (r"jobvite\.com", "jobvite"),
    (r"icims\.com", "icims"),
    # Added for the data-base.xlsx expansion
    (r"run\.homerun\.co|homerun\.co", "homerun"),
    (r"freshteam\.com", "freshteam"),
    (r"breezy\.hr", "breezy"),
    (r"welcometothejungle\.com", "welcometothejungle"),
    (r"manatal\.com", "manatal"),
    (r"pinpointhq\.com", "pinpoint"),
    (r"tribepad\.com", "tribepad"),
    (r"occupop\.com", "occupop"),
    (r"jobylon\.com", "jobylon"),
    (r"varbi\.com", "varbi"),
    (r"homerun\.co/([a-zA-Z0-9_-]+)", "homerun"),
    (r"careers\.softgarden\.de|softgarden\.de", "softgarden"),
    (r"join\.com", "join"),
    (r"jobbase\.io|prescreen\.io", "prescreen"),
    (r"recruitingapp\.umantis\.com|umantis\.com", "umantis"),
    (r"jobs\.kenjo\.io|kenjo\.io", "kenjo"),
    (r"d-vinci\.de", "d.vinci"),
    (r"onlyifyme\.com|onlyify\.com", "onlyify"),
]

# Known ATS search/listing pages that return structured data
# These are public no-auth endpoints — query them directly
ATS_SEARCH_ENDPOINTS = [
    # Greenhouse: filter by keyword in job title, returns JSON
    {
        "ats": "greenhouse",
        "url_template": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false",
        "probe_tokens": [],  # filled dynamically from registry
    },
    # Lever: all postings for a company slug, JSON
    {
        "ats": "lever",
        "url_template": "https://api.lever.co/v0/postings/{token}?mode=json",
        "probe_tokens": [],
    },
    # Ashby: POST endpoint
    {
        "ats": "ashby",
        "url_template": "https://api.ashbyhq.com/posting-api/job-board/{token}",
        "probe_tokens": [],
    },
]

# Curated list of well-known sponsoring companies NOT in seed CSV
# Grouped by ATS so we can probe them directly without web search
DISCOVERY_CANDIDATES = {
    "greenhouse": [
        ("Intercom", "intercom"), ("Figma", "figma"), ("Brex", "brex"),
        ("Plaid", "plaid"), ("Coinbase", "coinbase"), ("Robinhood", "robinhood"),
        ("Duolingo", "duolingo"), ("Airtable", "airtable"), ("Checkr", "checkr"),
        ("Scale AI", "scaleai"), ("Calm", "calm"), ("Patreon", "patreon"),
        ("Kraken", "kraken"), ("Chainalysis", "chainalysis"), ("Deel", "deel"),
        ("Remote", "remote"), ("Papaya Global", "papayaglobal"),
        ("Lemonnade", "lemonade"), ("Pipe", "pipe"), ("Ramp", "ramp"),
        ("Mercury", "mercury"), ("Braze", "braze"), ("Amplitude", "amplitude"),
        ("Domo", "domo"), ("Mimecast", "mimecast"), ("Contentstack", "contentstack"),
        ("Sprinklr", "sprinklr"), ("Podium", "podium"), ("Lucid", "lucidsoftware"),
        ("Canva", "canva"), ("Atlassian", "atlassian"), ("Xero", "xero"),
        ("Culture Amp", "cultureamp"), ("SafetyCulture", "safetyculture"),
        ("Samsara", "samsara"), ("Verkada", "verkada"), ("Cribl", "cribl"),
        ("LaunchDarkly", "launchdarkly"), ("Snyk", "snyk"), ("Dynatrace", "dynatrace"),
        ("JFrog", "jfrog"), ("monday.com", "mondaycom"), ("WalkMe", "walkme"),
        ("ClickUp", "clickup"), ("Loom (Atlassian)", "loom"), ("Webflow", "webflow"),
        ("Pendo", "pendo"), ("Gainsight", "gainsight"), ("Freshworks", "freshworks"),
        ("Chargebee", "chargebee"), ("CleverTap", "clevertap"), ("Postman", "postmanapiplatform"),
        ("Hasura", "hasura"), ("Cockroach Labs", "cockroachlabs"), ("Timescale", "timescale"),
        ("PlanetScale", "planetscale"), ("SingleStore", "singlestore"),
        ("Starburst", "starburst"), ("dbt Labs", "dbtlabs"), ("Fivetran", "fivetran"),
        ("Airbyte", "airbyte"), ("Hightouch", "hightouch"), ("Census", "census"),
        ("Hex", "hex"), ("Metabase", "metabase"), ("Grafana", "grafana"),
        ("Datadog", "datadog"), ("New Relic", "newrelic"), ("PagerDuty", "pagerduty"),
        ("OpsRamp", "opsramp"), ("Miro", "realtimeboard"), ("Productboard", "productboard"),
        ("Maze", "maze"), ("UserTesting", "usertesting"), ("Hotjar", "hotjar"),
        ("Heap", "heap"), ("FullStory", "fullstory"), ("Contentsquare", "contentsquare"),
        ("Algolia", "algolia"), ("Yotpo", "yotpo"), ("Gorgias", "gorgias"),
        ("Recharge", "rechargepayments"), ("Bold Commerce", "boldcommerce"),
        ("Nosto", "nosto"), ("Klaviyo", "klaviyo"), ("Omnisend", "omnisend"),
        ("ActiveCampaign", "activecampaign"), ("Drip", "drip"), ("Iterable", "iterable"),
        ("Customer.io", "customerioapps"), ("Braze", "braze"),
    ],
    "lever": [
        ("Vercel", "vercel"), ("Netlify", "netlify"), ("Render", "render"),
        ("Railway", "railway"), ("Fly.io", "fly"), ("Supabase", "supabase"),
        ("PlanetScale", "planetscale"), ("Neon", "neondatabase"),
        ("Upstash", "upstash"), ("Turso", "chiselstrike"), ("Convex", "convex"),
        ("Clerk", "clerk"), ("Stytch", "stytch"), ("WorkOS", "workos"),
        ("Ory", "orylabs"), ("Auth0 (Okta)", "okta"), ("Frontegg", "frontegg"),
        ("Descope", "descope"), ("ZITADEL", "zitadel"),
        ("Liveblocks", "liveblocks"), ("PartyKit", "partykit"),
        ("Inngest", "inngest"), ("Trigger.dev", "triggerdev"),
        ("Temporal", "temporal"), ("Restate", "restate"),
        ("Buf", "buf"), ("Apollo GraphQL", "apollographql"),
        ("Hasura", "hasura"), ("Stellate", "stellate"),
        ("Grafbase", "grafbase"), ("Wundergraph", "wundergraph"),
        ("Sentry", "sentry"), ("Axiom", "axiomhq"), ("Baselime", "baselime"),
        ("Highlight", "highlight"), ("LogRocket", "logrocket"),
        ("OpenReplay", "openreplay"), ("Jam", "jam"),
        ("Linear", "linear"), ("Height", "height"), ("Plane", "plane"),
        ("Shortcut", "shortcut"), ("Fibery", "fibery"),
        ("Notion", "notion"), ("Coda", "coda"), ("Almanac", "almanac"),
        ("GitBook", "gitbook"), ("Slite", "slite"), ("Slab", "slab"),
        ("Confluence (Atlassian)", "atlassian"),
        ("Docusign", "docusign"), ("PandaDoc", "pandadoc"), ("Ironclad", "ironcladapp"),
        ("Dropbox Sign", "dropbox"), ("DocuWare", "docuware"),
        ("Rippling", "rippling"), ("Lattice", "lattice"), ("Culture Amp", "cultureamp"),
        ("Leapsome", "leapsome"), ("Betterworks", "betterworks"),
        ("15five", "fifteenfive"), ("Reflektive", "reflektive"),
    ],
    "ashby": [
        ("Linear", "linear"), ("Loom", "loom"), ("Airbyte", "airbyte"),
        ("Retool", "retool"), ("dbt Labs", "dbtlabs"), ("Incident.io", "incident.io"),
        ("Cal.com", "calcom"), ("Rows", "rows"), ("Raycast", "raycast"),
        ("Warp", "warp"), ("Fig", "fig"), ("Zed", "zed"),
        ("Cursor", "cursor"), ("Pieces", "pieces"), ("Codeium", "codeium"),
        ("Tabnine", "tabnine"), ("Sourcegraph", "sourcegraph"), ("Swimm", "swimm"),
        ("Mintlify", "mintlify"), ("Readme", "readme"), ("Stoplight", "stoplight"),
        ("Speakeasy", "speakeasy"), ("Stainless", "stainless"),
        ("Merge", "merge"), ("Apideck", "apideck"), ("Paragon", "useparagon"),
        ("Tray.io", "tray"), ("n8n", "n8n"), ("Pipedream", "pipedream"),
        ("Zapier", "zapier"), ("Make (Integromat)", "make"),
        ("Qdrant", "qdrant"), ("Weaviate", "weaviate"), ("Pinecone", "pinecone"),
        ("Milvus/Zilliz", "zilliz"), ("Chroma", "chroma"), ("LanceDB", "lancedb"),
        ("Cohere", "cohere"), ("Anthropic", "anthropic"), ("Mistral", "mistral"),
        ("Together AI", "togetherai"), ("Fireworks AI", "fireworksai"),
        ("Replicate", "replicate"), ("Modal", "modal"), ("Banana", "banana"),
        ("Baseten", "baseten"), ("Beam", "beam"), ("Cerebrium", "cerebrium"),
        ("Hugging Face", "huggingface"), ("Lightning AI", "lightnin"),
        ("Weights & Biases", "wandb"), ("Neptune.ai", "neptune"),
        ("Comet ML", "cometml"), ("Evidently AI", "evidentlyai"),
        ("Arize AI", "arize"), ("Fiddler AI", "fiddler"), ("Arthur AI", "arthur"),
    ],
}


def detect_ats(url: str, html: str = "") -> str:
    """Detect ATS type from URL or page HTML."""
    text = (url + " " + html).lower()
    for pattern, ats_name in ATS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ats_name
    return "official_careers"


def _extract_company_name(url: str, ats: str) -> str:
    """Best-effort company name extraction from ATS URL slug."""
    patterns = {
        "greenhouse": r"(?:greenhouse\.io|job-boards\.greenhouse\.io|boards\.greenhouse\.io)/([^/?#]+)",
        "lever": r"(?:jobs|careers)\.lever\.co/([^/?#]+)",
        "workable": r"apply\.workable\.com/([^/?#]+)",
        "ashby": r"ashbyhq\.com/([^/?#]+)",
        "teamtailor": r"([a-zA-Z0-9_-]+)\.teamtailor\.com",
        "personio": r"([a-zA-Z0-9_-]+)\.(?:jobs\.)?personio\.(?:com|de)",
        "smartrecruiters": r"(?:careers|jobs)\.smartrecruiters\.com/([^/?#]+)",
        "workday": r"([a-zA-Z0-9_-]+)\.wd\d+\.myworkdayjobs\.com",
        "bamboohr": r"([a-zA-Z0-9_-]+)\.bamboohr\.com",
        "recruitee": r"([a-zA-Z0-9_-]+)\.recruitee\.com",
        "jobvite": r"jobs\.jobvite\.com/([^/?#]+)",
        "icims": r"([a-zA-Z0-9_-]+)\.icims\.com",
    }
    pattern = patterns.get(ats, r"//(?:careers|jobs)\.([^./?#]+)")
    m = re.search(pattern, url, re.IGNORECASE)
    if m:
        slug = m.group(1)
        return slug.replace("-", " ").replace("_", " ").title()
    return ""


logger = logging.getLogger(__name__)

def discover_companies_from_curated(
    query: str, country: str = "", limit: int = 30
) -> list[dict]:
    """
    Primary discovery strategy: probe curated ATS slugs directly.
    No web search needed — hits the real ATS APIs.
    Filters by query keyword match against company name.
    """
    results = []
    query_lower = query.lower()
    seen_names = set()

    with http_session() as session:
        for ats, candidates in DISCOVERY_CANDIDATES.items():
            if len(results) >= limit:
                break
            for company_name, slug in candidates:
                if len(results) >= limit:
                    break
                # Filter: if query looks like a role/skill, always include;
                # if query looks like a company name, filter by it
                role_keywords = ["analyst", "engineer", "developer", "designer", "manager",
                                 "data", "python", "java", "backend", "frontend", "full stack",
                                 "devops", "cloud", "ml", "ai", "product", "finance", "sales",
                                 "marketing", "operations", "remote", "senior", "junior", "lead"]
                query_is_role = any(kw in query_lower for kw in role_keywords) or len(query.split()) > 1
                if not query_is_role and query_lower not in company_name.lower():
                    continue
                if company_name in seen_names:
                    continue

                # Build the ATS URL
                if ats == "greenhouse":
                    careers_url = f"https://boards.greenhouse.io/{slug}"
                    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
                elif ats == "lever":
                    careers_url = f"https://jobs.lever.co/{slug}"
                    api_url = f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1"
                elif ats == "ashby":
                    careers_url = f"https://jobs.ashbyhq.com/{slug}"
                    api_url = None  # POST endpoint, skip probe here
                else:
                    continue

                # Probe the API to confirm the board exists and has jobs
                try:
                    if ats == "ashby":
                        r = session.post(
                            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                            json={"includeCompensation": False},
                            timeout=10,
                            headers={"Content-Type": "application/json"},
                        )
                    else:
                        r = session.get(api_url, timeout=10)

                    if r.status_code == 200:
                        try:
                            payload = r.json()
                            items = (payload.get("jobs") or payload.get("jobPostings") or
                                     (payload if isinstance(payload, list) else []))
                            count = len(items) if isinstance(items, list) else 0
                        except ValueError as exc:
                            logger.debug(
                                "Curated probe JSON parse failed for %s/%s: %s",
                                ats,
                                company_name,
                                exc,
                            )
                            count = 0

                        if count > 0:
                            seen_names.add(company_name)
                            results.append({
                                "careers_url": normalize_url(careers_url),
                                "ats_type": ats,
                                "ats_board_token": slug,
                                "company_name": company_name,
                                "source": "curated_probe",
                            })
                except Exception as exc:
                    logger.exception(
                        "Curated probe failed for %s/%s", ats, company_name
                    )
                time.sleep(0.15)

    return results


def discover_companies_from_search(
    query: str,
    country: str = "",
    limit: int = 20,
    domains: list[str] | None = None,
    sponsorship_only: bool = False,
    remote_filter: str = "All",
    search_engine: str = "eu",
) -> list[dict]:
    """
    Discover companies using multiple strategies in order:
    1. Curated ATS probe (fast, reliable, no web search needed)
    2. Search-engine fallback across Google, DuckDuckGo, and EU-oriented engines
    Returns list of candidate company dicts with detected ATS.
    """
    # Strategy 1: Curated probe (works even without web search access)
    results = discover_companies_from_curated(query, country, limit=limit)

    # Strategy 2: user-supplied domains or career URLs. This is the most
    # reliable path for expanding into new EU companies because it probes
    # the real careers page, follows likely /jobs variants, and detects
    # embedded ATS boards before falling back to HTML job extraction.
    if domains and len(results) < limit:
        results.extend(
            discover_companies_from_portals(
                domains,
                query=query,
                country=country,
                limit=limit - len(results),
                sponsorship_only=sponsorship_only,
                remote_filter=remote_filter,
            )
        )

    if results:
        return _dedupe_candidates(results)[:limit]

    # Strategy 3: Search-engine fallback. This is intentionally last because
    # search engines change HTML often and may throttle automated requests.
    if len(results) < limit:
        results.extend(
            discover_companies_from_search_engines(
                query,
                country=country,
                limit=limit - len(results),
                search_engine=search_engine,
            )
        )

    return _dedupe_candidates(results)[:limit]


def discover_companies_from_search_engines(
    query: str,
    country: str = "",
    limit: int = 20,
    search_engine: str = "eu",
) -> list[dict]:
    """Discover ATS/company board URLs via configured web search engines."""
    engines = _resolve_search_engines(search_engine)
    search_query = _build_search_query(query, country)
    results: list[dict] = []
    with http_session() as session:
        for engine_name in engines:
            if len(results) >= limit:
                break
            engine = SEARCH_ENGINES.get(engine_name)
            if not engine:
                continue
            try:
                resp = session.get(
                    engine["url"],
                    params=engine["params"](search_query, country),
                    timeout=15,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0 Safari/537.36"
                        ),
                        "Accept-Language": _accept_language(country),
                    },
                )
                if resp.status_code >= 400:
                    logger.debug("%s search returned HTTP %s", engine_name, resp.status_code)
                    continue
                for href in _extract_search_result_urls(resp.text, engine["selectors"]):
                    ats = detect_ats(href)
                    if ats == "official_careers":
                        continue
                    results.append({
                        "careers_url": normalize_url(href),
                        "ats_type": ats,
                        "ats_board_token": _extract_company_name(href, ats).lower().replace(" ", ""),
                        "company_name": _extract_company_name(href, ats),
                        "source": engine["source"],
                    })
                    if len(_dedupe_candidates(results)) >= limit:
                        break
            except Exception as exc:
                logger.exception("%s discovery search failed for query %r", engine_name, query)
            time.sleep(0.4)
    return _dedupe_candidates(results)[:limit]


def discover_companies_from_portals(
    domains_or_urls: list[str],
    query: str = "",
    country: str = "",
    limit: int = 20,
    sponsorship_only: bool = False,
    remote_filter: str = "All",
) -> list[dict]:
    """Discover ATS boards or HTML job portals from supplied domains/URLs."""
    results: list[dict] = []
    with http_session() as session:
        for target in domains_or_urls:
            if len(results) >= limit:
                break
            for url in likely_careers_urls(target)[:10]:
                if len(results) >= limit:
                    break
                try:
                    resp = session.get(url, timeout=15, allow_redirects=True)
                    if resp.status_code >= 400 or len(resp.text or "") < 200:
                        continue
                except Exception as exc:
                    logger.debug("Portal discovery probe failed for %s: %s", url, exc)
                    continue

                final_url = normalize_url(getattr(resp, "url", url) or url)
                ats_links = extract_ats_links(final_url, resp.text)
                if ats_links:
                    for ats_url in ats_links:
                        ats = detect_ats(ats_url)
                        results.append({
                            "careers_url": ats_url,
                            "ats_type": ats,
                            "ats_board_token": _extract_company_name(ats_url, ats).lower().replace(" ", ""),
                            "company_name": _extract_company_name(ats_url, ats),
                            "source": "portal_ats_link",
                        })
                        if len(results) >= limit:
                            break
                    continue

                portal_jobs, _, _ = crawl_official_careers(
                    final_url,
                    query=query,
                    country=country,
                    sponsorship_only=sponsorship_only,
                    remote_filter=remote_filter,
                    max_pages=4,
                    limit=20,
                )
                if portal_jobs:
                    results.append({
                        "careers_url": final_url,
                        "ats_type": "official_careers",
                        "ats_board_token": "",
                        "company_name": _company_name_from_domain(final_url),
                        "source": "portal_html",
                        "matched_jobs": len(portal_jobs),
                    })
                    break
                time.sleep(0.1)
    return _dedupe_candidates(results)[:limit]


def auto_register_companies(conn, candidates: list[dict], country: str = "") -> list[dict]:
    """
    Given candidates from discover_companies_from_search(),
    save them to the DB. Returns list of newly registered companies.
    """
    registered = []

    for cand in candidates:
        url = cand.get("careers_url", "")
        ats = cand.get("ats_type", "official_careers")
        name = cand.get("company_name") or _extract_company_name(url, ats)
        if not name or not url:
            continue

        company = {
            "name": name,
            "country": country or "",
            "ats_type": ats,
            "ats_board_token": cand.get("ats_board_token", ""),
            "careers_url": url,
            "industry": "",
            "sponsorship_history_score": 0,
            "english_friendly_score": 80,
            "remote_score": 0,
        }
        try:
            save_company(conn, company)
            registered.append(company)
        except Exception as exc:
            logger.exception("Failed to auto-register company %s: %s", name, exc)
        time.sleep(0.1)

    return registered


def find_careers_url(company_domain: str) -> Optional[str]:
    """Try to find the careers page for a given domain."""
    with http_session() as session:
        for url in likely_careers_urls(company_domain):
            try:
                r = session.get(url, timeout=12, allow_redirects=True)
                if r.status_code == 200 and len(r.text) > 500:
                    ats_links = extract_ats_links(r.url, r.text)
                    return ats_links[0] if ats_links else normalize_url(r.url)
            except Exception as exc:
                logger.exception("Careers URL probe failed for %s: %s", company_domain, exc)
            time.sleep(0.2)
    return None


def _company_name_from_domain(url: str) -> str:
    host = urlparse(url if re.match(r"^https?://", url, re.I) else f"https://{url}").netloc
    host = re.sub(r"^(www|jobs|careers)\.", "", host)
    name = host.split(".", 1)[0]
    return name.replace("-", " ").replace("_", " ").title()


def _build_search_query(query: str, country: str = "") -> str:
    parts = [query.strip() or "software engineer", "visa sponsorship jobs"]
    if country:
        parts.append(country)
    site_terms = " OR ".join(f"site:{domain}" for domain in ATS_SEARCH_DOMAINS)
    parts.append(f"({site_terms})")
    return " ".join(parts)


def _resolve_search_engines(search_engine: str) -> list[str]:
    requested = (search_engine or "all").strip().lower()
    if requested in SEARCH_ENGINE_ALIASES:
        return SEARCH_ENGINE_ALIASES[requested]
    engines = [part.strip().lower() for part in requested.split(",") if part.strip()]
    return [engine for engine in engines if engine in SEARCH_ENGINES] or SEARCH_ENGINE_ALIASES["all"]


def _extract_search_result_urls(html: str, selectors: list[str]) -> list[str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "lxml")
    urls: list[str] = []
    for selector in selectors:
        for anchor in soup.select(selector):
            href = anchor.get("href", "")
            clean_url = _clean_search_href(href)
            if clean_url and detect_ats(clean_url) != "official_careers":
                urls.append(clean_url)
    return _dedupe_url_list(urls)


def _clean_search_href(href: str) -> str:
    href = (href or "").strip()
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return ""

    if href.startswith("//"):
        href = f"https:{href}"

    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    for key in ("q", "url", "u", "uddg", "target"):
        if key in query and query[key]:
            candidate = unquote(query[key][0])
            if candidate.startswith("http"):
                href = candidate
                break

    if href.startswith("/url?"):
        query = parse_qs(urlparse(href).query)
        candidate = (query.get("q") or query.get("url") or [""])[0]
        href = unquote(candidate)

    if not href.startswith("http"):
        return ""
    if any(blocked in href.lower() for blocked in ("google.com/search", "accounts.google", "preferences", "cache:")):
        return ""
    return normalize_url(href)


def _dedupe_url_list(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def _accept_language(country: str = "") -> str:
    mapping = {
        "germany": "de-DE,de;q=0.9,en;q=0.8",
        "netherlands": "nl-NL,nl;q=0.9,en;q=0.8",
        "france": "fr-FR,fr;q=0.9,en;q=0.8",
        "ireland": "en-IE,en;q=0.9",
        "spain": "es-ES,es;q=0.9,en;q=0.8",
        "portugal": "pt-PT,pt;q=0.9,en;q=0.8",
        "italy": "it-IT,it;q=0.9,en;q=0.8",
        "sweden": "sv-SE,sv;q=0.9,en;q=0.8",
        "denmark": "da-DK,da;q=0.9,en;q=0.8",
        "finland": "fi-FI,fi;q=0.9,en;q=0.8",
    }
    return mapping.get((country or "").strip().lower(), "en-GB,en;q=0.9")


def _ddg_region(country: str = "") -> str:
    mapping = {
        "germany": "de-de",
        "netherlands": "nl-nl",
        "france": "fr-fr",
        "ireland": "ie-en",
        "spain": "es-es",
        "portugal": "pt-pt",
        "italy": "it-it",
        "sweden": "se-sv",
        "denmark": "dk-da",
        "finland": "fi-fi",
        "united kingdom": "uk-en",
    }
    return mapping.get((country or "").strip().lower(), "wt-wt")


def _qwant_locale(country: str = "") -> str:
    mapping = {
        "germany": "de_DE",
        "netherlands": "nl_NL",
        "france": "fr_FR",
        "spain": "es_ES",
        "italy": "it_IT",
        "united kingdom": "en_GB",
    }
    return mapping.get((country or "").strip().lower(), "en_GB")


def _dedupe_candidates(candidates: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    result: list[dict] = []
    for candidate in candidates:
        key = (
            normalize_url(candidate.get("careers_url", "")),
            (candidate.get("ats_type", "") or "").lower(),
        )
        if not key[0] or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result
