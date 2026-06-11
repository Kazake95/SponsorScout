from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html, strip_html


logger = logging.getLogger(__name__)
class AshbyConnector(BaseConnector):
    ats_name = "ashby"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context-manager form so the connection pool is
        # always closed — build_session() leaks otherwise.
        with http_session() as session:
            # Ashby public API: POST https://api.ashbyhq.com/posting-api/job-board/{slug}
            slug = self._extract_slug(careers_url)
            if slug:
                api = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
                try:
                    r = session.post(api, json={"includeCompensation": False}, timeout=30,
                                     headers={"Content-Type": "application/json"})
                    r.raise_for_status()
                    payload = r.json()
                    postings = payload.get("jobPostings") or []
                    if isinstance(postings, list) and postings:
                        jobs = []
                        for job in postings:
                            loc = job.get("primaryLocation", {})
                            location = ", ".join(filter(None, [
                                loc.get("city", ""),
                                loc.get("countryCode", ""),
                            ])) if isinstance(loc, dict) else str(loc)
                            url = normalize_url(job.get("jobUrl") or careers_url)
                            # B6 fix: strip HTML tags from the description so
                            # downstream sponsorship/keyword matches work on the
                            # plain-text body, not on "<p>visa</p> sponsorship".
                            raw_desc = (
                                job.get("descriptionPlain")
                                or job.get("description")
                                or job.get("descriptionHtml")
                                or ""
                            )
                            jobs.append({
                                "external_id": str(job.get("id", "")),
                                "title": job.get("title", ""),
                                "company": company["name"],
                                "country": company.get("country", ""),
                                "location": location,
                                "url": url,
                                "description": strip_html(raw_desc),
                                "ats_source": "ashby",
                            })
                        if jobs:
                            return jobs
                except Exception as exc:
                    logger.exception("Connector %s error", self.ats_name)
                    pass

            # Fallback HTML scrape
            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.exception("Connector %s error", self.ats_name)
                return []

    def _extract_slug(self, url: str) -> str:
        # https://jobs.ashbyhq.com/CompanySlug
        m = re.search(r"ashbyhq\.com/([^/?#]+)", url)
        return m.group(1) if m else ""
