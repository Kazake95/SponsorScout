from __future__ import annotations
import logging
import re
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.core.location_country import country_from_location

# Country name normalization map
COUNTRY_MAP = {
    "united kingdom": "United Kingdom", "uk": "United Kingdom", "u.k.": "United Kingdom", "gb": "United Kingdom",
    "germany": "Germany", "de": "Germany", "deutschland": "Germany",
    "netherlands": "Netherlands", "the netherlands": "Netherlands", "nl": "Netherlands", "holland": "Netherlands",
    "france": "France", "fr": "France",
    "sweden": "Sweden", "se": "Sweden",
    "spain": "Spain", "es": "Spain",
    "portugal": "Portugal", "pt": "Portugal",
    "poland": "Poland", "pl": "Poland",
    "ireland": "Ireland", "ie": "Ireland",
    "denmark": "Denmark", "dk": "Denmark",
    "finland": "Finland", "fi": "Finland",
    "norway": "Norway", "no": "Norway",
    "switzerland": "Switzerland", "ch": "Switzerland",
    "austria": "Austria", "at": "Austria",
    "belgium": "Belgium", "be": "Belgium",
    "italy": "Italy", "it": "Italy",
    "czech republic": "Czech Republic", "czechia": "Czech Republic", "cz": "Czech Republic",
    "romania": "Romania", "ro": "Romania",
    "united states": "United States", "usa": "United States", "us": "United States",
    "canada": "Canada", "ca": "Canada",
    "australia": "Australia", "au": "Australia",
    "singapore": "Singapore", "sg": "Singapore",
    "remote": "Remote",
}

# Title normalization: strip common noise
TITLE_NOISE = re.compile(
    r"\s*[\(\[](?:m/f|f/m|m/w/d|f/m/x|any gender|all genders?|m/f/d|f/m/d)[\)\]]\s*",
    re.IGNORECASE,
)

# Experience-level detection (v0.4.2 feature).
# We use simple keyword matching on the job title because that's where
# EU/global ATS boards tend to encode seniority (the description is
# usually more verbose / multi-lingual and harder to grep).
#
# Order matters: we check LEAD before SENIOR because "Lead Senior
# Engineer" is a thing, and we check EXEC last because "Chief" almost
# never appears in regular titles but is unambiguous when it does.
_EXPERIENCE_PATTERNS = [
    # ── BUGFIX (v0.4.2) ────────────────────────────────────────
    # BUGFIX: previous version was missing this whole block, so all
    # jobs normalised to '' and the Search tab's Experience filter had
    # nothing to match against. Now every normalised job gets one of
    # 'intern', 'entry', 'mid', 'senior', 'lead', 'exec' or '' (unknown).
    # ────────────────────────────────────────────────────────────
    ("intern",  re.compile(r"\b(intern(ship)?|praktikant|praktikum|stage|stageplaats|werkstudent)\b", re.I)),
    ("entry",   re.compile(r"\b(junior|entry[- ]level|graduate|new grad|0[\s-]*2\s*years?( experience)?|1[\s-]*2\s*years?( experience)?)\b", re.I)),
    ("mid",     re.compile(r"\b(mid[- ]level|2[\s-]*5\s*years?( experience)?|3[\s-]*5\s*years?( experience)?|engineer ii\b|specialist\b)\b", re.I)),
    ("senior",  re.compile(r"\b(senior|sr\.?\b|5\+?\s*years?( experience)?|7\+?\s*years?( experience)?|experienced\b|staff\b|principal\b)\b", re.I)),
    ("lead",    re.compile(r"\b(lead|staff\b|principal\b|head of\b|manager\b)\b", re.I)),
    ("exec",    re.compile(r"\b(chief|cto\b|ceo\b|cfo\b|cmo\b|coo\b|vp\b|vice president|director|head of)\b", re.I)),
]


def detect_experience_level(title: str) -> str:
    """Classify a job title into an experience bucket.

    Returns one of: 'intern', 'entry', 'mid', 'senior', 'lead', 'exec', or ''.
    The first matching bucket wins, so we order patterns from most
    specific (intern / exec) to least (mid).
    """
    if not title:
        return ""
    for level, pat in _EXPERIENCE_PATTERNS:
        if pat.search(title):
            return level
    return ""


def normalize_country(raw: str) -> str:
    if not raw:
        return ""
    key = raw.strip().lower().rstrip(".").replace(".", "")
    return COUNTRY_MAP.get(key, raw.strip().title())


def normalize_title(raw: str) -> str:
    if not raw:
        return ""
    title = TITLE_NOISE.sub(" ", raw)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def normalize_location(raw: str) -> str:
    if not raw:
        return ""
    # Check for remote signals
    low = raw.lower()
    if "remote" in low:
        return raw.strip()
    # Trim excessive whitespace
    return re.sub(r"\s+", " ", raw).strip()


logger = logging.getLogger(__name__)


def normalize_job(raw: dict, source_type: str, source_name: str, fallback_company: str = "") -> dict:
    hq_country = normalize_country(raw.get("country", "") or "")
    location_raw = normalize_location(raw.get("location", "") or "")

    # Derive job's actual country from its location string.
    # Fall back to company HQ country only when location gives no signal.
    job_country = country_from_location(location_raw, fallback=hq_country)

    title = normalize_title(raw.get("title", ""))
    company = (raw.get("company", "") or fallback_company or "").strip()
    url = normalize_url(raw.get("url", ""))
    external_id = raw.get("external_id", "") or raw.get("id", "")

    if not company:
        logger.debug("Job payload missing company field: %r", raw)
        raise ValueError("Job payload missing required company")
    if not title:
        logger.debug("Job payload missing title field: %r", raw)
        raise ValueError("Job payload missing required title")
    if not url:
        logger.debug("Job payload missing url field: %r", raw)
        raise ValueError("Job payload missing required url")

    return {
        "external_id": external_id,
        "title": title,
        "company": company,
        "country": job_country,
        "location": location_raw,
        "url": url,
        "description": (raw.get("description", "") or ""),
        "ats_source": raw.get("ats_source", "") or source_name,
        "source_type": source_type,
        "source_name": source_name,
        "experience_level": detect_experience_level(title),
    }
