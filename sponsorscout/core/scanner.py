from __future__ import annotations
import logging
import random
import time
import concurrent.futures
from pathlib import Path
from urllib.parse import urlparse

from sponsorscout.connectors import get_connector
from sponsorscout.core.normalizer import normalize_job
from sponsorscout.core.sponsorship import score as sponsorship_score, detect_sponsorship_keywords
from sponsorscout.core.scoring import score_job
from sponsorscout.core.persistence import upsert_job, save_company, save_discovery, mark_job_expired
from sponsorscout.core.verification import mark_verified
from sponsorscout.db.database import get_connection, DB_PATH
from sponsorscout.services.profile import DEFAULT_PROFILE
from sponsorscout.services.source_policy import classify_source
from sponsorscout.models.job import Job
from sponsorscout.services.ats_health import record_success, record_failure

from sponsorscout.core.portal_search import crawl_official_careers
from sponsorscout.core.ats_detection import detect_ats_from_links
from sponsorscout.core.http_client import http_session

logger = logging.getLogger(__name__)

# Rate limiting: max concurrent requests per ATS
MAX_WORKERS = 4

# Adaptive delay between companies (seconds)
# Base range — randomized slightly to appear more human-like
REQUEST_DELAY_MIN = 0.8
REQUEST_DELAY_MAX = 1.5

# Per-domain cooldown tracking — prevents hitting the same domain too fast
# Key: domain (e.g., "boards.greenhouse.io"), Value: last access timestamp
_domain_cooldowns: dict[str, float] = {}
DOMAIN_COOLDOWN_SECONDS = 3.0  # minimum seconds between requests to same domain
DOMAIN_BLOCK_BACKOFF = 5.0  # additional delay if domain was recently blocked


def _existing_active_urls(conn, company_name: str, ats_source: str) -> set[str]:
    rows = conn.execute(
        "SELECT url FROM jobs WHERE company = ? AND ats_source = ? AND verified_active = 1 AND is_expired = 0",
        (company_name, ats_source),
    ).fetchall()
    return {row["url"] for row in rows}


def _build_job_record(raw, company, connector_name):
    raw = dict(raw)
    raw.setdefault("company", company.get("name", "") or "")
    normalized = normalize_job(
        raw,
        "verified",
        connector_name,
        fallback_company=company.get("name", ""),
    )
    # Build the typed dataclass first, then enrich with computed fields.
    # Using ``Job(...)`` directly (instead of raw dict) keeps all scoring
    # fields declared in models/job.py - adding a column to the DB requires
    # only adding one dataclass field rather than chasing scattered dict
    # assignments across the scanner pipeline.
    job = Job(
        external_id=normalized["external_id"],
        title=normalized["title"],
        company=normalized["company"],
        country=normalized["country"],
        location=normalized["location"],
        url=normalized["url"],
        description=normalized["description"],
        ats_source=normalized["ats_source"],
        source_type="verified",
        source_name=connector_name,
    )
    text_for_analysis = (job.title or "") + " " + (job.description or "")
    spons_details = detect_sponsorship_keywords(text_for_analysis)
    record = job.to_record()
    record["sponsorship_score"] = sponsorship_score(text_for_analysis)
    record["match_score"] = score_job(job, DEFAULT_PROFILE)
    record["remote_type"] = spons_details.get("remote_type", "onsite")
    record["eu_blue_card"] = 1 if spons_details.get("eu_blue_card") else 0
    record["has_relocation"] = 1 if spons_details.get("relocation") else 0
    record = mark_verified(record)
    return record



