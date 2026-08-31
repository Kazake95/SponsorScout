"""
Freshteam connector (by Freshworks).
https://www.freshteam.com/

Public API: https://{slug}.freshteam.com/api/job_posts
Returns a list of job postings.
"""
from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html, strip_html
logger = logging.getLogger(__name__)


class FreshteamConnector(BaseConnector):
    ats_name = "freshteam"

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
                api = f"https://{slug}.freshteam.com/api/job_posts"
                try:
                    r = session.get(api, timeout=30,
                                    headers={"Accept": "application/json"})
                    r.raise_for_status()
                    items = r.json()
                    if isinstance(items, list) and items:
                        jobs = []
                        for job in items:
                            loc = job.get("job_location") or {}
                            if isinstance(loc, dict):
                                city = loc.get("city", "")
                                country = loc.get("country", "")
                                location = ", ".join(filter(None, [city, country]))
                            else:
                                location = str(loc or "")
                            desc = job.get("description") or ""
                            url = normalize_url(
                                job.get("url") or
                                f"https://{slug}.freshteam.com/jobs/{job.get('id', '')}"
                            )
                            jobs.append({
                                "external_id": str(job.get("id", "")),
                                "title": job.get("title", ""),
                                "company": company["name"],
                                "country": company.get("country", ""),
                                "location": location,
                                "url": url,
                                "description": strip_html(desc),
                                "ats_source": "freshteam",
                            })
                        if jobs:
                            return jobs
                except Exception as exc:
                    logger.exception("Connector %s error", self.ats_name)
                    # Fall through: scanner._scan_company turns the empty return
                    # into an ats_health record_failure() call.

            # Fallback: HTML scrape
            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.exception("Connector %s error", self.ats_name)
                return []

    def _extract_slug(self, url: str) -> str:
        m = re.search(r"([a-zA-Z0-9_-]+)\.freshteam\.com", url)
        return m.group(1) if m else ""
