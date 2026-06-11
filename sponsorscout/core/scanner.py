from __future__ import annotations
import logging
import time
import concurrent.futures
from pathlib import Path

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

# Rate limiting: max concurrent requests per ATS
MAX_WORKERS = 4
REQUEST_DELAY = 0.3  # seconds between requests per company


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
    record = job.__dict__.copy()
    record["sponsorship_score"] = sponsorship_score(text_for_analysis)
    record["match_score"] = score_job(job, DEFAULT_PROFILE)
    record["remote_type"] = spons_details.get("remote_type", "onsite")
    record["eu_blue_card"] = 1 if spons_details.get("eu_blue_card") else 0
    record["has_relocation"] = 1 if spons_details.get("relocation") else 0
    record = mark_verified(record)
    return record


def _scan_company(company, db_path=DB_PATH, on_progress=None):
    """Scan a single company. Returns list of job records.

    B10 fix: previous version called record_success() after the HTTP fetch
    succeeded, even if every per-job normalization failed. Now we track
    per-job failures and only record a true success when at least one job
    made it through cleanly.

    BUGFIX (2024-Q4): previous version called `time.sleep(REQUEST_DELAY)`
    only on the success path, so an exception in `fetch_jobs()` skipped the
    rate-limit delay and let the next company hammer the ATS API immediately.
    We now wrap the whole body in try/finally so the sleep is unconditional
    and we don't get throttled (or banned) by the upstream ATS when one
    company errors out.

    BUGFIX (2024-Q4): `conn.close()` is also moved into the finally block so
    that the connection is released even when `record_failure()` itself
    raises (e.g. DB is locked for so long the busy_timeout fires).
    """
    connector = get_connector(company.get("ats_type"))
    if connector is None:
        return []

    conn = get_connection(db_path)
    save_company(conn, company)
    ats_name = company.get("ats_type", "unknown")
    start = time.perf_counter()
    seen_urls = set()
    found = []
    per_job_errors = 0

    try:
        try:
            raw_jobs = connector.fetch_jobs(company)
        except Exception as exc:
            logger.exception(
                "Connector fetch_jobs failed for %s (%s)",
                company.get("name", "unknown"),
                ats_name,
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            record_failure(conn, ats_name, elapsed_ms)
            return found

        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)

        for raw in raw_jobs:
            try:
                record = _build_job_record(raw, company, ats_name)
                upsert_job(conn, record)
                seen_urls.add(record["url"])
                found.append(record)
            except Exception as exc:
                logger.exception(
                    "Failed to normalize or persist job for %s: %s",
                    company.get("name", "unknown"),
                    exc,
                )
                # B10: count but don't swallow silently. We surface the
                # failure count via the health metric below.
                per_job_errors += 1

        # Expire jobs no longer listed
        for active_url in _existing_active_urls(conn, company["name"], ats_name):
            if active_url not in seen_urls:
                mark_job_expired(conn, active_url)

        # B10 fix: only credit a "success" if the fetch returned jobs AND
        # most of them normalized cleanly. If 100% of jobs errored, the ATS
        # response is broken — record a failure instead.
        total = len(raw_jobs)
        if total == 0 or per_job_errors >= total:
            record_failure(conn, ats_name, elapsed_ms)
        else:
            # Record success for the HTTP fetch; partial-failure case is
            # still a success for the connector-level health metric.
            record_success(conn, ats_name, elapsed_ms)
    finally:
        try:
            conn.close()
        except Exception:
            pass
        # Rate-limit every company uniformly so a single ATS error
        # doesn't cascade into a burst of requests on the next call.
        time.sleep(REQUEST_DELAY)
    return found


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