def _scan_company(company, db_path=DB_PATH, on_progress=None):
    """Scan a single company. Returns list of job records.

    Official career-page jobs are harvested first. If the company also
    exposes a detectable ATS or has a known ATS, that ATS is scanned next
    and any additional jobs are merged in.
    """
    expected_ats = company.get("ats_type", "unknown")
    careers_url = company.get("careers_url", "").rstrip("/")

    detected_ats = ""
    detected_token = ""
    official_jobs = []

    # 1. Career Page First: Probe for ATS links and collect HTML jobs.
    # CSV careers_url is the user's hand-vetted source of truth; we always
    # scrape it first regardless of expected_ats. A successful scrape means
    # the official page won and we can skip the connector entirely.
    company_name = company.get("name", "unknown")
    if careers_url:
        with http_session() as session:
            try:
                portal_jobs, ats_links = crawl_official_careers(
                    session,
                    careers_url,
                    max_pages=8,
                    limit=300,
                    is_verified=(expected_ats == "official_careers"),
                )
                official_jobs = portal_jobs
                detected_ats, detected_token = detect_ats_from_links(ats_links)
                if official_jobs:
                    logger.info(
                        "Career page scrape for %s: %d jobs from %s",
                        company_name, len(official_jobs), careers_url,
                    )
                else:
                    logger.warning(
                        "Career page scrape for %s returned 0 jobs from %s "
                        "(will try connector as fallback)",
                        company_name, careers_url,
                    )
            except Exception as exc:
                logger.warning(
                    "Career page probe failed for %s (%s): %s",
                    company_name, careers_url, exc,
                )

    # 2. Decide which ATS to use as fallback when careers scrape was empty.
    # Priority: detected ATS (from links on the careers page) > expected ATS
    # (from CSV) > official_careers (re-scrape the URL via connector).
    if detected_ats:
        ats_to_use = detected_ats
        company["ats_board_token"] = detected_token
        if expected_ats and detected_ats != expected_ats:
            logger.info(
                "ATS mismatch for %s: expected %s but detected %s",
                company.get("name"), expected_ats, detected_ats
            )
    elif expected_ats and expected_ats != "official_careers" and expected_ats != "unknown":
        ats_to_use = expected_ats
    else:
        # Re-scrape via the connector - makes sure CSV careers_url gets
        # exercised with full Playwright fallback even if the first pass
        # returned 0 (which usually means JS-rendering was unavailable).
        ats_to_use = "official_careers"

    company["ats_type"] = ats_to_use
    connector = get_connector(ats_to_use)
    if connector is None and not official_jobs:
        return []

    conn = get_connection(db_path)
    save_company(conn, company)
    ats_name = ats_to_use
    start = time.perf_counter()
    found = []
    per_job_errors = 0
    global_seen_urls: set[str] = set()

    def _persist_jobs(raw_jobs, source_name: str):
        nonlocal per_job_errors
        source_seen_urls: set[str] = set()
        source_found = []
        for raw in raw_jobs:
            try:
                record = _build_job_record(raw, company, source_name)
                if record["url"] in global_seen_urls:
                    continue
                upsert_job(conn, record)
                global_seen_urls.add(record["url"])
                source_seen_urls.add(record["url"])
                found.append(record)
                source_found.append(record)
            except Exception as exc:
                logger.exception(
                    "Failed to normalize or persist job for %s: %s",
                    company.get("name", "unknown"),
                    exc,
                )
                per_job_errors += 1

        # Expire rows for this specific source only.
        for active_url in _existing_active_urls(conn, company["name"], source_name):
            if active_url not in source_seen_urls:
                mark_job_expired(conn, active_url)

        return source_found

    try:
        # 3. Persist official-careers jobs first.
        if official_jobs:
            official_raw_jobs = []
            for job in official_jobs:
                title = (job.title or "").strip()
                if not title or len(title) < 3:
                    continue
                official_raw_jobs.append(
                    {
                        "external_id": job.url,
                        "title": title,
                        "company": company.get("name", ""),
                        "country": company.get("country", ""),
                        "location": job.location,
                        "url": job.url,
                        "description": job.description or title,
                        "ats_source": "official_careers",
                    }
                )
            _persist_jobs(official_raw_jobs, "official_careers")

        # 4. Then scan the ATS board if the company has one.
        raw_jobs = []
        if ats_to_use != "official_careers" and connector is not None:
            try:
                raw_jobs = connector.fetch_jobs(company)
            except Exception as exc:
                logger.exception(
                    "Connector fetch_jobs failed for %s (%s)",
                    company.get("name", "unknown"),
                    ats_name,
                )
                raw_jobs = []

            if raw_jobs:
                # Use the ATS jobs as an additional source, after official jobs.
                _persist_jobs(raw_jobs, ats_name)
            elif not official_jobs:
                # No official jobs and no ATS jobs: expire any previously active
                # rows for this source before recording the failure.
                for active_url in _existing_active_urls(conn, company["name"], ats_name):
                    mark_job_expired(conn, active_url)
                elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
                record_failure(conn, ats_name, elapsed_ms)
                if expected_ats and expected_ats != ats_name and expected_ats != "unknown":
                    record_failure(conn, expected_ats, elapsed_ms)
                return found

        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)

        # Health bookkeeping. Official-careers success is only relevant if we
        # actually found jobs on the company portal.
        if official_jobs:
            record_success(conn, "official_careers", elapsed_ms)

        if raw_jobs:
            record_success(conn, ats_name, elapsed_ms)
            if expected_ats and expected_ats != ats_name and expected_ats != "unknown":
                record_failure(conn, expected_ats, elapsed_ms)
        elif not official_jobs:
            record_failure(conn, ats_name, elapsed_ms)
            if expected_ats and expected_ats != ats_name and expected_ats != "unknown":
                record_failure(conn, expected_ats, elapsed_ms)

        # If the company only has official jobs, return them now.
        return found
    finally:
        try:
            conn.close()
        except Exception:
            pass
        # Adaptive delay between companies to avoid rate limiting
        delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        
        # Apply per-domain cooldown: extract domain from careers_url and enforce
        # minimum gap between hits to the same domain.
        careers_domain = ""
        if careers_url:
            try:
                parsed = urlparse(careers_url)
                careers_domain = parsed.netloc.lower()
            except Exception:
                pass
        
        if careers_domain:
            now = time.time()
            last_access = _domain_cooldowns.get(careers_domain, 0.0)
            gap = now - last_access
            if gap < DOMAIN_COOLDOWN_SECONDS:
                # Need to wait longer to respect the cooldown
                extra_wait = DOMAIN_COOLDOWN_SECONDS - gap + random.uniform(0.1, 0.5)
                delay = max(delay, extra_wait)
            _domain_cooldowns[careers_domain] = time.time()
        
        time.sleep(delay)
    

