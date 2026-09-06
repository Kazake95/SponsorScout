"""Scan pipeline: orchestrates the ATS + career scanners and ingests results.

Design (locked with the project owner):

* The scanners keep their proven CLI behaviour — they write their own CSV
  artifacts (jobs, recruiter split, quarantine, per-run scan log) into
  ``paths.SCAN_OUTPUT_DIR``.  Nothing in the scanners was rewritten; only
  cooperative-cancel hooks and the progress shim were added.
* This module runs them (ATS first — it is API-fast — then the career
  crawler), then ingests the *accepted* job rows into the SQLite DB via
  ``persistence.upsert_job`` and copies the per-company scan-log rows into
  the ``scan_log`` table so the Tools tab can show per-scan evidence.
* Quarantined rows are never ingested as jobs (they stay in the quarantine
  CSV artifacts); their counts arrive via the scan-log rows.
* ``eu_blue_card`` / ``has_relocation`` (legacy INTEGER columns) are derived
  strictly from the verdict columns ('Y' -> 1, everything else -> 0), so
  Unknown is never presented as a hard "No" in boolean contexts either.
* ``sponsorship_score`` is derived from verdict + support confidence + the
  seed's ``sponsorship_history`` (locked decision #3), so the Dashboard
  "Sponsored" card and "strongest first" sorting keep working.
"""

from __future__ import annotations

import csv
import logging
import threading
import time
from pathlib import Path
from typing import Callable

from sponsorscout import paths
from sponsorscout.application import seed_manager
from sponsorscout.scanning.ats import ats_scanner as ats_module
from sponsorscout.scanning.career import career_scanner as career_module
from sponsorscout.core.location_country import country_from_location
from sponsorscout.core import persistence
from sponsorscout.db import database as db

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]


def _noop_progress(_msg: str) -> None:  # pragma: no cover
    pass


# ── Score / verdict derivation ───────────────────────────────────────────────

def derive_sponsorship_score(visa_verdict: str, confidence: float,
                             sponsorship_history) -> int:
    """Derive the 0-100 sponsorship score (locked decision #3).

    verdict 'Y'      -> base 70 (+ confidence bonus + seed history bonus)
    verdict Unknown  -> flat 35 (neutral: no bonuses from evidence the row
                        does not have — confidence and seed history must not
                        inflate an unevidenced verdict, nor drag it down)
    verdict 'N'      -> 0
    """
    verdict = str(visa_verdict or "").strip().lower()
    if verdict == "y":
        base = 70
    elif verdict == "n":
        return 0
    else:
        return 35
    try:
        conf = max(0.0, min(1.0, float(confidence or 0)))
    except (TypeError, ValueError):
        conf = 0.0
    try:
        history = max(0, min(100, int(sponsorship_history or 0)))
    except (TypeError, ValueError):
        history = 0
    score = base + conf * 20 + history * 0.10
    return int(round(max(0, min(100, score))))


def _as_verdict(value) -> str:
    """Normalise a scanner verdict cell to 'Y' / 'N' / 'Unknown' / ''."""
    v = str(value or "").strip()
    low = v.lower()
    if low in ("y", "yes", "true", "1"):
        return "Y"
    if low in ("n", "no", "false", "0"):
        return "N"
    if low == "unknown":
        return "Unknown"
    return ""


def _as_bool(verdict: str) -> int:
    """Legacy boolean derivation: strictly 'Y' -> 1, everything else 0."""
    return 1 if str(verdict or "").strip().lower() == "y" else 0


def _norm_location(value) -> str:
    v = str(value or "").strip()
    return "" if v.lower() in ("unknown", "not specified") else v


def _remote_type(row: dict) -> str:
    hay = f"{row.get('Job Type', '')} {row.get('Job Location', '')} {row.get('Raw Location', '')}".lower()
    return "remote" if "remote" in hay else "onsite"


def _job_country(row: dict) -> str:
    """Best-effort country (locked decision Q8): job-location parse first,
    then the seed's target country when it names a concrete country."""
    loc = _norm_location(row.get("Job Location"))
    if loc:
        country = country_from_location(loc)
        if country:
            return country
    target = str(row.get("Target Country") or "").strip()
    if target and target.lower() not in ("global", "unknown"):
        return target
    return ""


