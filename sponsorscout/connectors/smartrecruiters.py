from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html, strip_html


logger = logging.getLogger(__name__)
class SmartRecruitersConnector(BaseConnector):
    ats_name = "smartrecruiters"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            # SmartRecruiters public API: /jobs?limit=100
            slug = self._extract_slug(careers_url)
            if slug:
                api_candidates = [
                    f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
                    f"{careers_url}/jobs?limit=100",
                ]
                for api in api_candidates:
                    try:
                        r = session.get(api, timeout=30)
                        r.raise_for_status()
                        payload = r.json()
                        items = payload.get("content") or payload.get("jobs") or []
                        if isinstance(items, list) and items:
                            jobs = []
                            for job in items:
                                loc = job.get("location", {}) or {}
                                location = ", ".join(filter(None, [loc.get("city", ""), loc.get("country", "")]))
                                url = normalize_url(job.get("ref") or job.get("postingHref") or careers_url)
                                # B6 fix: strip HTML from description.
                                job_ad = job.get("jobAd")
                                raw_desc = ""
                                if isinstance(job_ad, dict):
                                    sections = job_ad.get("sections", {})
                                    if isinstance(sections, dict):
                                        jd = sections.get("jobDescription", {})
                                        if isinstance(jd, dict):
                                            raw_desc = jd.get("text", "") or ""
                                # Fallback to top-level description if any
                                raw_desc = raw_desc or job.get("description", "") or ""
                                jobs.append({
                                    "external_id": str(job.get("id", "")),
                                    "title": job.get("name", "") or job.get("title", ""),
                                    "company": company["name"],
                                    "country": company.get("country", ""),
                                    "location": location,
                                    "url": url,
                                    "description": strip_html(raw_desc),
                                    "ats_source": "smartrecruiters",
                                })
                            if jobs:
                                return jobs
                    except Exception as exc:
                        logger.exception("Connector %s error", self.ats_name)
                        # Fall through: scanner._scan_company turns the empty return
                        # into an ats_health record_failure() call.

            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.exception("Connector %s error", self.ats_name)
                return []

    def _extract_slug(self, url: str) -> str:
        # https://careers.smartrecruiters.com/CompanyName  or  https://jobs.smartrecruiters.com/CompanyName
        m = re.search(r"smartrecruiters\.com/([^/?#]+)", url)
        return m.group(1) if m else ""