def scan_all(companies, discovery_items=None, db_path=DB_PATH, parallel=False, on_progress=None):
    """
    Scan all companies with optional parallel execution.
    Returns list of all job records found.
    on_progress(msg, done, total): called after each company finishes.
    """
    found = []
    total = len(companies)
    done_count = [0]  # mutable counter for thread-safe increment

    def _wrapped(company):
        result = _scan_company(company, db_path, on_progress=on_progress)
        done_count[0] += 1
        if on_progress:
            n = len(result)
            label = f"✓ {company.get('name', '?')} — {n} job{'s' if n != 1 else ''}"
            on_progress(label, done_count[0], total)
        return result

    if parallel and total > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_wrapped, company): company for company in companies}
            for future in concurrent.futures.as_completed(futures):
                try:
                    found.extend(future.result())
                except Exception as exc:
                    logger.exception("Parallel scan thread failed: %s", exc)
    else:
        for company in companies:
            found.extend(_wrapped(company))

    if discovery_items:
        conn = get_connection(db_path)
        for item in discovery_items:
            try:
                source_type, trust_score, discovery_only = classify_source(item.get("source_name", ""))
                item["source_type"] = source_type
                item["trust_score"] = trust_score
                item["verified_active"] = not discovery_only
                item["freshness_score"] = 50 if discovery_only else 100
                if not discovery_only:
                    item = mark_verified(item)
                # Add remote/sponsorship analysis if description available
                text = (item.get("title", "") or "") + " " + (item.get("description", "") or "")
                spons_details = detect_sponsorship_keywords(text)
                item["remote_type"] = spons_details.get("remote_type", "onsite")
                item["eu_blue_card"] = 1 if spons_details.get("eu_blue_card") else 0
                item["has_relocation"] = 1 if spons_details.get("relocation") else 0
                upsert_job(conn, item)
                save_discovery(conn, item)
                found.append(item)
            except Exception as exc:
                logger.exception("Failed to persist discovery item %s: %s", item.get("source_name"), exc)
        conn.close()

    return found
