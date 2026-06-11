from __future__ import annotations
import logging
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html


logger = logging.getLogger(__name__)
class BambooHRConnector(BaseConnector):
    ats_name = "bamboohr"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            # BambooHR public API: /jobs/list.json (no auth for public boards)
            slug = self._extract_slug(careers_url)
            if slug:
                api_candidates = [
                    f"https://{slug}.bamboohr.com/jobs/embed2/list",
                    f"https://api.bamboohr.com/api/gateway.php/{slug}/v1/applicant_tracking/jobs",
                ]
                for api in api_candidates:
                    try:
                        r = session.get(api, timeout=30, headers={"Accept": "application/json"})
                        r.raise_for_status()
                        payload = r.json()
                        items = payload.get("result") or payload.get("jobs") or (payload if isinstance(payload, list) else [])
                        if isinstance(items, list) and items:
                            jobs = []
                            for job in items:
                                dept = job.get("departmentLabel", "") or ""
                                location = job.get("location", {}).get("city", "") if isinstance(job.get("location"), dict) else str(job.get("location", ""))
                                url = normalize_url(job.get("url") or f"https://{slug}.bamboohr.com/jobs/{job.get('id', '')}")
                                jobs.append({
                                    "external_id": str(job.get("id", "")),
                                    "title": job.get("jobOpeningName", "") or job.get("title", ""),
                                    "company": company["name"],
                                    "country": company.get("country", ""),
                                    "location": location,
                                    "url": url,
                                    "description": dept,
                                    "ats_source": "bamboohr",
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
        import re
        m = re.search(r"([a-zA-Z0-9_-]+)\.bamboohr\.com", url)
        return m.group(1) if m else ""
