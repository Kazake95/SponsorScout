"""
Lightweight HTTP-based page fetcher (replaces playwright dependency).
Falls back gracefully — no headless browser required.

BUGFIX: previous version used `build_session()` without closing the session
after the request, leaking one connection pool per call. Freshness checks
call this function for every job URL, so a 500-job verification run would
open 500 stale connections and potentially exhaust the OS's ephemeral-port
range. Now we use the `http_session()` context manager which guarantees
`session.close()` is always called, even on exception.
"""
from __future__ import annotations
import re
from sponsorscout.core.http_client import http_session


def fetch_rendered_html(url: str, wait_ms: int = 0) -> dict:
    """Fetch a URL and return {url, title, html}. Uses requests (no browser)."""
    try:
        with http_session() as session:
            r = session.get(url, timeout=20)
            html = r.text or ""
            # Extract <title> without BS4 import cycle
            title = ""
            if "<title" in html.lower():
                m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
                title = m.group(1).strip() if m else ""
            return {"url": r.url, "title": title, "html": html, "status": r.status_code}
    except Exception as exc:
        return {"url": url, "title": "", "html": "", "status": 0, "error": str(exc)}
