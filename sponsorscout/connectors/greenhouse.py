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
                        # Handle rate limiting with retry
                        if r.status_code == 429:
                            import time
                            retry_after = int(r.headers.get("Retry-After", 5))
                            logger.info(
                                "Greenhouse rate-limited on %s, waiting %ds",
                                api, retry_after,
                            )
                            time.sleep(retry_after)
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
                                desc = job.get("content", "") or ""
                                # Strip HTML from description
                                if desc and "<" in desc:
                                    from sponsorscout.connectors.common import strip_html
                                    desc = strip_html(desc)
                                jobs.append({
                                    "external_id": str(job.get("id", "")),
                                    "title": job.get("title", ""),
                                    "company": company["name"],
                                    "country": company.get("country", ""),
                                    "location": location,
                                    "url": url,
                                    "description": desc,
                                    "ats_source": "greenhouse",
                                })
                            if jobs:
                                logger.info(
                                    "Greenhouse: fetched %d jobs for %s via %s",
                                    len(jobs), company.get("name"), token,
                                )
                                return jobs
                    except Exception as exc:
                        logger.debug(
                            "Greenhouse API %s failed for %s: %s",
                            api, company.get("name"), exc,
                        )
                        # Continue to next API endpoint
                        continue

                # If all API endpoints failed, try the board page directly
                try:
                    board_url = f"https://boards.greenhouse.io/{token}"
                    r = session.get(board_url, timeout=30)
                    if r.status_code == 200:
                        jobs = parse_links_from_html(r.text, board_url, company["name"])
                        if jobs:
                            logger.info(
                                "Greenhouse: scraped %d jobs from board page for %s",
                                len(jobs), company.get("name"),
                            )
                            return jobs
                except Exception as exc:
                    logger.debug("Greenhouse board page scrape failed for %s: %s", company.get("name"), exc)

            # Final fallback: scrape the careers page HTML
            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.debug("Greenhouse HTML fallback failed for %s: %s", company.get("name"), exc)
                return []

    def _extract_token(self, url: str) -> str:
        """Extract Greenhouse board token from URL patterns:
        - boards.greenhouse.io/{token}
        - job-boards.greenhouse.io/{token}
        - {company}.greenhouse.io  (sometimes)
        - www.hubspot.com/careers/jobs/all?page=1 → try hubspot as token
        """
        # Direct board URL: boards.greenhouse.io/stripe
        m = re.search(r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)", url)
        if m:
            return m.group(1)

        # Custom domain: try to extract company name from hostname
        # e.g., careers.hubspot.com → hubspot
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            # Remove common prefixes
            company_name = hostname.replace("careers.", "").replace("jobs.", "").replace("www.", "")
            # Remove TLD
            company_name = company_name.split(".")[0] if "." in company_name else company_name
            if company_name and len(company_name) >= 2:
                return company_name
        except Exception:
            pass

        return ""
