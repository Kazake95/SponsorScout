# ─────────────────────────────────────────────────────────────────────────────
# ATS Career Portal Scanner v5
#
# Scans public ATS job boards (Ashby, Greenhouse, Lever, SmartRecruiters,
# Personio, Recruitee, Workable, Workday) via their official APIs, with a
# browser fallback for anything else. This is the ATS counterpart of the
# career-page scanner (career_portal_scanner_v7.py) and shares its output
# schema, scan-log format, and policies:
#
#   • Fresh output by default (never silently appends); --resume is explicit.
#   • Recruiters written to a separate <output>_recruiter.csv.
#   • Quarantined rows written to <output>_quarantine.csv (never silently dropped).
#   • Per-run scan log <output>_scan_log.csv that matches the jobs output.
#   • Visa sponsorship / relocation / EU Blue Card classified ONLY from explicit
#     evidence in the job description; otherwise "Unknown" (no fabricated "N").
#   • Job Type / Location default to "Unknown" when no evidence (no fabricated
#     "Full-time / On-site" or "Not Specified").
#   • Canonical requisition IDs dedupe mirror URLs (apply vs job URLs).
#   • Network retry + backoff and a pre-flight connectivity gate.
#   • Self-healing seed upgrade (fixes wrong/legacy URLs, EU Lever, recruiter tags).
# ─────────────────────────────────────────────────────────────────────────────
import csv
import json
import logging
import os
import re
import socket
import time
import unicodedata
from collections import Counter
from html import unescape
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, urljoin
from urllib.request import Request, urlopen

try:
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:
    sync_playwright = None

# Real-time logging. When a progress callback is installed (desktop app) all
# output lines are routed to it; otherwise they print to stdout as before.
# The original script's module-level logging.basicConfig() side effect is removed.
import builtins as _builtins

progress_cb = None


def _notify(msg):
    if progress_cb:
        progress_cb(msg)
    else:
        _builtins.print(msg, flush=True)


def print(*args, **kwargs):
    _notify(" ".join(str(a) for a in args))

# ───────────────────────── CONFIG ─────────────────────────────────────────────
from sponsorscout.scanning.common import OUTPUT_FIELDS, LOG_FIELDS

BAD_HOSTS = {
    "bcorporation.net", "glassdoor.com", "indeed.com", "linkedin.com",
    "youtube.com", "google.com", "cookie-script.com", "onetrust.com",
    "sharepoint.com", "my.greenhouse.io",
}

BAD_TITLES = {
    "create alert", "skip to main content", "open positions", "working at",
    "here", "report", "b corporation",
}

# Network resilience (v5)
PREFLIGHT_PROBE_HOSTS = (
    "www.google.com", "boards-api.greenhouse.io", "api.ashbyhq.com",
    "api.lever.co", "api.smartrecruiters.com",
)
PREFLIGHT_PORT = 443
PREFLIGHT_TIMEOUT_SEC = 5
PREFLIGHT_MAX_FAILURES = 2
HTTP_RETRIES = 3
HTTP_BACKOFF_BASE_SEC = 1.5
HTTP_TIMEOUT_SEC = 35


# ─────────────────────────────────────────────────────────────────────────────
# SEED UPGRADE TABLE — fixes for the v4 seed. Keyed by company `name`.
# Applied in-memory when reading a v6-format seed (name, ats_type, careers_url,
# industry, ...). Corrections:
#   • innogames  → EU Lever API (the US api.lever.co 404s)
#   • avomind    → recruiter + Workable public API
#   • ecosia     → flag: Ashby board currently returns 0 jobs
#   • dbtlabsinc → flag: Greenhouse board taken private (404)
#   • crealytics / moss → flag: Personio board currently empty
# ─────────────────────────────────────────────────────────────────────────────
SEED_UPGRADE = {
    "InnoGames": {"lever_region": "eu"},
    "Avomind": {"source_type": "recruiter"},
}

# ATS types whose public list API is known to currently return 0/404 — surfaced
# in the scan log diagnostics rather than silently reported as healthy.
KNOWN_BOARD_ISSUES = {
    "Ecosia": "Ashby board 'ecosia.org' currently returns 0 jobs (board may have moved)",
    "Dbt Labs": "Greenhouse board 'dbtlabsinc' returns 404 (board taken private)",
    "Crealytics": "Personio board currently returns 0 positions",
    "Moss": "Personio board currently returns 0 positions",
}

# ───────────────────────── SHARED HELPERS ────────────────────────────────────
from sponsorscout.scanning.common import clean, host_of
from sponsorscout.scanning.jd_support import (
    JDSupportDetector,
    VERDICT_YES,
    VERDICT_NO,
    VERDICT_UNKNOWN,
)


