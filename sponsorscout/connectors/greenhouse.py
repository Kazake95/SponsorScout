from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html


logger = logging.getLogger(__name__)
class GreenhouseConnector(BaseConnector):
    ats_name = "greenhouse"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is closed
        # when the function returns. The previous build_session() form
        # leaked one Session per call → dozens of open pools after a scan.
        with http_session() as session:
            # Extract board token from careers_url or use explicit ats_board_token field
            token = company.get("ats_board_token") or self._extract_token(careers_url)

            if token:
                # Official Greenhouse public jobs API
                api_candidates = [
                    f"https://boards.greenhouse.io/api/v1/boards/{token}/jobs?content=true",
                    f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
                    # Some companies use job_posts endpoint
                    f"https://boards.greenhouse.io/api/v1/boards/{token}/job_posts?live=true",
                ]
                for api in api_candidates:
                    try:
                        r = session.get(api, timeout=30)
                        r.raise_for_status()
                        payload = r.json()
                        jobs = []
                        raw_jobs = payload.get("jobs") or payload.get("job_posts") or []
                        if isinstance(raw_jobs, list) and raw_jobs:
                            for job in raw_jobs:
                                loc = job.get("location") or {}
                                location = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                                url = normalize_url(job.get("absolute_url") or job.get("url") or careers_url)
                                jobs.append({
                                    "external_id": str(job.get("id", "")),
                                    "title": job.get("title", ""),
                                    "company": company["name"],
                                    "country": company.get("country", ""),
                                    "location": location,
                                    "url": url,
                                    "description": job.get("content", "") or "",
                                    "ats_source": "greenhouse",
                                })
                            if jobs:
                                return jobs
                    except Exception as exc:
                        logger.exception("Connector %s error", self.ats_name)
                        pass

            # Fallback: scrape the careers page HTML
            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.exception("Connector %s error", self.ats_name)
                return []

    def _extract_token(self, url: str) -> str:
        """Extract Greenhouse board token from URL patterns:
        - boards.greenhouse.io/{token}
        - job-boards.greenhouse.io/{token}
        - {company}.greenhouse.io  (sometimes)
        """
        # Direct board URL: boards.greenhouse.io/stripe
        m = re.search(r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)", url)
        if m:
            return m.group(1)
        # Sometimes careers URL is custom domain — can't extract token, fall through to HTML
        return ""
