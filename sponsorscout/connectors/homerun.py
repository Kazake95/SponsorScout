"""
Homerun ATS connector.
https://homerun.co/

Homerun is an ATS popular with European tech startups. Public JSON API:
  https://{slug}.run.homerun.co/api/v1/jobs?page=N
Returns {"meta": {...}, "data": [{...}]}.
"""
from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html
logger = logging.getLogger(__name__)


class HomerunConnector(BaseConnector):
    ats_name = "homerun"

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
                api = f"https://{slug}.run.homerun.co/api/v1/jobs?page=1"
                try:
                    r = session.get(api, timeout=30,
                                    headers={"Accept": "application/json"})
                    r.raise_for_status()
                    payload = r.json()
                    items = payload.get("data") or []
                    if isinstance(items, list) and items:
                        jobs = []
                        for job in items:
                            loc = job.get("location") or {}
                            if isinstance(loc, dict):
                                city = loc.get("city", "")
                                country_code = loc.get("country_code", "") or loc.get("country", "")
                                location = ", ".join(filter(None, [city, country_code]))
                            else:
                                location = str(loc or "")
                            # Strip HTML from description
                            desc = job.get("description") or job.get("summary") or ""
                            url = normalize_url(
                                job.get("url") or job.get("apply_url") or
                                f"https://{slug}.run.homerun.co/jobs/{job.get('id', '')}"
                            )
                            jobs.append({
                                "external_id": str(job.get("id", "")),
                                "title": job.get("title", "") or job.get("name", ""),
                                "company": company["name"],
                                "country": company.get("country", ""),
                                "location": location,
                                "url": url,
                                "description": desc,
                                "ats_source": "homerun",
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
        m = re.search(r"([a-zA-Z0-9_-]+)\.run\.homerun\.co", url)
        if m:
            return m.group(1)
        m = re.search(r"homerun\.co/([a-zA-Z0-9_-]+)", url)
        return m.group(1) if m else ""
