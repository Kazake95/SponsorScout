from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html


logger = logging.getLogger(__name__)
class WorkdayConnector(BaseConnector):
    ats_name = "workday"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []

        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session: 
            
            tenant, site = self._extract_workday_params(careers_url)
            if tenant and site:
                # Workday uses .wd1, .wd3, .wd5 etc — try all common variants
                for subdomain in [f"{tenant}.wd1", f"{tenant}.wd3", f"{tenant}.wd5", tenant]:
                    endpoint = f"https://{subdomain}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
                    try:
                        r = session.post(
                            endpoint,
                            json={"limit": 100, "offset": 0, "searchText": "", "appliedFacets": {}},
                            timeout=30,
                            headers={"Content-Type": "application/json", "Accept": "application/json"},
                        )
                        if r.status_code != 200:
                            continue
                        payload = r.json()
                        postings = payload.get("jobPostings") or []
                        if isinstance(postings, list) and postings:
                            jobs = []
                            base_url = f"https://{subdomain}.myworkdayjobs.com"
                            for job in postings:
                                path = job.get("externalPath", "")
                                url = normalize_url(base_url + path if path else careers_url)
                                jobs.append({
                                    "external_id": path.split("/")[-1] if path else str(job.get("title", "")),
                                    "title": job.get("title", ""),
                                    "company": company["name"],
                                    "country": company.get("country", ""),
                                    "location": job.get("locationsText", "") or "",
                                    "url": url,
                                    "description": "",
                                    "ats_source": "workday",
                                })
                            if jobs:
                                return jobs
                    except Exception as exc:
                        logger.exception("Connector %s error", self.ats_name)
                        continue
            else:
                # B16 fix: previous version silently fell through to HTML scraping
                # when no tenant could be extracted, which fails for almost all
                # Workday boards (they render via JS). Now we at least try a
                # reasonable subdomain guess and report the failure through the
                # logging system if we still can't extract tenant/site.
                import logging
                logging.getLogger(__name__).debug(
                    "Workday: couldn't extract tenant/site from %r; "
                    "HTML scrape fallback will likely yield 0 jobs.", careers_url
                )

            try:
                r = session.get(careers_url, timeout=30)
                r.raise_for_status()
                return parse_links_from_html(r.text, careers_url, company["name"])
            except Exception as exc:
                logger.exception("Connector %s error", self.ats_name)
                return []

    def _extract_workday_params(self, url: str):
        """Extract (tenant, site) from Workday URL patterns:
        - https://company.wd1.myworkdayjobs.com/en-US/SiteName
        - https://company.wd3.myworkdayjobs.com/SiteName
        - https://company.myworkdayjobs.com/SiteName
        """
        # Pattern: {tenant}.wd{n}.myworkdayjobs.com/[locale/]{site}
        m = re.match(
            r"https?://([a-zA-Z0-9_-]+?)(?:\.wd\d+)?\.myworkdayjobs\.com"
            r"(?:/[a-z]{2}-[A-Z]{2})?/([^/?#]+)",
            url
        )
        if m:
            return m.group(1), m.group(2)
        return "", ""
