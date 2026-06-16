"""
Official Careers connector — HTML scraping for custom career pages.

Handles companies that don't use a standard ATS or embed an ATS on
their own domain.  When the first ``crawl_official_careers`` pass
returns 0 jobs (typical for SPA / JS-heavy career pages), the
connector retries with progressively more aggressive strategies:

  1. Re-crawl with ``max_pages=12`` (more sub-paths)
  2. Try alternate sub-paths that commonly host job listings
  3. Direct Playwright render of the career URL with longer wait times
"""
from __future__ import annotations
import logging
from urllib.parse import urljoin, urlparse

from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.portal_search import crawl_official_careers, extract_jobs_from_html
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.services.browser_fetcher import fetch_rendered_html

logger = logging.getLogger(__name__)

# Common sub-paths that SPA career sites often redirect to or hide jobs under.
_RETRY_SUB_PATHS = [
    "/careers/search",
    "/careers/all-jobs",
    "/careers/all-roles",
    "/careers/find-a-job",
    "/jobs",
    "/jobs/search",
    "/open-positions",
    "/search-jobs",
]


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

        # ── Pass 1: Standard crawl with slightly more pages ──────
        with http_session() as session:
            try:
                portal_jobs, ats_links = crawl_official_careers(
                    session,
                    careers_url,
                    max_pages=12,
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

        # ── Pass 2: Try alternate sub-paths via direct Playwright ──
        logger.info(
            "Official careers for %s: 0 jobs from %s — trying alternate sub-paths",
            company_name, careers_url,
        )
        parsed = urlparse(careers_url)
        root = f"{parsed.scheme}://{parsed.netloc}"

        for sub_path in _RETRY_SUB_PATHS:
            candidate = normalize_url(urljoin(root, sub_path))
            if candidate == careers_url.rstrip("/"):
                continue
            try:
                rendered = fetch_rendered_html(candidate, wait_ms=4000, timeout=30, force_browser=True)
                rendered_html = rendered.get("html") or ""
                if rendered_html and len(rendered_html) > 2000:
                    captured = rendered.get("captured_json") or []
                    page_jobs = extract_jobs_from_html(
                        candidate, rendered_html, limit=300, extra_json_blobs=captured,
                    )
                    if page_jobs:
                        logger.info(
                            "Sub-path %s yielded %d jobs for %s",
                            candidate, len(page_jobs), company_name,
                        )
                        return self._format_jobs(page_jobs, company_name, hq_country)
            except Exception:
                continue

        # ── Pass 3: Direct Playwright on the original URL with long wait ──
        try:
            rendered = fetch_rendered_html(careers_url, wait_ms=6000, timeout=40, force_browser=True)
            rendered_html = rendered.get("html") or ""
            if rendered_html:
                captured = rendered.get("captured_json") or []
                page_jobs = extract_jobs_from_html(
                    careers_url, rendered_html, limit=300, extra_json_blobs=captured,
                )
                if page_jobs:
                    logger.info(
                        "Pass-3 Playwright render yielded %d jobs for %s",
                        len(page_jobs), company_name,
                    )
                    return self._format_jobs(page_jobs, company_name, hq_country)
        except Exception as exc:
            logger.debug("Pass-3 Playwright render failed for %s: %s", careers_url, exc)

        logger.warning(
            "Official careers for %s returned 0 jobs from %s after all retries",
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
