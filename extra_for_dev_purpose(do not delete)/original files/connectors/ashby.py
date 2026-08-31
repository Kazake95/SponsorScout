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

        slug = self._extract_slug(careers_url)
        if not slug:
            return self._fallback_html(careers_url, company)

        # Public Ashby job board JSON — no auth required
        api = f"https://jobs.ashbyhq.com/{slug}/jobs.json"
        try:
            with http_session() as session:
                r = session.get(api, timeout=30)
                r.raise_for_status()
                payload = r.json()
        except Exception as exc:
            logger.debug("Ashby public JSON failed for %s: %s", slug, exc)
            return self._fallback_html(careers_url, company)

        postings = payload.get("jobs") or []
        if not postings:
            return self._fallback_html(careers_url, company)

        jobs = []
        for job in postings:
            loc = job.get("location", "")
            if isinstance(loc, dict):
                location = ", ".join(filter(None, [
                    loc.get("city", ""),
                    loc.get("countryCode", ""),
                ]))
            else:
                location = str(loc)

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
                "url": normalize_url(job.get("url") or careers_url),
                "description": strip_html(raw_desc),
                "ats_source": "ashby",
            })

        return jobs

    def _fallback_html(self, careers_url, company):
        """Fallback HTML scrape when the JSON endpoint fails."""
        try:
            with http_session() as session:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
        except Exception as exc:
            logger.debug("Ashby HTML fallback failed for %s: %s", company.get("name"), exc)
            return []

    def _extract_slug(self, url: str) -> str:
        # https://jobs.ashbyhq.com/CompanySlug
        m = re.search(r"ashbyhq\.com/([^/?#]+)", url)
        return m.group(1) if m else ""
