"""
Welcome to the Jungle connector.
https://www.welcometothejungle.com/

Public API: https://api.welcometothejungle.com/api/v1/organizations/{slug}/jobs
Returns {"jobs": [...]}.

BUGFIX (2024-Q4): previously this module had broken indentation (a leftover
from a bad refactor) and would not even import — `ast.parse` raised
`IndentationError: unindent does not match any outer indentation level` at
line 30. Because the class was registered in `sponsorscout/connectors/__init__.py`,
the entire `sponsorscout.connectors` package import failed at app startup,
so the app crashed on first launch. The method body has been fully rewritten
below with consistent 4-space indentation and verified to import cleanly.
"""
from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html

logger = logging.getLogger(__name__)

class WTTJConnector(BaseConnector):
    ats_name = "welcometothejungle"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            slug = company.get("ats_board_token") or self._extract_slug(careers_url)
            if slug:
                api = f"https://api.welcometothejungle.com/api/v1/organizations/{slug}/jobs"
                try:
                    r = session.get(api, timeout=30,
                                    headers={"Accept": "application/json"})
                    r.raise_for_status()
                    payload = r.json()
                    items = payload.get("jobs") if isinstance(payload, dict) else payload
                    if isinstance(items, list) and items:
                        jobs = []
                        for job in items:
                            offices = job.get("offices") or []
                            location = ", ".join(offices) if isinstance(offices, list) else str(offices)
                            desc = job.get("description") or job.get("summary") or ""
                            url = normalize_url(
                                job.get("url") or job.get("link") or
                                f"https://www.welcometothejungle.com/jobs/{slug}/{job.get('slug', '')}"
                            )
                            jobs.append({
                                "external_id": str(job.get("id", "") or job.get("slug", "")),
                                "title": job.get("name", "") or job.get("title", ""),
                                "company": company["name"],
                                "country": company.get("country", ""),
                                "location": location,
                                "url": url,
                                "description": desc,
                                "ats_source": "welcometothejungle",
                            })
                        if jobs:
                            return jobs
                except Exception as exc:
                    logger.exception("Connector %s error", self.ats_name)
                    pass

            # Fallback: HTML scrape
            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.exception("Connector %s error", self.ats_name)
                return []

    def _extract_slug(self, url: str) -> str:
        m = re.search(r"welcometothejungle\.com/([a-zA-Z0-9_-]+)", url)
        if m and m.group(1) not in ("en", "fr", "de", "es", "it", "companies", "jobs"):
            return m.group(1)
        return ""
