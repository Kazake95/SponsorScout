from __future__ import annotations
import logging
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html


logger = logging.getLogger(__name__)
class TeamtailorConnector(BaseConnector):
    ats_name = "teamtailor"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            # Teamtailor JSON API: append .json or use /jobs endpoint
            api_candidates = [
                f"{careers_url}/jobs.json",
                f"{careers_url}/jobs",
            ]
            for api in api_candidates:
                try:
                    r = session.get(api, timeout=30, headers={"Accept": "application/json"})
                    r.raise_for_status()
                    payload = r.json()
                    items = payload.get("jobs") or (payload if isinstance(payload, list) else [])
                    if isinstance(items, list) and items:
                        jobs = []
                        for job in items:
                            attrs = job.get("attributes", job)
                            location = attrs.get("remote-status", "") or attrs.get("location", "") or ""
                            url = normalize_url(attrs.get("career-site-url") or job.get("links", {}).get("careersite") or careers_url)
                            jobs.append({
                                "external_id": str(job.get("id", "")),
                                "title": attrs.get("title", ""),
                                "company": company["name"],
                                "country": company.get("country", ""),
                                "location": location,
                                "url": url,
                                "description": attrs.get("body", "") or "",
                                "ats_source": "teamtailor",
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
