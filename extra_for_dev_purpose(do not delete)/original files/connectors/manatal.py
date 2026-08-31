"""
Manatal connector.
https://manatal.com/

Public API: https://api.manatal.com/api/v3/career-page/{slug}/jobs/
Note: Manatal's public API requires a token in most cases; this connector
falls back to HTML scraping of the career page.
"""
from __future__ import annotations
import logging
import re
import json as _json
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html
logger = logging.getLogger(__name__)


class ManatalConnector(BaseConnector):
    ats_name = "manatal"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            # Manatal's career page is public HTML — scrape the embedded job JSON.
            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                html = r.text
                # Many Manatal pages embed a JSON blob of jobs in a <script id="..."> tag.
                m = re.search(
                    r'<script[^>]*id="(?:__NEXT_DATA__|job-data|initial-data)"[^>]*>(.*?)</script>',
                    html, re.DOTALL | re.IGNORECASE,
                )
                if m:
                    try:
                        blob = _json.loads(m.group(1))
                        items = (
                            blob.get("props", {}).get("pageProps", {}).get("jobs")
                            or blob.get("jobs")
                            or []
                        )
                        if isinstance(items, list) and items:
                            jobs = []
                            for job in items:
                                if not isinstance(job, dict):
                                    continue
                                loc = job.get("location") or job.get("city") or ""
                                desc = job.get("description") or ""
                                url = normalize_url(
                                    job.get("url") or job.get("link") or
                                    f"{careers_url}/{job.get('id', job.get('slug', ''))}"
                                )
                                jobs.append({
                                    "external_id": str(job.get("id", "") or job.get("slug", "")),
                                    "title": job.get("title", "") or job.get("name", ""),
                                    "company": company["name"],
                                    "country": company.get("country", ""),
                                    "location": str(loc),
                                    "url": url,
                                    "description": desc,
                                    "ats_source": "manatal",
                                })
                            if jobs:
                                return jobs
                    except Exception as exc:
                        logger.exception("Connector %s error", self.ats_name)
                        # Fall through: scanner._scan_company turns the empty return
                        # into an ats_health record_failure() call.
                # Fallback: link scrape
                return parse_links_from_html(html, careers_url, company["name"])
            except Exception as exc:
                logger.exception("Connector %s error", self.ats_name)
                return []