def _row_to_job(row: dict, *, source_subtype: str = "direct", run_id: str) -> dict | None:
    """Map one 35-column scanner output row to an ``upsert_job`` dict."""
    url = str(row.get("Job URL") or "").strip()
    title = str(row.get("Job Title") or "").strip()
    if not url or not title or title.lower() == "unknown":
        return None
    company = (str(row.get("Hiring Company") or "").strip()
               or str(row.get("Company Name") or "").strip()
               or str(row.get("Seed Name") or "").strip())
    if company.lower() == "unknown":
        # Recruiter rows carry Hiring Company='Unknown'; fall back to the
        # seed identity so the job is attributed to the scanned company.
        company = (str(row.get("Company Name") or "").strip()
                   or str(row.get("Seed Name") or "").strip() or "Unknown")
    visa = _as_verdict(row.get("Visa Sponsorship"))
    reloc = _as_verdict(row.get("Relocation Support"))
    blue = _as_verdict(row.get("EU Blue Card"))
    try:
        confidence = float(row.get("Support Confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    try:
        history = int(row.get("Sponsorship History Score") or 0)
    except (TypeError, ValueError):
        history = 0
    industry = str(row.get("Industry Type") or "").strip()
    if industry.lower() == "unknown":
        industry = ""
    return {
        "external_id": str(row.get("Canonical Job ID") or "").strip(),
        "title": title,
        "company": company,
        "country": _job_country(row),
        "location": _norm_location(row.get("Job Location")),
        "url": url,
        "ats_source": str(row.get("Provider") or "").strip(),
        "source_type": "verified",
        "source_subtype": source_subtype,
        "source_name": str(row.get("Seed Name") or "").strip(),
        "description": "",
        "trust_score": 80,
        "freshness_score": 0,
        "sponsorship_score": derive_sponsorship_score(visa, confidence, history),
        "match_score": 0,
        "verified_active": True,
        "is_expired": False,
        "remote_type": _remote_type(row),
        # Legacy derived booleans — strictly 'Y' -> 1 (Unknown is never a No).
        "eu_blue_card": _as_bool(blue),
        "has_relocation": _as_bool(reloc),
        # Authoritative three-state evidence (Q4 decision).
        "visa_sponsorship": visa,
        "relocation_support": reloc,
        "eu_blue_card_verdict": blue,
        "relocation_required": _as_verdict(row.get("Relocation Required")),
        "support_confidence": confidence,
        "support_evidence": str(row.get("Support Evidence") or "").strip(),
        "support_evidence_url": str(row.get("Support Evidence URL") or "").strip(),
        "support_evidence_type": str(row.get("Support Evidence Type") or "").strip(),
        "blue_card_evidence": str(row.get("Blue Card Evidence") or "").strip(),
        "canonical_job_id": str(row.get("Canonical Job ID") or "").strip(),
        "run_id": run_id,
        "industry": industry,
    }


# ── Ingestion ────────────────────────────────────────────────────────────────

def _ingest_output_csv(db_path, path: Path, run_id: str, source_subtype: str,
                       seen_canonical: set) -> tuple[int, int]:
    """Ingest accepted job rows from one scanner output CSV.

    Returns (ingested, duplicates).  Duplicates are rows whose canonical job
    ID was already ingested in this run (mirror URLs across scanners/files).
    """
    if not path or not path.exists():
        return 0, 0
    ingested = duplicates = 0
    conn = db.get_connection(db_path)
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                cid = str(row.get("Canonical Job ID") or "").strip()
                if cid and cid in seen_canonical:
                    duplicates += 1
                    continue
                job = _row_to_job(row, source_subtype=source_subtype, run_id=run_id)
                if job is None:
                    db.record_scan_event(
                        db_path, run_id, level="warning", phase="ingest",
                        company=str(row.get("Company Name") or row.get("Seed Name") or ""),
                        message="Skipped row (no valid URL / unparsable): "
                                + str(row.get("Job Title") or "")[:120])
                    continue
                try:
                    persistence.upsert_job(conn, job)
                except Exception:
                    logger.exception("Failed to upsert job %s", job.get("url"))
                    db.record_scan_event(
                        db_path, run_id, level="error", phase="ingest",
                        company=job.get("company", ""),
                        message=f"Failed to ingest job {job.get('url')}")
                    continue
                if cid:
                    seen_canonical.add(cid)
                ingested += 1
    finally:
        conn.close()
    return ingested, duplicates


def _ingest_scan_log(db_path, path: Path, run_id: str, scanner: str) -> int:
    """Copy one scanner's per-run scan-log CSV into the scan_log table."""
    if not path or not path.exists():
        return 0
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if rows:
        db.record_scan_log_rows(db_path, run_id, scanner, rows)
        # Elevate per-company failures into the event timeline so hidden errors
        # that reduce job yield are visible in the downloaded scan analysis.
        for row in rows:
            status = str(row.get("Status") or row.get("status") or "").lower()
            err = (row.get("Error") or row.get("error") or "").strip()
            if status in ("error", "failed", "partial") or err:
                db.record_scan_event(
                    db_path, run_id, level="error", phase=scanner,
                    company=str(row.get("Company") or row.get("Seed Name") or ""),
                    message=" | ".join(part for part in
                                       (err, str(row.get("Diagnostics") or "")) if part)[:2000])
    return len(rows)


def _count_seed_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return max(0, sum(1 for _ in csv.DictReader(f)))
    except OSError:
        return 0


def _infer_level(msg: str) -> str:
    low = msg.lower()
    if "error" in low or "failed" in low or "exception" in low or "✗" in low:
        return "error"
    if low.startswith("warning") or " warn" in low:
        return "warning"
    return "info"


def _infer_phase(msg: str) -> str:
    low = msg.lower()
    if low.startswith("scan "):
        return "pipeline"
    if "ats" in low:
        return "ats"
    if "career" in low:
        return "career"
    if "ingest" in low:
        return "ingest"
    return "pipeline"


def _event_tee(db_path, run_id: str, progress: ProgressFn) -> ProgressFn:
    """Wrap a progress callback so every line is also persisted to the run's
    scan_events timeline (level/phase inferred from the message text)."""
    def tee(msg: str) -> None:
        progress(msg)
        try:
            db.record_scan_event(
                db_path, run_id,
                level=_infer_level(msg),
                phase=_infer_phase(msg),
                message=str(msg),
            )
        except Exception:  # pragma: no cover - event logging must not crash scans
            pass
    return tee


class _LiveIngester(threading.Thread):
    """Progressively ingest scanner CSV rows while the scan is still running.

    Both scanners append accepted rows to their output CSVs company by
    company, so tailing them lets the Dashboard show live numbers during a
    scan instead of only after ingestion.  Ingestion is idempotent
    (``upsert_job`` upserts on the normalized URL and shares the run's
    ``seen_canonical`` dedup set), and the final bulk ingest at the end of
    ``run_scan`` re-upserts everything, so no special bookkeeping is needed.
    """

    def __init__(self, db_path, run_id: str,
                 csv_specs: list[tuple[Path, str]],
                 seen_canonical: set,
                 interval: float = 5.0,
                 progress: ProgressFn | None = None):
        super().__init__(name="LiveIngester", daemon=True)
        self.db_path = db_path
        self.run_id = run_id
        self.csv_specs = csv_specs
        self.seen_canonical = seen_canonical
        self.interval = interval
        self.progress = progress or _noop_progress
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        ingested_so_far = 0
        while not self._stop.wait(self.interval):
            try:
                for path, subtype in self.csv_specs:
                    ingested, _dups = _ingest_output_csv(
                        self.db_path, path, self.run_id,
                        source_subtype=subtype, seen_canonical=self.seen_canonical)
                    ingested_so_far += ingested
                if ingested_so_far:
                    self.progress(
                        f"Ingested live so far: {ingested_so_far} jobs "
                        "(Dashboard 'Refresh' reflects these)")
            except Exception:  # pragma: no cover - never kill the poller
                logger.exception("Live ingestion cycle failed")


# ── Orchestration ────────────────────────────────────────────────────────────

def run_scan(method: str = "quick",
             db_path=None,
             cancel_event: threading.Event | None = None,
             only_companies: list | None = None,
             progress: ProgressFn | None = None) -> dict:
    """Run a full scan campaign and ingest the results.

    method:
      * ``quick`` — ATS boards + career pages, no detail-page enrichment.
      * ``full``  — same plus per-job detail-page evidence enrichment
                    (Playwright; significantly slower).

    only_companies: optional list of company names — when given, only those
      seed targets are scanned (CLI --company).

    Must be called from a worker thread (it performs network I/O); the UI
    layer receives progress via ``progress`` and cancellation via the shared
    ``cancel_event``.  Returns a summary dict for the Tools tab.
    """
    method = "full" if method == "full" else "quick"
    progress = progress or _noop_progress
    cancel_event = cancel_event or threading.Event()
    db_path = str(db_path or paths.DB_PATH)
    out_dir = paths.ensure_scan_output_dir()
    paths.ensure_user_data_dir()

    # Make sure user-editable seed copies exist (bundled defaults on first run).
    seed_manager.ensure_user_seeds()

    # Make sure the schema (incl. scan_runs/scan_log + evidence columns) exists.
    try:
        db.initialize(db_path)
    except TypeError:  # pragma: no cover - older signature fallback
        db.initialize()

    run_id = time.strftime("%Y%m%dT%H%M%S")
    # Tee every progress line into the run's scan_events timeline for later
    # download / analysis (phase + level inferred from the message text).
    progress = _event_tee(db_path, run_id, progress)
    ats_out = out_dir / f"{run_id}_ats_jobs.csv"
    career_out = out_dir / f"{run_id}_career_jobs.csv"
    detail = method == "full"

    phase_errors: list[str] = []
    cancelled = False
    ats_csv = career_csv = None

    summary = {
        "run_id": run_id,
        "method": method,
        "cancelled": False,
        "status": "completed",
        "ingested": 0,
        "duplicates": 0,
        "log_rows": 0,
        "artifacts": {},
        "errors": phase_errors,
    }

    n_ats = _count_seed_rows(seed_manager.user_ats_path())
    n_career = _count_seed_rows(seed_manager.user_career_path())
    if only_companies:
        wanted = {c.strip().lower() for c in only_companies if c and c.strip()}
        if wanted:
            n_ats = sum(
                1 for r in seed_manager.read_seed_rows(
                    seed_manager.user_ats_path())["rows"]
                if r.get("name", "").strip().lower() in wanted)
            n_career = sum(
                1 for r in seed_manager.read_seed_rows(
                    seed_manager.user_career_path())["rows"]
                if r.get("name", "").strip().lower() in wanted)
    db.start_scan_run(db_path, run_id, method, n_ats, n_career)
    progress(f"Scan {run_id} started: method={method}, "
             f"ATS companies={n_ats}, career companies={n_career}")

    # Live ingestion: scanners write accepted rows to their CSVs company by
    # company, so tail them into the DB while the scan runs. This makes the
    # Dashboard's Refresh button show live numbers mid-scan. The final bulk
    # ingest below re-upserts everything (idempotent), so counts stay exact.
    seen_canonical: set = set()
    live = _LiveIngester(
        db_path, run_id,
        csv_specs=[
            (ats_out, "direct"),
            (ats_out.with_name(ats_out.stem + "_recruiter.csv"), "recruiter"),
            (career_out, "direct"),
            (career_out.with_name(career_out.stem + "_recruiter.csv"), "recruiter"),
        ],
        seen_canonical=seen_canonical,
        progress=progress,
    )
    live.start()

    # 1 ─ ATS scan (API-first, fast) ------------------------------------------
    if n_ats > 0:
        try:
            scanner = ats_module.ATSScanner(
                seed_file=str(seed_manager.user_ats_path()),
                output_file=str(ats_out),
                cancel_event=cancel_event,
                only_companies=only_companies,
            )
            scanner.run_id = run_id
            ats_module.progress_cb = progress
            scanner.run()
            ats_csv = ats_out
            if cancel_event.is_set():
                cancelled = True
        except Exception as exc:  # preflight failure, seed errors, network down
            logger.exception("ATS scan phase failed")
            phase_errors.append(f"ATS: {type(exc).__name__}: {exc}")
            progress(f"ATS scan failed: {exc}")
    else:
        progress("No ATS seed rows — skipping ATS phase")

    # 2 ─ Career crawl (browser-heavy) ----------------------------------------
    if n_career == 0:
        progress("No career seed rows — skipping career phase")
    elif cancel_event.is_set() and ats_csv is None:
        # Cancelled during ATS with nothing produced: honour the stop fully.
        cancelled = True
    else:
        try:
            scanner = career_module.CareerPortalScanner(
                input_csv=str(seed_manager.user_career_path()),
                output_csv=str(career_out),
                detail_scan=detail,
                cancel_event=cancel_event,
                only_companies=only_companies,
            )
            scanner.run_id = run_id
            career_module.progress_cb = progress
            scanner.execute_crawler()
            career_csv = career_out
            if cancel_event.is_set():
                cancelled = True
        except Exception as exc:
            logger.exception("Career scan phase failed")
            phase_errors.append(f"Career: {type(exc).__name__}: {exc}")
            progress(f"Career scan failed: {exc}")

    # 3 ─ Ingest accepted rows + scan logs into the DB ------------------------
    live.stop()
    live.join(timeout=15)
    # Deliberately a *fresh* dedup set: the final pass re-reads every row once
    # so the summary counts match the previous bulk-only behaviour exactly
    # (rows already ingested live are simply upserted again, idempotently).
    seen_canonical: set = set()
    ingested_total = dup_total = log_rows_total = 0
    for csv_base, scanner_label in ((ats_csv, "ats"), (career_csv, "career")):
        if csv_base is None:
            continue
        try:
            ingested, dups = _ingest_output_csv(
                db_path, csv_base, run_id,
                source_subtype="direct", seen_canonical=seen_canonical)
            rec_ing, rec_dups = _ingest_output_csv(
                db_path, csv_base.with_name(csv_base.stem + "_recruiter.csv"),
                run_id, source_subtype="recruiter",
                seen_canonical=seen_canonical)
            log_rows = _ingest_scan_log(
                db_path, csv_base.with_name(csv_base.stem + "_scan_log.csv"),
                run_id, scanner_label)
        except Exception as exc:
            logger.exception("Ingestion failed for %s", csv_base)
            phase_errors.append(
                f"Ingest({scanner_label}): {type(exc).__name__}: {exc}")
            continue
        ingested_total += ingested + rec_ing
        dup_total += dups + rec_dups
        log_rows_total += log_rows
        summary["artifacts"][scanner_label] = {
            "jobs": str(csv_base),
            "recruiter": str(csv_base.with_name(csv_base.stem + "_recruiter.csv")),
            "quarantine": str(csv_base.with_name(csv_base.stem + "_quarantine.csv")),
            "scan_log": str(csv_base.with_name(csv_base.stem + "_scan_log.csv")),
        }

    summary["ingested"] = ingested_total
    summary["duplicates"] = dup_total
    summary["log_rows"] = log_rows_total
    summary["cancelled"] = cancelled
    if phase_errors and ingested_total == 0:
        summary["status"] = "error"
    elif cancelled:
        summary["status"] = "cancelled"
    elif phase_errors:
        summary["status"] = "partial"
    else:
        summary["status"] = "completed"

    try:
        db.finish_scan_run(
            db_path, run_id,
            jobs_found=ingested_total, jobs_duplicates=dup_total,
            status=summary["status"],
            error="; ".join(phase_errors)[:2000],
        )
    except Exception:  # pragma: no cover - evidence logging must not crash
        logger.exception("Failed to finalise scan_runs row")

    progress(f"Scan {run_id} finished: status={summary['status']}, "
             f"ingested={ingested_total}, duplicates={dup_total}")
    return summary
