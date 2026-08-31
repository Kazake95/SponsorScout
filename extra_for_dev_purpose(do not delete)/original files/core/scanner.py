from __future__ import annotations
import logging
import random
import re
import time
import concurrent.futures
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

logger = logging.getLogger(__name__)

MAX_WORKERS = 4
REQUEST_DELAY_MIN = 0.8
REQUEST_DELAY_MAX = 1.5

import threading as _threading
_domain_cooldowns: dict[str, float] = {}
_domain_cooldowns_lock = _threading.Lock()
DOMAIN_COOLDOWN_SECONDS = 3.0

_domain_probe_cache: set[str] = set()
_domain_probe_lock = _threading.Lock()

_CAREERS_API_PROBE_PATHS = ["/api/jobs", "/jobs.json"]


def _existing_active_urls(conn, company_name: str, ats_source: str) -> set[str]:
    rows = conn.execute(
        "SELECT url FROM jobs WHERE company = ? AND ats_source = ? AND verified_active = 1 AND is_expired = 0",
        (company_name, ats_source),
    ).fetchall()
    return {row["url"] for row in rows}


def _existing_active_urls_for_company(conn, company_name: str) -> set[str]:
    rows = conn.execute(
        "SELECT url FROM jobs WHERE company = ? AND verified_active = 1 AND is_expired = 0",
        (company_name,),
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
    record["industry"] = company.get("industry", "")
    record = mark_verified(record)
    return record


def _probe_careers_api(careers_url: str, company_name: str) -> list[dict]:
    """Try a minimal set of JSON API paths when the HTML page is bot-blocked."""
    from urllib.parse import urlparse
    import json as _json
    from sponsorscout.core.http_client import http_session
    from sponsorscout.core.portal_search import _collect_jobs_from_json, PortalJob

    try:
        parsed = urlparse(careers_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        domain = parsed.netloc.lower()
    except Exception:
        return []

    with _domain_probe_lock:
        if domain in _domain_probe_cache:
            return []
        _domain_probe_cache.add(domain)

    results: list[dict] = []

    with http_session() as session:
        for i, path in enumerate(_CAREERS_API_PROBE_PATHS):
            probe_url = base + path
            try:
                if i > 0:
                    time.sleep(5.0)
                resp = session.get(probe_url, timeout=12)
                if not resp.ok:
                    continue
                ct = resp.headers.get("content-type", "").lower()
                if "json" not in ct and "javascript" not in ct:
                    text = (resp.text or "").strip()
                    if not (text.startswith("{") or text.startswith("[")):
                        continue
                else:
                    text = (resp.text or "").strip()

                blob = _json.loads(text)
                found: list[PortalJob] = []
                _collect_jobs_from_json(blob, probe_url, found, 300)
                if found:
                    logger.info(
                        "API probe hit for %s at %s — %d jobs",
                        company_name, probe_url, len(found),
                    )
                    for job in found:
                        results.append({
                            "external_id": job.url,
                            "title": job.title,
                            "url": job.url,
                            "location": job.location,
                            "description": job.description or job.title,
                            "ats_source": "official_careers",
                        })
                    break
            except Exception:
                continue

    return results


def _scan_company(company, db_path=DB_PATH, on_progress=None):
    """Scan a single company. Returns list of job records."""
    from sponsorscout.core.portal_search import crawl_official_careers, ATS_LINK_RE
    from sponsorscout.core.ats_detection import detect_ats_from_links

    expected_ats = company.get("ats_type", "unknown")
    careers_url = company.get("careers_url", "").rstrip("/")
    company_name = company.get("name", "unknown")

    detected_ats = ""
    detected_token = ""
    official_jobs = []

    # CRITICAL FIX: Only crawl generic career pages. Never crawl known ATS board URLs.
    should_crawl = expected_ats == "official_careers"

    # If the careers_url itself IS an ATS board link, skip crawl regardless
    if careers_url and ATS_LINK_RE.search(careers_url):
        pre_detected_ats, pre_detected_token = detect_ats_from_links([careers_url])
        if pre_detected_ats:
            logger.info(
                "careers_url for %s IS an ATS board (%s) — skipping portal crawl",
                company_name, pre_detected_ats,
            )
            detected_ats = pre_detected_ats
            detected_token = pre_detected_token
            company["ats_board_token"] = pre_detected_token
            should_crawl = False

    _portal_bot_blocked = False
    if should_crawl and careers_url:
        try:
            portal_jobs, ats_links, render_meta = crawl_official_careers(
                careers_url,
                max_pages=1,
                limit=300,
                is_verified=True,
            )
            _portal_bot_blocked = bool(render_meta.get("bot_blocked"))
            official_jobs = portal_jobs
            detected_ats, detected_token = detect_ats_from_links(ats_links)
            if official_jobs:
                logger.info(
                    "Career page scrape for %s: %d jobs from %s",
                    company_name, len(official_jobs), careers_url,
                )
            elif _portal_bot_blocked:
                logger.warning(
                    "Career page for %s is bot-blocked (%s) — marking for manual review",
                    company_name, careers_url,
                )
            else:
                logger.warning(
                    "Career page scrape for %s returned 0 jobs from %s",
                    company_name, careers_url,
                )
        except Exception as exc:
            logger.warning(
                "Career page probe failed for %s (%s): %s",
                company_name, careers_url, exc,
            )

    if detected_ats:
        ats_to_use = detected_ats
        company["ats_board_token"] = detected_token
        if expected_ats and detected_ats != expected_ats:
            logger.info(
                "ATS mismatch for %s: expected %s but detected %s",
                company_name, expected_ats, detected_ats
            )
    elif expected_ats and expected_ats not in ("official_careers", "unknown"):
        ats_to_use = expected_ats
    else:
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
        for raw in raw_jobs:
            try:
                record = _build_job_record(raw, company, source_name)
                if record["url"] in global_seen_urls:
                    continue
                upsert_job(conn, record)
                global_seen_urls.add(record["url"])
                source_seen_urls.add(record["url"])
                found.append(record)
            except Exception as exc:
                logger.exception(
                    "Failed to normalize or persist job for %s: %s",
                    company_name, exc,
                )
                per_job_errors += 1

        for active_url in _existing_active_urls(conn, company_name, source_name):
            if active_url not in source_seen_urls:
                mark_job_expired(conn, active_url)

    try:
        if official_jobs:
            official_raw_jobs = []
            for job in official_jobs:
                title = (job.title or "").strip()
                if not title or len(title) < 3:
                    continue
                official_raw_jobs.append({
                    "external_id": job.url,
                    "title": title,
                    "company": company_name,
                    "country": company.get("country", ""),
                    "location": job.location,
                    "url": job.url,
                    "description": job.description or title,
                    "ats_source": "official_careers",
                })
            _persist_jobs(official_raw_jobs, "official_careers")

        raw_jobs = []
        _skip_due_to_block = _portal_bot_blocked and ats_to_use == "official_careers"

        if _portal_bot_blocked and not detected_ats and careers_url:
            _bot_block_jobs = _probe_careers_api(careers_url, company_name)
            if _bot_block_jobs:
                logger.info(
                    "Bot-blocked page for %s — recovered %d jobs via API probe",
                    company_name, len(_bot_block_jobs),
                )
                _persist_jobs(_bot_block_jobs, "official_careers")

        if connector is not None and not _skip_due_to_block and (ats_to_use != "official_careers" or not official_jobs):
            try:
                raw_jobs = connector.fetch_jobs(company)
            except Exception as exc:
                logger.exception(
                    "Connector fetch_jobs failed for %s (%s)",
                    company_name, ats_name,
                )
                raw_jobs = []

            if raw_jobs:
                _persist_jobs(raw_jobs, ats_name)
            elif not official_jobs:
                for active_url in _existing_active_urls(conn, company_name, ats_name):
                    mark_job_expired(conn, active_url)
                elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
                record_failure(conn, ats_name, elapsed_ms)
                if expected_ats and expected_ats != ats_name and expected_ats != "unknown":
                    record_failure(conn, expected_ats, elapsed_ms)
                return found

        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)

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

        # Company-wide expiration
        for active_url in _existing_active_urls_for_company(conn, company_name):
            if active_url not in global_seen_urls:
                mark_job_expired(conn, active_url)

        return found
    finally:
        try:
            conn.close()
        except Exception:
            pass

        delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        careers_domain = ""
        if careers_url:
            try:
                parsed = urlparse(careers_url)
                careers_domain = parsed.netloc.lower()
            except Exception:
                pass

        if careers_domain:
            with _domain_cooldowns_lock:
                now = time.time()
                last_access = _domain_cooldowns.get(careers_domain, 0.0)
                gap = now - last_access
                if gap < DOMAIN_COOLDOWN_SECONDS:
                    extra_wait = DOMAIN_COOLDOWN_SECONDS - gap + random.uniform(0.1, 0.5)
                    delay = max(delay, extra_wait)
                _domain_cooldowns[careers_domain] = now

        time.sleep(delay)


def scan_all(companies, discovery_items=None, db_path=DB_PATH, parallel=False,
              on_progress=None, cancel_event=None):
    """Scan all companies with optional parallel execution."""
    found = []
    total = len(companies)
    done_count = [0]

    def _cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

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
            futures = {}
            for company in companies:
                if _cancelled():
                    break
                futures[executor.submit(_wrapped, company)] = company
            for future in concurrent.futures.as_completed(futures):
                try:
                    found.extend(future.result())
                except Exception as exc:
                    logger.exception("Parallel scan thread failed: %s", exc)
    else:
        for company in companies:
            if _cancelled():
                if on_progress:
                    on_progress("⏹ Stop requested — not starting further companies.",
                                 done_count[0], total)
                break
            found.extend(_wrapped(company))

    if discovery_items and not _cancelled():
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
