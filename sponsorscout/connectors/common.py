
from __future__ import annotations
import logging
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from sponsorscout.core.url_normalizer import normalize_url
logger = logging.getLogger(__name__)


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&(?:#x?[0-9a-fA-F]+|[a-zA-Z]+);")


def strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities.

    BUGFIX: this was previously exposed as a private function (`_strip_html`).
    Connectors like Ashby, Freshteam, and SmartRecruiters (HTML responses)
    need plain text for downstream sponsorship / keyword matching. The
    leading underscore signalled "private to the module" but other modules
    were importing it anyway. Renamed to `strip_html` so the public API is
    honest about who depends on it.

    The original `_strip_html` symbol is kept as an alias so any external
    code that was importing it under the old name still works.
    """
    if not text:
        return ""
    # Fast path: if there are no < or &, no work to do.
    if "<" not in text and "&" not in text:
        return text
    try:
        soup = BeautifulSoup(text, "lxml")
        plain = soup.get_text(" ", strip=True)
    except Exception as exc:
        logger.exception("strip_html error")
        # Fall back to regex strip if BS4 chokes on malformed HTML.
        plain = _HTML_TAG_RE.sub(" ", text)
        plain = _HTML_ENTITY_RE.sub(" ", plain)
    return re.sub(r"\s+", " ", plain).strip()


# Backwards-compat alias for any third-party import of the old private name.
_strip_html = strip_html


def parse_links_from_html(html: str, base_url: str, company_name: str):
    soup = BeautifulSoup(html, "lxml")
    out = []
    seen = set()
    for a in soup.select("a[href]"):
        text = " ".join(a.get_text(" ", strip=True).split())
        href = a.get("href", "")
        if not href:
            continue
        href = urljoin(base_url, href)
        href = normalize_url(href)
        if href in seen:
            continue
        seen.add(href)
        if any(k in (text + " " + href).lower() for k in ["job", "career", "role", "opening", "vacancy", "apply"]):
            out.append({
                "external_id": href,
                "title": text or "Open role",
                "company": company_name,
                "country": "",
                "location": "",
                "url": href,
                "description": text,
                "ats_source": "official_careers",
            })
    return out
