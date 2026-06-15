
from __future__ import annotations

from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "gh_src", "lever-source", "source", "ref", "referrer", "fbclid", "gclid",
}

def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [(k, v) for k, v in query_items if k.lower() not in TRACKING_PARAMS]
    filtered.sort()
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            urlencode(filtered, doseq=True),
            "",
        )
    )
