
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
    # Only remove tracking params; preserve original order.
    # Sorting query params breaks order-sensitive ATS backends (SAP SuccessFactors,
    # Oracle Taleo, some Workday tenants) that treat param order as meaningful.
    filtered = [(k, v) for k, v in query_items if k.lower() not in TRACKING_PARAMS]
    # Do NOT sort — keep the original query-param order from the source URL.
    # Preserve fragments — many career pages use them for content selection
    # (e.g. careers.insify.nl/#jobs, amazon.jobs/…#section). Stripping the
    # fragment breaks those URLs entirely.
    fragment = parsed.fragment  # keep as-is; don't lowercase (some SPAs are case-sensitive)
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            urlencode(filtered, doseq=True),
            fragment,
        )
    )
