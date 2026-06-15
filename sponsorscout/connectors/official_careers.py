"""
Official Careers connector — HTML scraping for custom career pages.
Handles companies that don't use a standard ATS or embed an ATS on their own domain.
Extracts job links from HTML with smart filtering to reduce noise.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.portal_search import crawl_official_careers


class OfficialCareersConnector(BaseConnector):
    ats_name = "official_careers"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # Use the context manager so the connection pool is
        # closed when the function returns.
        with http_session() as session:
            company_name = company.get("name", "")
            hq_country   = company.get("country", "")
            # Determine if this is a verified URL (when classed directly from CSV)
            expected_ats = company.get("ats_type", "").lower()
            is_verified = (expected_ats == "official_careers")
            try:
                portal_jobs, ats_links = crawl_official_careers(
                    session,
                    careers_url,
                    max_pages=10,
                    limit=300,
                    is_verified=is_verified,
                )
                # Log detected ATS links for debugging
                if ats_links:
                    logger.debug(
                        "Official careers for %s found ATS links: %s",
                        company_name, ats_links[:3],
                    )
            except Exception as exc:
                logger.exception("Connector %s error for %s", self.ats_name, company_name)
                return []

            if not portal_jobs:
                logger.warning(
                    "Official careers for %s returned 0 jobs from %s "
                    "(possible bot-blocked or JS-rendered page)",
                    company_name, careers_url,
                )

            return [
                {
                    "external_id": job.url,
                    "title": job.title,
                    "company": company_name,
                    "country": hq_country,
                    "location": job.location,
                    "url": job.url,
                    "description": job.description or job.title,
                    "ats_source": "official_careers",
                }
                for job in portal_jobs
            ]
