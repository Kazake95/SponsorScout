from __future__ import annotations
import logging
import re
from sponsorscout.connectors.base import BaseConnector
from sponsorscout.core.http_client import http_session
from sponsorscout.core.url_normalizer import normalize_url
from sponsorscout.connectors.common import parse_links_from_html


logger = logging.getLogger(__name__)
class PersonioConnector(BaseConnector):
    ats_name = "personio"

    def fetch_jobs(self, company):
        careers_url = company.get("careers_url", "").rstrip("/")
        if not careers_url:
            return []
        # BUGFIX: use the context manager so the connection pool is
        # closed when the function returns. build_session() leaked one
        # open Session per call (dozens leaked after a full scan).
        with http_session() as session:
            # Build the correct Personio XML/JSON feed URL
            # Pattern: {slug}.jobs.personio.com/xml  or  {slug}.jobs.personio.de/xml
            slug = company.get("ats_board_token") or self._extract_slug(careers_url)
            xml_candidates = []
            if slug:
                xml_candidates = [
                    f"https://{slug}.jobs.personio.com/xml",
                    f"https://{slug}.jobs.personio.de/xml",
                    f"https://{slug}.personio.com/jobs/xml",
                ]
            # Also try appending to careers_url directly if it already looks right
            if "personio" in careers_url:
                xml_candidates.append(f"{careers_url}/xml")
                xml_candidates.append(careers_url.rstrip("/xml") + "/xml")

            for xml_url in xml_candidates:
                try:
                    r = session.get(xml_url, timeout=30)
                    if r.status_code != 200:
                        continue
                    ct = r.headers.get("content-type", "")
                    # B9 fix: previous version preferred XML even when the server
                    # returned JSON, because r.text.startswith("<") catches any
                    # leading whitespace. Now we only treat the body as XML when
                    # the server explicitly says so via Content-Type.
                    if "xml" in ct:
                        jobs = self._parse_xml(r.text, company, careers_url)
                        if jobs:
                            return jobs
                    elif "json" in ct or r.text.lstrip().startswith(("{", "[")):
                        try:
                            payload = r.json()
                            items = payload.get("data") or payload.get("jobs") or (payload if isinstance(payload, list) else [])
                            if isinstance(items, list) and items:
                                jobs = self._parse_json_items(items, company, careers_url)
                                if jobs:
                                    return jobs
                        except Exception as exc:
                            logger.debug("Connector %s API error (expected for wrong slug/token): %s", self.ats_name, locals().get("exc", ""))
                            # Fall through: scanner._scan_company turns the empty return
                            # into an ats_health record_failure() call.
                    else:
                        # Unknown content-type: try JSON first, then XML.
                        try:
                            payload = r.json()
                            items = payload.get("data") or payload.get("jobs") or (payload if isinstance(payload, list) else [])
                            if isinstance(items, list) and items:
                                jobs = self._parse_json_items(items, company, careers_url)
                                if jobs:
                                    return jobs
                        except Exception as exc:
                            logger.debug("Connector %s API error (expected for wrong slug/token): %s", self.ats_name, locals().get("exc", ""))
                            jobs = self._parse_xml(r.text, company, careers_url)
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
        m = re.search(r"([a-zA-Z0-9_-]+)\.(?:jobs\.)?personio\.(?:com|de)", url)
        return m.group(1) if m else ""

    def _parse_xml(self, xml_text: str, company: dict, base_url: str) -> list:
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_text)
            jobs = []
            for pos in root.findall(".//position"):
                title = (pos.findtext("name") or "").strip()
                if not title:
                    continue
                url = normalize_url(pos.findtext("applyUrl") or pos.findtext("url") or base_url)
                office = (pos.findtext("office") or "").strip()
                desc = (pos.findtext(".//jobDescription/value") or
                        pos.findtext("jobDescriptions/jobDescription/value") or "").strip()
                jobs.append({
                    "external_id": pos.findtext("id") or "",
                    "title": title,
                    "company": company["name"],
                    "country": company.get("country", ""),
                    "location": office,
                    "url": url,
                    "description": desc,
                    "ats_source": "personio",
                })
            return jobs
        except Exception as exc:
            logger.debug("Connector %s API error (expected for wrong slug/token): %s", self.ats_name, locals().get("exc", ""))
            return []

    def _parse_json_items(self, items: list, company: dict, base_url: str) -> list:
        jobs = []
        for job in items:
            attrs = job.get("attributes", job)
            office = attrs.get("office", {})
            location = office.get("attributes", {}).get("name", "") if isinstance(office, dict) else str(office)
            url = normalize_url(attrs.get("url") or job.get("url") or base_url)
            jobs.append({
                "external_id": str(job.get("id", "")),
                "title": attrs.get("name", "") or attrs.get("title", ""),
                "company": company["name"],
                "country": company.get("country", ""),
                "location": location,
                "url": url,
                "description": attrs.get("description", "") or "",
                "ats_source": "personio",
            })
        return jobs
