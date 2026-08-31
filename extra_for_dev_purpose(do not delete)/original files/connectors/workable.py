from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html


logger = logging.getLogger(__name__)
class WorkableConnector(BaseConnector):
    ats_name = "workable"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []

        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            slug = company.get("ats_board_token") or self._extract_slug(careers_url)

            if slug:
                # Official Workable public Jobs API v3
                api_candidates = [
                    f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
                    f"https://apply.workable.com/{slug}/api/v3/jobs",
                ]
                for api in api_candidates:
                    try:
                        r = session.get(api, timeout=30,
                                        headers={"Accept": "application/json"})
                        r.raise_for_status()
                        payload = r.json()
                        items = payload.get("results") or payload.get("jobs") or (payload if isinstance(payload, list) else [])
                        if isinstance(items, list) and items:
                            jobs = []
                            for job in items:
                                loc = job.get("location") or {}
                                location = ", ".join(filter(None, [
                                    loc.get("city", ""),
                                    loc.get("country", ""),
                                ])) if isinstance(loc, dict) else str(loc)
                                url = normalize_url(job.get("url") or job.get("shortlink") or f"https://apply.workable.com/{slug}/j/{job.get('shortcode','')}")
                                jobs.append({
                                    "external_id": str(job.get("id", "") or job.get("shortcode", "")),
                                    "title": job.get("title", ""),
                                    "company": company["name"],
                                    "country": company.get("country", ""),
                                    "location": location,
                                    "url": url,
                                    "description": job.get("description", "") or "",
                                    "ats_source": "workable",
                                })
                            if jobs:
                                return jobs
                    except Exception as exc:
                        logger.debug("Connector %s API error (expected for wrong slug/token): %s", self.ats_name, locals().get("exc", ""))
                        # Fall through: scanner._scan_company turns the empty return
                        # into an ats_health record_failure() call.

            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.debug("Connector %s API error (expected for wrong slug/token): %s", self.ats_name, locals().get("exc", ""))
                return []

    def _extract_slug(self, url: str) -> str:
        # Standard apply.workable.com/{slug}
        m = re.search(r"apply\.workable\.com/([^/?#]+)", url)
        if m:
            return m.group(1)
        # Known Workable custom domains — return their hardcoded slugs
        _CUSTOM_DOMAIN_SLUGS = {
            "wise.jobs": "wise",
            "jobs.babbel.com": "babbel",
        }
        from urllib.parse import urlparse
        try:
            host = urlparse(url).netloc.lower().lstrip("www.")
            if host in _CUSTOM_DOMAIN_SLUGS:
                return _CUSTOM_DOMAIN_SLUGS[host]
        except Exception:
            pass
        return ""
