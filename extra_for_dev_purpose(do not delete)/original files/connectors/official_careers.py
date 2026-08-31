"""
Official Careers connector — HTML scraping for custom career pages.

Extracts job listings directly from the verified career page provided
in the CSV, utilizing Playwright to handle dynamic JS, accordions,
and layouts without running recursive or external sub-path guessing.
"""
from __future__ import annotations
import logging

from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.portal_search import crawl_official_careers, extract_jobs_from_html
from sponsorscout.services.browser_fetcher import fetch_rendered_html

logger = logging.getLogger(__name__)


class OfficialCareersConnector(BaseConnector):
    ats_name = "official_careers"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []

        company_name = company.get("name", "")
        hq_country   = company.get("country", "")
        expected_ats = company.get("ats_type", "").lower()
        is_verified  = (expected_ats == "official_careers")

        portal_jobs = []
        ats_links: list[str] = []

        # ── Pass 1: Crawl ONLY the direct verified URL using Playwright JS rendering ──────
        with http_session() as session:
            try:
                portal_jobs, ats_links, _ = crawl_official_careers(
                    careers_url,
                    max_pages=1,  # Strict single-page parsing limit
                    limit=300,
                    is_verified=is_verified,
                )
                if ats_links:
                    logger.debug(
                        "Official careers for %s found ATS links: %s",
                        company_name, ats_links[:3],
                    )
            except Exception as exc:
                logger.exception("Connector %s pass-1 error for %s", self.ats_name, company_name)

        if portal_jobs:
            return self._format_jobs(portal_jobs, company_name, hq_country)

        # ── Playwright Direct Render Fallback on the EXACT URL ──
        # If crawl failed to return jobs (due to lazy rendering or slow loading times),
        # we retry directly on the exact careers_url with a longer wait budget.
        try:
            rendered = fetch_rendered_html(careers_url, wait_ms=6500, timeout=90, force_browser=True)
            rendered_html = rendered.get("html") or ""
            if rendered_html:
                captured = rendered.get("captured_json") or []
                page_jobs = extract_jobs_from_html(
                    careers_url, rendered_html, limit=300, extra_json_blobs=captured,
                )
                if page_jobs:
                    logger.info(
                        "Direct Playwright render yielded %d jobs for %s",
                        len(page_jobs), company_name,
                    )
                    return self._format_jobs(page_jobs, company_name, hq_country)
        except Exception as exc:
            logger.debug("Direct Playwright fallback render failed for %s: %s", careers_url, exc)

        logger.warning(
            "Official careers for %s returned 0 jobs from %s",
            company_name, careers_url,
        )
        return []

    @staticmethod
    def _format_jobs(portal_jobs, company_name: str, hq_country: str) -> list[dict]:
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