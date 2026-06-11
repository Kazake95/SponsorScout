from __future__ import annotations
import logging
import re
import time
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html


logger = logging.getLogger(__name__)
class ICIMSConnector(BaseConnector):
    """
    iCIMS connector.
    iCIMS has no standard public API — each enterprise client has a custom setup.
    We support two patterns:
    1. iCIMS Talent Cloud portal (career.icims.com): ?mode=job_api&iis=...
    2. Custom subdomain (company.icims.com): HTML scraping with job link detection
    Falls back to HTML scraping in all cases.
    """
    ats_name = "icims"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            # iCIMS portal pattern: https://careers.icims.com/jobs/search?pr=...&in_iframe=1
            # or: https://company.icims.com/jobs/search
            portal_id = self._extract_portal_id(careers_url)
            if portal_id:
                # B7 fix: previous version sent `iisn=SponsorScout` (a string) as
                # the iCIMS source-name param. iCIMS rejects anything that isn't
                # a short numeric token, causing many portals to return 400 and
                # silently fall through to the HTML scrape. Now we omit iisn and
                # use a real numeric session id surrogate (millisecond timestamp
                # truncated to fit iCIMS' documented 8-char limit).
                session_id = str(int(time.time() * 1000))[-8:]
                api = (
                    f"https://careers.icims.com/jobs/search"
                    f"?pr={portal_id}&schemaId=&jId=&cf=&rc=10"
                    f"&iis={session_id}&mode=job_api"
                )
                try:
                    r = session.get(api, timeout=30)
                    if r.status_code == 200:
                        try:
                            payload = r.json()
                            items = (payload.get("searchResults") or
                                     payload.get("jobs") or
                                     (payload if isinstance(payload, list) else []))
                            if isinstance(items, list) and items:
                                return self._parse_items(items, company, careers_url)
                        except Exception as exc:
                            logger.exception("Connector %s error", self.ats_name)
                            pass
                except Exception as exc:
                    logger.exception("Connector %s error", self.ats_name)
                    pass

            # Fallback: HTML link scraping
            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.exception("Connector %s error", self.ats_name)
                return []

    def _extract_portal_id(self, url: str) -> str:
        m = re.search(r"pr=(\d+)", url)
        return m.group(1) if m else ""

    def _parse_items(self, items: list, company: dict, base_url: str) -> list:
        jobs = []
        for job in items:
            location = ", ".join(filter(None, [
                job.get("city", ""), job.get("state", ""), job.get("country", ""),
            ]))
            url = normalize_url(job.get("detailUrl") or job.get("url") or base_url)
            jobs.append({
                "external_id": str(job.get("jobId", "") or job.get("id", "")),
                "title": job.get("title", ""),
                "company": company["name"],
                "country": company.get("country", ""),
                "location": location,
                "url": url,
                "description": job.get("jobDescription", "") or "",
                "ats_source": "icims",
            })
        return jobs