class ATSScanner:
    def __init__(self, seed_file="company_ATS_seed.csv",
                 output_file="scraped_ats_jobs_v5.csv",
                 skip_preflight=False, resume=False, cancel_event=None,
                 only_companies=None):
        self.seed_file = seed_file
        self.output_file = output_file
        self.skip_preflight = skip_preflight
        self.resume = resume
        # Cooperative cancellation for the desktop UI Stop button: checked
        # between targets in run(); never interrupts an in-flight request.
        self.cancel_event = cancel_event
        # Optional whitelist of company names (CLI --company): when set, only
        # these targets are scanned.
        self.only_companies = only_companies
        self.run_id = time.strftime("%Y%m%dT%H%M%S")
        self.detector = JDSupportDetector()

    # ── HTTP helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _is_network_error(exc):
        msg = str(exc).lower()
        markers = (
            "net::err_", "err_name_not_resolved", "err_connection_",
            "err_timed_out", "err_ssl_", "err_http_", "dns", "socket",
            "connection reset", "timed out", "timeout", "temporary failure",
            "getaddrinfo", "connectionrefused",
        )
        return any(m in msg for m in markers)

    def _preflight_connectivity(self):
        if self.skip_preflight:
            return
        failures = []
        for host in PREFLIGHT_PROBE_HOSTS:
            try:
                socket.setdefaulttimeout(PREFLIGHT_TIMEOUT_SEC)
                infos = socket.getaddrinfo(host, PREFLIGHT_PORT, socket.AF_INET)
                if not infos:
                    raise socket.gaierror("no address")
                ip = infos[0][4][0]
                with socket.create_connection((ip, PREFLIGHT_PORT),
                                              timeout=PREFLIGHT_TIMEOUT_SEC):
                    pass
                print(f"[preflight] OK   {host}")
            except Exception as exc:
                failures.append(f"{host}: {type(exc).__name__}: {exc}")
                print(f"[preflight] FAIL {host}: {type(exc).__name__}: {exc}")
        if len(failures) >= PREFLIGHT_MAX_FAILURES:
            raise RuntimeError(
                "Connectivity pre-flight FAILED: "
                f"{len(failures)}/{len(PREFLIGHT_PROBE_HOSTS)} probes unreachable. "
                "Aborting before crawling. Check DNS/VPN/proxy, then re-run. "
                "(Use --skip-preflight to bypass.)\n  " + "\n  ".join(failures))

    def _fetch(self, url, method="GET", body=None, timeout=None):
        """Fetch a URL with transient-error retry + exponential backoff.
        Returns decoded text. Raises on definitive 404/410 (no retry)."""
        timeout = timeout or HTTP_TIMEOUT_SEC
        last_exc = None
        for attempt in range(1, HTTP_RETRIES + 1):
            try:
                data = json.dumps(body).encode() if body is not None else None
                req = Request(url, data=data, method=method, headers={
                    "User-Agent": "Mozilla/5.0 ATS Scanner",
                    "Accept": "application/json,text/xml,*/*",
                    "Content-Type": "application/json",
                })
                with urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode("utf-8-sig", errors="replace")
            except Exception as exc:
                import urllib.error
                if isinstance(exc, urllib.error.HTTPError):
                    # 404/410 are definitive; 429/5xx are transient — retry them.
                    if exc.code in (404, 410):
                        raise
                    if exc.code != 429 and exc.code < 500:
                        raise
                    last_exc = exc
                elif not self._is_network_error(exc):
                    raise
                else:
                    last_exc = exc
            if attempt < HTTP_RETRIES:
                time.sleep(HTTP_BACKOFF_BASE_SEC * (2 ** (attempt - 1)))
        raise last_exc

    def _get_json(self, url):
        return json.loads(self._fetch(url))

    def _post_json(self, url, body):
        return json.loads(self._fetch(url, method="POST", body=body))

    # ── Seed ─────────────────────────────────────────────────────────────────
    def read_seed_file(self):
        if not os.path.exists(self.seed_file):
            raise FileNotFoundError(
                f"Seed file '{self.seed_file}' not found. "
                f"Put 'company_ATS_seed.csv' in the working directory or pass --input."
            )
        records = []
        errors = []
        seen_keys = set()
        with open(self.seed_file, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [clean(x) for x in (reader.fieldnames or [])]
            for line_no, row in enumerate(reader, 2):
                name = clean(row.get("name"))
                ats_type = clean(row.get("ats_type")).lower()
                industry = clean(row.get("industry") or "Tech")
                url = clean(row.get("careers_url"))
                if not name or not ats_type or not url:
                    errors.append(f"line {line_no}: missing name/ats_type/careers_url")
                    continue
                if not url.startswith(("http://", "https://")):
                    errors.append(f"line {line_no} {name}: invalid URL {url!r}")
                    continue
                # v6 → v5 upgrade
                upg = SEED_UPGRADE.get(name)
                if upg:
                    changed = []
                    for k in ("source_type", "lever_region"):
                        if upg.get(k):
                            changed.append(f"{k} -> {upg[k]}")
                    if changed:
                        print(f"   [upgrade] {name}: " + "; ".join(changed))
                source_type = (upg or {}).get("source_type") or "direct_employer"
                lever_region = (upg or {}).get("lever_region") or ""
                key = (name.casefold(), ats_type, url.casefold())
                if key in seen_keys:
                    print(f"   -> Seed deduped (duplicate): {name} line {line_no}")
                    continue
                seen_keys.add(key)
                scores = {}
                for col in ("sponsorship_history", "english_friendly", "remote_score"):
                    raw = clean(row.get(col))
                    try:
                        scores[col] = int(raw) if raw else None
                    except ValueError:
                        scores[col] = None
                records.append({
                    "name": name, "ats_type": ats_type, "url": url,
                    "industry": industry, "source_type": source_type,
                    "lever_region": lever_region, **scores,
                })
        if errors:
            raise ValueError("Seed validation failed:\n - " + "\n - ".join(errors))
        return records

    # ── Normalization ────────────────────────────────────────────────────────
    @staticmethod
    def _strip_html(text):
        text = re.sub(r"<[^>]+>", " ", text or "")
        return clean(text)

    def _norm(self, s):
        try:
            s = s.translate(str.maketrans({
                "\u0142": "l", "\u0141": "L", "\u0105": "a", "\u0104": "A",
                "\u0119": "e", "\u0118": "E", "\u0144": "n", "\u0143": "N",
                "\u015b": "s", "\u015a": "S", "\u017a": "z", "\u0179": "Z",
                "\u017c": "z", "\u017b": "Z", "\u0107": "c", "\u0106": "C",
                "\u00f8": "o", "\u00d8": "O", "\u00e5": "a", "\u00c5": "A",
                "\u00e6": "ae", "\u00c6": "AE", "\u0153": "oe", "\u0152": "OE",
                "\u00df": "ss",
            }))
            s = unicodedata.normalize("NFKD", s)
            s = s.encode("ascii", "ignore").decode()
        except Exception:
            pass
        return re.sub(r"\s+", " ", s).strip().lower()

    # Acronyms / country codes that must never be title-cased ("UK" → "Uk").
    _ACRONYMS = {"uk", "us", "usa", "uae", "eu", "emea", "apac", "latam",
                 "mena", "dach", "dnu", "hq"}

    # Source-data typos seen in ATS location strings.
    _TYPO_MAP = {"dehli": "Delhi"}

    @staticmethod
    def _fmt_token(tok):
        """Normalize one location token: strip Workday '(DNU)' / '(Remote)'
        artifacts and stray parentheses, fix known source typos, preserve
        acronym casing, otherwise keep the source casing (ATS strings are
        already title-cased)."""
        tok = re.sub(r"\s*\(?\s*dnu\s*\)?\s*$", "", tok, flags=re.I)
        tok = tok.strip(" )([")
        if not tok:
            return ""
        # fix source-data typos word-by-word
        for bad, good in ATSScanner._TYPO_MAP.items():
            tok = re.sub(r"\b" + re.escape(bad) + r"\b", good, tok, flags=re.I)
        # normalize acronyms inside a possibly comma-separated region string
        parts = [p.strip() for p in tok.split(",")]
        parts = [
            (p.upper() if p.lower() in ATSScanner._ACRONYMS else p)
            for p in parts if p
        ]
        return ", ".join(parts) if parts else tok

    def format_location(self, location, remote_hint=""):
        """Normalize a structured ATS location string to 'City, Country' or
        'Remote - X'. Returns 'Remote' when the posting is remote with no
        physical place, otherwise 'Unknown' when nothing usable remains."""
        location = clean(location or "")
        remote_hint = clean(remote_hint or "").lower()
        if not location:
            return ("Remote" if "remote" in remote_hint else "Unknown")
        # Collapse multi-line / pipe-separated location lists to the first value
        parts = [clean(p) for p in re.split(r"[;\n|]+", location) if clean(p)]
        location = parts[0] if parts else ""
        if not location:
            return ("Remote" if "remote" in remote_hint else "Unknown")
        low = location.lower()
        if low in ("global", "worldwide", "united", "anywhere", "multiple locations"):
            return ("Remote" if "remote" in remote_hint else "Unknown")
        # "2 Locations" style Workday placeholder (actual sites not in list API)
        if re.fullmatch(r"\d+\s+locations?", low):
            return "Unknown"

        # ── Remote-first forms: "Remote", "Remote - X", "Remote, X", "Remote (X)" ──
        if re.match(r"^remote\b", low):
            m = re.search(r"^remote[\s:.,()-]+(.+)$", location, re.I)
            if m:
                # strip trailing "(Remote)" / "(DNU)" qualifiers, keep the region
                region = re.sub(r"\s*\(\s*remote\s*\)\s*$", "", m.group(1), flags=re.I)
                region = self._fmt_token(region)
                return f"Remote - {region}" if region else "Remote"
            return "Remote"

        # ── "City1, City2 or Remote (Country)" → "City1, Country" ──────────────
        if re.search(r"\bor\b.{0,24}\bremote\b", low):
            cm = re.search(r"\(([^)]+)\)", location)
            country = self._fmt_token(cm.group(1)) if cm else ""
            first_city = self._fmt_token(location.split(",")[0])
            return f"{first_city}, {country}" if country else first_city

        # ── "Place - Remote Based" → keep the leading place ───────────────────
        if re.search(r"-\s*remote\b", low) or re.search(r"\bremote\s+based\b", low):
            leading = re.split(r"-\s*remote\b|\bremote\s+based\b", location, 1, re.I)[0]
            leading = self._fmt_token(leading)
            if leading:
                return leading

        # ── "City, Region, Country" (or bare city) ────────────────────────────
        segs = [s.strip() for s in location.split(",") if s.strip()]
        if segs:
            out = [self._fmt_token(s) for s in segs]
            out = [s for s in out if s]
            if out:
                return ", ".join(out)

        out = self._fmt_token(location)
        return out or ("Remote" if "remote" in remote_hint else "Unknown")

    # ── Classification (honest — no fabrication) ─────────────────────────────
    def classify_job_type(self, raw="", workplace="", description=""):
        text = clean(f"{raw} {workplace} {description}").lower()
        job_kind = "Unknown"
        if re.search(r"\bintern(ship)?\b|praktikum|tirocinio|trainee|apprentic|stage\b", text):
            job_kind = "Internship"
        elif re.search(r"part[ -]?time|teilzeit|deeltijd", text):
            job_kind = "Part-time"
        elif re.search(r"\bfull[ -]?time|fulltime|vollzeit|voltijd|permanent|contract|fixed[ -]?term|temporary", text):
            job_kind = "Full-time"
        mode = "Unknown"
        if re.search(r"\bremote\b|work from home|home office|100% remote|fully remote", text):
            mode = "Remote"
        elif re.search(r"\bhybrid\b|smart working|smartworking", text):
            mode = "Hybrid"
        elif re.search(r"\bon[- ]?site|onsite|in[- ]?office|in office", text):
            mode = "On-site"
        return f"{job_kind} / {mode}"

    def classify_support(self, description, title=""):
        """Run the explicit-evidence support detector over the JD text.
        Returns (eu_blue_card, visa, relocation, relocation_required,
                 confidence, evidence, support_flag)."""
        if not description:
            return ("Unknown", "Unknown", "Unknown", "Unknown", 0.0, "", "Unknown")
        text = self._strip_html(description)
        if not text:
            return ("Unknown", "Unknown", "Unknown", "Unknown", 0.0, "", "Unknown")
        sup = self.detector.detect(text)
        visa = sup["visa"]["verdict"]
        reloc = sup["relocation"]["verdict"]
        # ── False-positive guards (a mention is only "support offered to YOU" if
        # it isn't the job FUNCTION, an event/travel arrangement, or brand
        # sponsorship) ─────────────────────────────────────────────────────────
        # (1) "sponsorship" alone is ambiguous (event/brand/partnership).
        #     A visa "Yes" needs an actual visa/immigration/work-authorization
        #     keyword present, not merely "sponsor a session / trade show".
        if visa == VERDICT_YES:
            if not re.search(
                r"visa|work permit|work authori[sz]ation|immigration|h-?1b|"
                r"blue card|carta blu|blaue karte|blauwe kaart|carte bleue|"
                r"tarjeta azul|skilled (migrant|worker)|aufenthaltstitel|"
                r"arbeitserlaubnis|permesso di soggiorno|permis de travail|"
                r"werkvergunning|arbeidsvergunning|permiso de trabajo",
                text, re.I,
            ):
                visa = VERDICT_UNKNOWN
        # (2) event/trade-show/partner sponsorship is not visa sponsorship.
        if re.search(
            r"sponsor\w*.{0,50}\b(event|conference|trade[- ]show|booth|"
            r"session|co[- ]market|partner|speaker)\b",
            text, re.I,
        ) or re.search(
            r"\b(event|conference|trade[- ]show|booth|session|co[- ]market|"
            r"partner)\w*.{0,50}sponsor\w*",
            text, re.I,
        ):
            visa = VERDICT_UNKNOWN if visa == VERDICT_YES else visa
        # (3) "visas for international events / speakers / travel" = arranging
        #     travel documents, not sponsoring the candidate.
        if re.search(
            r"\b(visas?|work permits?)\s+for\s+(international\s+events?|"
            r"speakers?|travel|attendees?)",
            text, re.I,
        ):
            visa = VERDICT_UNKNOWN if visa == VERDICT_YES else visa
        # (4) job FUNCTION: the role administers mobility/immigration/relocation
        #     for OTHERS (its title says so). These are not candidate benefits.
        t = clean(title or "").lower()
        if re.search(
            r"\b(?:global|international)\s+mobility\b|\bimmigration\b|\brelocation\b",
            t,
        ) and re.search(
            r"\b(manager|specialist|coordinator|officer|lead|director|program|"
            r"administrator|consultant|partner|hr)\b",
            t,
        ):
            visa = VERDICT_UNKNOWN if visa == VERDICT_YES else visa
            reloc = VERDICT_UNKNOWN if reloc == VERDICT_YES else reloc
        # (5) duty-frame: "tracking of work permits" / "manage visa applications"
        #     describes work the HIRE performs for others, not a benefit. Downgrade
        #     unless the JD ALSO makes a candidate-facing offer ("sponsor your
        #     visa" / "we will sponsor your visa"). A bare "we offer" or
        #     "benefits include" elsewhere in the JD is NOT enough.
        if visa == VERDICT_YES and re.search(
            r"\b(track(?:ing)?|manag(?:e|ing)|oversee(?:ing)?|administer(?:ing)?|"
            r"process(?:ing)?|handle(?:ing)?|coordinat(?:e|ing))\s+(?:of\s+)?"
            r"(work\s+permits?|visas?|immigration\s+cases?)\b",
            text, re.I,
        ):
            candidate_offer = re.search(
                r"\b(your|you)\b.{0,25}\b(visa|work\s+permit)\b"
                r"|\b(sponsor\w*|cover\w*|pay\s+for)\s+(your|the)\s+(visa|work\s+permit)"
                r"|\bwe\b.{0,30}\b(sponsor\w*)\b.{0,30}\b(visa|work\s+permit)\b",
                text, re.I,
            )
            if not candidate_offer:
                visa = VERDICT_UNKNOWN
        reloc_req = ("Yes" if sup["relocation"]["required"] else "Unknown")
        conf = round(max(sup["visa"]["confidence"], sup["relocation"]["confidence"]), 2)
        evidence = "; ".join(filter(None, [
            self.detector.best_evidence(sup["visa"]),
            self.detector.best_evidence(sup["relocation"]),
        ]))
        # Blue card is independent of general visa sponsorship.
        blue = "Unknown"
        for sent in self.detector.split_sentences(text):
            if re.search(
                r"\b(?:eu\s+)?blue[- ]?card|blaue karte|carta blu|blauwe kaart|carte bleue|tarjeta azul\b",
                sent, re.I,
            ):
                if self.detector.NEGATION.search(sent):
                    blue = "N"
                elif self.detector.POSITIVE_VERBS.search(sent):
                    blue = "Y"
                break
        flag = "Unknown"
        if visa == VERDICT_YES or reloc == VERDICT_YES:
            flag = "Y"
        elif visa == VERDICT_NO and reloc == VERDICT_NO:
            flag = "N"
        return (blue, visa, reloc, reloc_req, conf, evidence, flag)

    # ── Identity / validation ────────────────────────────────────────────────
    def canonical_job_id(self, company, url, provider, title="", location=""):
        u = unescape(url or "")
        candidates = []
        for pattern in (
            r"(?i)(?:jobid|job_id|gh_jid|reqid|requisitionid|career_job_req_id|postingid|r)=([A-Za-z]*\d{4,})",
            r"(?i)(?:^|[/_-])(R\d{5,})(?:[-_/?]|$)",
            r"(?i)/jobs?/(\d{5,})(?:/|$)",
            r"(?i)/([0-9a-f]{8}-[0-9a-f-]{27,})(?:/|$)",
            r"(?i)/(\d{5,})(?:/?(?:[?#]|$))",
        ):
            candidates.extend(re.findall(pattern, u))
        identity = candidates[0].casefold() if candidates else ""
        if not identity:
            p = urlparse(u)
            identity = p.netloc.casefold().removeprefix("www.") + p.path.rstrip("/").casefold()
        if not identity and title:
            identity = f"title:{self._norm(title)}|loc:{self._norm(location)}"
        return f"{company.casefold()}|{provider.casefold()}|{identity}"

    def valid_job_url(self, url):
        if not url or not url.startswith(("http://", "https://")):
            return False
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        if host in BAD_HOSTS or any(host.endswith("." + h) for h in BAD_HOSTS):
            return False
        # Reject UI routes by PATH SEGMENT, not substring. A job slug like
        # "Application-Engineer" must NOT match "/application", nor
        # "Team-Leader" match "/team", nor "Legal-Affairs" match "/legal".
        rejected_segments = {
            "users", "sign-in", "signin", "sign_in", "create-alert",
            "create_alert", "privacy", "cookie", "terms", "legal", "blog",
            "posts", "tags", "about", "team", "culture", "form",
            "applicationmethods", "apply", "application",
        }
        segments = [s for s in path.split("/") if s]
        for seg in segments:
            if seg in rejected_segments:
                return False
        # a couple of multi-segment UI routes (exact path, not substring)
        if re.search(r"/(users/sign_in|applicationmethods)(?:/|$)", path):
            return False
        if re.search(r"/(careers?|jobs?)/?$", path):
            return False
        return True

    def valid_title(self, title):
        title = clean(title)
        low = title.lower()
        if not title or len(title) > 180:
            return False
        # allow short CJK titles (e.g. 2-char "电工" = electrician); Latin titles
        # under 3 chars ("IT", "HR", "QA") are never real job titles
        if len(title) < 3 and not re.search(
                r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", title):
            return False
        if low in BAD_TITLES:
            return False
        rejected = (
            "sorry, internet explorer", "privacy policy", "cookie policy",
            "terms of service", "skip to main", "looking for a job",
            "equal opportunity", "data protection", "talent community",
            "talent pool", "candidate database", "career day",
            "save for later", "show job", "learn more",
            "read more", "view job", "view role",
        )
        if any(x in low for x in rejected):
            return False
        # Bare generic level/function words are not real titles — EXCEPT the
        # complete entry-level titles below, which are legitimate on their own
        # ("Intern", "Apprentice", "Trainee" describe the role fully, unlike
        # a truncated "Director" or "Engineer").
        if low in {"senior", "junior", "associate", "principal", "lead",
                   "manager", "director", "expert", "owner", "officer",
                   "specialist", "analyst", "engineer",
                   "full time", "part time", "contract"}:
            return False
        return True

    # ── Row construction (full v5 schema, honest defaults) ───────────────────
    def make_row(self, target, title, url, location, raw_location, job_type,
                 description, extraction_method, location_source="api"):
        title = clean(title)
        url = clean(url)
        reason = None
        if not self.valid_job_url(url):
            reason = "invalid_or_application_only_url"
        elif not self.valid_title(title):
            reason = "invalid_generic_or_department_title"
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        rec = {
            "Company Name": target["name"],
            "Seed Name": target["name"],
            "Source Type": target["source_type"],
            "Hiring Company": (target["name"] if target["source_type"] == "direct_employer" else "Unknown"),
            "Target Country": "Global",
            "Scope Policy": "global",
            "Industry Type": target["industry"],
            "Sponsorship History Score": target.get("sponsorship_history", ""),
            "English Friendly Score": target.get("english_friendly", ""),
            "Remote Score": target.get("remote_score", ""),
            "Job Title": title,
            "Raw Job Title": title,
            "Job Location": location if location and location != "Not Specified" else "Unknown",
            "Raw Location": raw_location or "",
            "Job Type": job_type,
            "Job URL": url,
            "Canonical Job ID": self.canonical_job_id(
                target["name"], url, target["ats_type"], title, location or ""),
            "Provider": target["ats_type"],
            "Extraction Method": extraction_method,
            "EU Blue Card": "Unknown",
            "Blue Card Evidence": "",
            "Relocation/Visa Support": "Unknown",
            "Location Source": location_source if location and location not in ("Not Specified", "Unknown") else "none",
            "URL Type": "real",
            "Visa Sponsorship": "Unknown",
            "Relocation Support": "Unknown",
            "Relocation Required": "Unknown",
            "Support Confidence": 0.0,
            "Support Evidence": "",
            "Support Evidence URL": url,
            "Support Evidence Type": "none",
            "Record Status": "quarantine" if reason else "accepted",
            "Quarantine Reason": reason or "",
            "Run ID": self.run_id,
            "Scanned At": now,
        }
        # Support detection from explicit JD evidence only.
        blue, visa, reloc, reloc_req, conf, evidence, flag = self.classify_support(description, title)
        rec["EU Blue Card"] = blue
        rec["Visa Sponsorship"] = visa
        rec["Relocation Support"] = reloc
        rec["Relocation Required"] = reloc_req
        rec["Support Confidence"] = conf
        rec["Support Evidence"] = evidence
        rec["Relocation/Visa Support"] = flag
        if evidence:
            rec["Support Evidence Type"] = "explicit_jd_sentence"
        return rec

    # ── ATS adapters ─────────────────────────────────────────────────────────
    def scan_ashby(self, target):
        url = target["url"]
        parts = [p for p in urlparse(url).path.split("/") if p]
        if not parts:
            return []
        board = parts[0]
        data = self._get_json(
            f"https://api.ashbyhq.com/posting-api/job-board/{board}"
            f"?includeCompensation=false")
        rows = []
        for job in data.get("jobs", []):
            if job.get("isListed") is False:
                continue
            locs = [self.format_location(job.get("location"))]
            for sl in job.get("secondaryLocations", []):
                locs.append(self.format_location(
                    sl if isinstance(sl, str) else (sl or {}).get("location")))
            locs = [x for x in dict.fromkeys(locs) if x and x != "Unknown"]
            location = locs[0] if locs else "Unknown"
            raw_location = " | ".join(locs)
            desc = job.get("descriptionPlain") or self._strip_html(job.get("descriptionHtml") or "")
            job_type = self.classify_job_type(
                job.get("employmentType"), job.get("workplaceType"), desc)
            row = self.make_row(
                target, job.get("title"), job.get("jobUrl") or job.get("applyUrl"),
                location, raw_location, job_type, desc, "ashby_api")
            rows.append(row)
        return rows

    def scan_greenhouse(self, target):
        url = target["url"]
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        board = ""
        if "job_board=" in parsed.query:
            board = parsed.query.split("job_board=", 1)[1].split("&", 1)[0]
        elif path_parts:
            board = path_parts[-1]
        if "figma.com" in urlparse(url).netloc:
            board = "figma"
        if board.lower() in {"careers", "job-openings"} or not board:
            return []
        data = self._get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
        rows = []
        for job in data.get("jobs", []):
            loc_obj = job.get("location") or {}
            location = self.format_location(loc_obj.get("name") or "")
            desc = self._strip_html(job.get("content") or "")
            job_type = self.classify_job_type(
                "", loc_obj.get("name") or "", desc)
            row = self.make_row(
                target, job.get("title"), job.get("absolute_url"),
                location, loc_obj.get("name") or "", job_type, desc, "greenhouse_api")
            rows.append(row)
        return rows

    def scan_lever(self, target):
        url = target["url"]
        parts = [p for p in urlparse(url).path.split("/") if p]
        if not parts:
            return []
        board = parts[0]
        region = target.get("lever_region") or ""
        if not region and ".eu.lever.co" in urlparse(url).netloc:
            region = "eu"
        base = "api.eu.lever.co" if region == "eu" else "api.lever.co"
        data = self._get_json(f"https://{base}/v0/postings/{board}?mode=json")
        rows = []
        if not isinstance(data, list):
            return rows
        for job in data:
            cats = job.get("categories", {})
            loc_val = cats.get("location") or "; ".join(cats.get("allLocations", []))
            location = self.format_location(loc_val)
            desc = job.get("descriptionPlain") or ""
            job_type = self.classify_job_type(
                cats.get("commitment"), loc_val, desc)
            row = self.make_row(
                target, job.get("text"), job.get("hostedUrl"),
                location, loc_val, job_type, desc, "lever_api")
            rows.append(row)
        return rows

    def scan_smartrecruiters(self, target):
        url = target["url"]
        host = urlparse(url).netloc.lower()
        # SmartRecruiters' own careers site uses a legacy host with no board in the
        # URL; its public board slug is "SmartRecruiters".
        if "smartrecruiterscareers.com" in host:
            board = "SmartRecruiters"
        else:
            m = re.search(r"smartrecruiters\.com/(?:jobs/)?([^/?#]+)", url, re.I)
            if not m:
                return []
            board = m.group(1)
        offset = 0
        rows = []
        while True:
            data = self._get_json(
                f"https://api.smartrecruiters.com/v1/companies/{board}/postings"
                f"?limit=100&offset={offset}")
            jobs = data.get("content", [])
            for job in jobs:
                loc_obj = job.get("location", {}) or {}
                loc_parts = [x for x in [
                    loc_obj.get("city"), loc_obj.get("region"), loc_obj.get("country"),
                ] if x]
                location = ", ".join(loc_parts) if loc_parts else ""
                remote = bool(loc_obj.get("remote"))
                location = self.format_location(location, "remote" if remote else "")
                title = job.get("name", "")
                slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
                job_url = (f"https://jobs.smartrecruiters.com/{board}/"
                           f"{job.get('id')}-{slug}")
                # gather JD text from jobAd sections for support detection
                desc_parts = []
                jobad = job.get("jobAd") or {}
                for sec in (jobad.get("sections") or {}).values():
                    if isinstance(sec, dict):
                        txt = sec.get("text") or sec.get("description") or ""
                        desc_parts.append(self._strip_html(txt))
                desc = " ".join(desc_parts)
                job_type = self.classify_job_type(
                    (job.get("typeOfEmployment") or {}).get("label"),
                    location, desc)
                row = self.make_row(
                    target, title, job_url, location,
                    location, job_type, desc, "smartrecruiters_api")
                rows.append(row)
            offset += len(jobs)
            if not jobs or offset >= data.get("totalFound", 0):
                break
        return rows

    def scan_personio(self, target):
        import xml.etree.ElementTree as ET
        host = urlparse(target["url"]).netloc
        slug = host.split(".")[0] if host else ""
        if not slug:
            return []
        raw = self._fetch(f"https://{slug}.jobs.personio.de/xml?language=en")
        root = ET.fromstring(raw)
        rows = []
        for pos in root.findall(".//position"):
            pid = (pos.findtext("id") or "").strip()
            job_url = (pos.findtext("jobUrl") or "").strip()
            if not job_url and pid:
                job_url = f"https://{slug}.jobs.personio.de/job/{pid}"
            office = (pos.findtext("office") or "").strip()
            location = self.format_location(office)
            ctx = " | ".join(filter(None, [
                pos.findtext("department"), pos.findtext("employmentType"),
                pos.findtext("schedule"),
            ]))
            job_type = self.classify_job_type("", "", ctx)
            # Personio list API carries no JD text → support stays Unknown (honest)
            row = self.make_row(
                target, pos.findtext("name"), job_url, location, office,
                job_type, "", "personio_api")
            rows.append(row)
        return rows

    def scan_recruitee(self, target):
        host = urlparse(target["url"]).netloc
        slug = host.split(".")[0] if host else ""
        data = self._get_json(f"https://{slug}.recruitee.com/api/offers/")
        rows = []
        for offer in data.get("offers", []):
            location = self.format_location(
                offer.get("location") or offer.get("city") or "")
            desc = self._strip_html(offer.get("description") or "")
            job_type = self.classify_job_type(
                offer.get("employment_type_code"), "", desc)
            job_url = offer.get("careers_url") or (
                f"https://{slug}.recruitee.com/o/{offer.get('slug')}")
            row = self.make_row(
                target, offer.get("title"), job_url, location,
                offer.get("location") or "", job_type, desc, "recruitee_api")
            rows.append(row)
        return rows

    def scan_workable(self, target):
        # apply.workable.com/<slug>/  → slug is the FIRST PATH segment
        path_seg = [p for p in urlparse(target["url"]).path.split("/") if p]
        slug = path_seg[0] if path_seg else ""
        if not slug:
            return []
        data = self._get_json(f"https://www.workable.com/api/accounts/{slug}?details=true")
        rows = []
        for job in data.get("jobs", []):
            loc_parts = [x for x in [job.get("city"), job.get("country")] if x]
            location = ", ".join(loc_parts) if loc_parts else ""
            remote = job.get("worktype") == "remote" or job.get("telecommuting")
            location = self.format_location(location, "remote" if remote else "")
            desc = self._strip_html(job.get("description") or "")
            job_type = self.classify_job_type(
                job.get("employment_type"), job.get("worktype") or "", desc)
            job_url = job.get("url") or job.get("application_url") or ""
            row = self.make_row(
                target, job.get("title"), job_url, location,
                ", ".join(loc_parts), job_type, desc, "workable_api")
            rows.append(row)
        return rows

    def scan_workday(self, target):
        url = target["url"]
        parsed = urlparse(url)
        host = parsed.netloc
        # tenant.wdX.myworkdayjobs.com → tenant + wdX
        m = re.match(r"([^.]+)\.(wd\d)\.myworkdayjobs\.com", host, re.I)
        if not m:
            return []
        tenant, wd = m.group(1), m.group(2)
        site = (parsed.path.strip("/").split("/") or [""])[-1]
        if not site:
            return []
        api = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
        rows = []
        offset = 0
        limit = 20  # Workday API rejects limit > 20 (HTTP 400)
        total = None
        while True:
            data = self._post_json(api, {
                "appliedFacets": {}, "limit": limit, "offset": offset,
                "searchText": "",
            })
            # Workday only reports `total` on the FIRST page; later pages return 0.
            if total is None:
                total = data.get("total") or 0
            jobs = data.get("jobPostings", [])
            if not jobs:
                break
            for job in jobs:
                title = job.get("title", "")
                ext = job.get("externalPath", "")
                job_url = f"https://{host}{ext}" if ext else ""
                location = self.format_location(job.get("locationsText") or "")
                req = ""
                bf = job.get("bulletFields") or []
                for b in bf:
                    if re.match(r"^R\d+$", str(b)):
                        req = str(b)
                        break
                # Workday list API has no JD text → support Unknown; use remoteType
                job_type = self.classify_job_type("", job.get("remoteType") or "", "")
                row = self.make_row(
                    target, title, job_url, location,
                    job.get("locationsText") or "", job_type, "", "workday_api")
                if req:
                    row["Canonical Job ID"] = (
                        f"{target['name'].casefold()}|workday|{req.casefold()}")
                rows.append(row)
            offset += len(jobs)
            if total and offset >= total:
                break
            if len(jobs) < limit:
                break
        return rows

    def browser_fallback(self, target):
        """Last-resort DOM scrape for ATS types without a public API."""
        if sync_playwright is None:
            logging.error("Playwright required for %s", target["url"])
            return []
        rows = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(target["url"], wait_until="domcontentloaded", timeout=35000)
                page.wait_for_timeout(2500)
                jobs = page.evaluate(
                    """
                    () => {
                        const out = [];
                        for (const a of document.querySelectorAll('a[href]')) {
                            const href = a.href || '';
                            if (!href.startsWith('http')) continue;
                            const card = a.closest('li, article, tr, [class*="job" i], [class*="opening" i], [class*="position" i]') || a.parentElement;
                            const heading = card && card.querySelector('h1,h2,h3,h4,[class*="title" i]');
                            const title = (a.innerText || (heading && heading.innerText) || '').replace(/\\s+/g,' ').trim();
                            if (!title || title.length < 3 || title.length > 180) continue;
                            out.push({ title, href, text: (card && card.innerText || '').replace(/\\s+/g,' ').trim() });
                        }
                        return out;
                    }
                    """
                )
                browser.close()
        except Exception as exc:
            logging.exception("Browser fallback failed for %s", target["url"])
            return []
        seen = set()
        for job in jobs:
            url = clean(job.get("href"))
            if url in seen:
                continue
            seen.add(url)
            title = clean(job.get("title"))
            if not self.valid_job_url(url) or not self.valid_title(title):
                continue
            desc = clean(job.get("text"))
            row = self.make_row(
                target, title, url, "Unknown", "", self.classify_job_type("", "", desc),
                desc, "browser_fallback", location_source="none")
            rows.append(row)
        return rows

    # ── Orchestration ────────────────────────────────────────────────────────
    def scan_target(self, target):
        adapters = {
            "ashby": self.scan_ashby,
            "greenhouse": self.scan_greenhouse,
            "lever": self.scan_lever,
            "smartrecruiters": self.scan_smartrecruiters,
            "personio": self.scan_personio,
            "recruitee": self.scan_recruitee,
            "workable": self.scan_workable,
            "workday": self.scan_workday,
        }
        adapter = adapters.get(target["ats_type"])
        if adapter is None:
            logging.warning("Unsupported ATS type: %s", target["ats_type"])
            return []
        return adapter(target)

    def _ensure_output_header(self, columns, path):
        """Write the header if the file is missing/empty; otherwise verify the
        existing header matches exactly (never leave output headerless)."""
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            with open(path, "w", encoding="utf-8", newline="") as f:
                csv.DictWriter(f, fieldnames=columns).writeheader()
            return
        with open(path, encoding="utf-8") as f:
            first = next(csv.reader(f), None)
        if first != list(columns):
            raise ValueError(
                f"Output schema mismatch for {path}. "
                f"Expected {list(columns)!r}, found {first!r}. "
                "Use a fresh --output path or migrate the file."
            )

    def run(self):
        import os
        targets = self.read_seed_file()
        if self.only_companies:
            wanted = {c.strip().lower() for c in self.only_companies if c and c.strip()}
            targets = [t for t in targets if t.get("name", "").strip().lower() in wanted]
            if not targets:
                print(f"no ATS targets matched only_companies={self.only_companies}")
                return
        self._preflight_connectivity()

        base = self.output_file[:-4] if self.output_file.lower().endswith(".csv") else self.output_file
        recruiter_csv = base + "_recruiter.csv"
        quarantine_csv = base + "_quarantine.csv"
        scan_log_csv = base + "_scan_log.csv"

        # Fresh run: truncate + write headers. Resume: load existing canonical
        # IDs so only NEW requisitions are appended, and verify (or write) the
        # header so output files are never left headerless.
        if not self.resume:
            for path in (self.output_file, recruiter_csv, quarantine_csv):
                with open(path, "w", encoding="utf-8", newline="") as f:
                    csv.DictWriter(f, fieldnames=OUTPUT_FIELDS).writeheader()
            with open(scan_log_csv, "w", encoding="utf-8", newline="") as f:
                csv.DictWriter(f, fieldnames=LOG_FIELDS).writeheader()
            seen_ids = set()
        else:
            for path in (self.output_file, recruiter_csv, quarantine_csv):
                self._ensure_output_header(OUTPUT_FIELDS, path)
            self._ensure_output_header(LOG_FIELDS, scan_log_csv)
            # Load existing canonical IDs so resume dedupes against prior runs.
            seen_ids = set()
            for path in (self.output_file, recruiter_csv):
                if not os.path.exists(path):
                    continue
                with open(path, encoding="utf-8") as f:
                    reader = csv.reader(f)
                    next(reader, None)  # skip header
                    for row in reader:
                        if len(row) >= 18 and row[16]:
                            seen_ids.add(row[16])

        print(f"ATS scan started: {len(targets)} targets; run_id={self.run_id}; resume={self.resume}")

        for idx, target in enumerate(targets, 1):
            if self.cancel_event is not None and self.cancel_event.is_set():
                print(f"\nCANCELLED: stopping before target [{idx}/{len(targets)}] {target['name']}")
                break
            started = time.monotonic()
            print(f"\n[{idx}/{len(targets)}] {target['name']} ({target['ats_type']})")
            error = ""
            diagnostics = []
            if target["name"] in KNOWN_BOARD_ISSUES:
                diagnostics.append(KNOWN_BOARD_ISSUES[target["name"]])
            try:
                result = self.scan_target(target)
            except Exception as exc:
                result = []
                error = f"{type(exc).__name__}: {exc}"
                diagnostics.append(error)
            accepted = []
            quarantined = []
            duplicates = 0
            for row in result:
                cid = row["Canonical Job ID"]
                if row["Record Status"] == "quarantine":
                    quarantined.append(row)
                    continue
                if cid in seen_ids:
                    duplicates += 1
                    continue
                seen_ids.add(cid)
                accepted.append(row)
            dest = recruiter_csv if target["source_type"] == "recruiter" else self.output_file
            with open(dest, "a", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
                for r in accepted:
                    w.writerow({k: r.get(k, "") for k in OUTPUT_FIELDS})
            with open(quarantine_csv, "a", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
                for r in quarantined:
                    w.writerow({k: r.get(k, "") for k in OUTPUT_FIELDS})
            status = "error" if error and not accepted else ("ok" if accepted else "empty")
            with open(scan_log_csv, "a", encoding="utf-8", newline="") as f:
                csv.DictWriter(f, fieldnames=LOG_FIELDS).writerow({
                    "Run ID": self.run_id, "Seed Name": target["name"],
                    "Company": target["name"], "Source Type": target["source_type"],
                    "Target Country": "Global", "Status": status,
                    "Provider": target["ats_type"], "Jobs Found": len(accepted),
                    "Quarantined": len(quarantined), "Duplicates": duplicates,
                    "Rejected Scope": 0, "Error": error,
                    "Diagnostics": " | ".join(diagnostics)[-4000:],
                    "Duration Sec": round(time.monotonic() - started, 1),
                    "Seed URL": target["url"],
                })
            print(f"   {status.upper()}: wrote={len(accepted)}, quarantined={len(quarantined)}, dups={duplicates}")

        print(f"\nATS scan complete. Outputs:\n  Direct: {self.output_file}\n"
              f"  Recruiters: {recruiter_csv}\n  Quarantine: {quarantine_csv}\n  Log: {scan_log_csv}")
