from __future__ import annotations
import logging
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html


logger = logging.getLogger(__name__)
class RecruiteeConnector(BaseConnector):
    ats_name = "recruitee"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            # Recruitee API: /api/offers  or  careers.companyslug.recruitee.com/api/offers
            api_candidates = [
                f"{careers_url}/api/offers?limit=100",
                f"{careers_url}/api/v1/offers",
            ]
            for api in api_candidates:
                try:
                    r = session.get(api, timeout=30)
                    r.raise_for_status()
                    payload = r.json()
                    items = payload.get("offers") or (payload if isinstance(payload, list) else [])
                    if isinstance(items, list) and items:
                        jobs = []
                        for job in items:
                            location = ", ".join(filter(None, [
                                job.get("city", ""),
                                job.get("country_code", "") or job.get("country", ""),
                            ]))
                            url = normalize_url(job.get("careers_url") or job.get("url") or careers_url)
                            jobs.append({
                                "external_id": str(job.get("id", "")),
                                "title": job.get("title", ""),
                                "company": company["name"],
                                "country": company.get("country", ""),
                                "location": location,
                                "url": url,
                                "description": job.get("description", "") or "",
                                "ats_source": "recruitee",
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
