from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html


logger = logging.getLogger(__name__)
class LeverConnector(BaseConnector):
    ats_name = "lever"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            # Extract company slug for the real Lever API
            slug = company.get("ats_board_token") or self._extract_slug(careers_url)

            if slug:
                # Official Lever public postings API
                api_candidates = [
                    f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=500",
                    f"https://jobs.lever.co/{slug}/postings?mode=json",
                ]
                for api in api_candidates:
                    try:
                        r = session.get(api, timeout=30)
                        r.raise_for_status()
                        payload = r.json()
                        jobs = []
                        items = payload if isinstance(payload, list) else payload.get("postings", [])
                        if isinstance(items, list) and items:
                            for job in items:
                                # B5 fix: previous version crashed with
                                # AttributeError when Lever returned `categories`
                                # as a string instead of a dict, which silently
                                # dropped every job for that board.
                                cats = job.get("categories")
                                if not isinstance(cats, dict):
                                    location = ""
                                else:
                                    all_locs = cats.get("allLocations")
                                    if isinstance(all_locs, list) and all_locs:
                                        location = all_locs[0] or ""
                                    else:
                                        location = ""
                                    location = location or cats.get("location", "") or ""
                                url = normalize_url(job.get("hostedUrl") or job.get("applyUrl") or careers_url)
                                jobs.append({
                                    "external_id": str(job.get("id", "")),
                                    "title": job.get("text", "") or job.get("title", ""),
                                    "company": company["name"],
                                    "country": company.get("country", ""),
                                    "location": location,
                                    "url": url,
                                    "description": job.get("descriptionPlain", "") or job.get("description", "") or "",
                                    "ats_source": "lever",
                                })
                            if jobs:
                                return jobs
                    except Exception as exc:
                        logger.exception("Connector %s error", self.ats_name)
                        pass

            # Fallback: HTML scrape
            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.exception("Connector %s error", self.ats_name)
                return []

    def _extract_slug(self, url: str) -> str:
        """Extract slug from:
        - jobs.lever.co/{slug}
        - careers.lever.co/{slug}
        """
        m = re.search(r"(?:jobs|careers)\.lever\.co/([^/?#]+)", url)
        return m.group(1) if m else ""
