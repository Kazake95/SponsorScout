from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html


logger = logging.getLogger(__name__)
class JobviteConnector(BaseConnector):
    ats_name = "jobvite"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            # Jobvite public feed: https://jobs.jobvite.com/companyslug/feed?format=json
            slug = self._extract_slug(careers_url)
            if slug:
                api_candidates = [
                    f"https://jobs.jobvite.com/{slug}/feed?format=json",
                    f"{careers_url}/feed?format=json",
                ]
                for api in api_candidates:
                    try:
                        r = session.get(api, timeout=30)
                        r.raise_for_status()
                        payload = r.json()
                        postings = payload.get("requisitions") or payload.get("jobs") or []
                        if isinstance(postings, list) and postings:
                            jobs = []
                            for job in postings:
                                url = normalize_url(job.get("applyLink") or job.get("url") or careers_url)
                                jobs.append({
                                    "external_id": str(job.get("id", "") or job.get("jobId", "")),
                                    "title": job.get("title", ""),
                                    "company": company["name"],
                                    "country": company.get("country", ""),
                                    "location": job.get("location", ""),
                                    "url": url,
                                    "description": job.get("description", "") or "",
                                    "ats_source": "jobvite",
                                })
                            if jobs:
                                return jobs
                    except Exception as exc:
                        logger.exception("Connector %s error", self.ats_name)
                        pass

            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.exception("Connector %s error", self.ats_name)
                return []

    def _extract_slug(self, url: str) -> str:
        m = re.search(r"jobvite\.com/([^/?#]+)", url)
        return m.group(1) if m else ""
