"""Schema migration tests: evidence columns, scan evidence tables, legacy drops."""
import sqlite3

from sponsorscout.db import database as db

EVIDENCE_COLUMNS = [
    "visa_sponsorship", "relocation_support", "eu_blue_card_verdict",
    "relocation_required", "support_confidence", "support_evidence",
    "support_evidence_url", "support_evidence_type", "blue_card_evidence",
    "canonical_job_id", "run_id",
]
LEGACY_TABLES = {"user_ai_assets", "company_discovery_queue", "discoveries", "ats_health"}


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_jobs_table_has_evidence_columns(db_path):
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    missing = [c for c in EVIDENCE_COLUMNS if c not in cols]
    assert not missing, f"missing columns: {missing}"
    # Legacy boolean columns are kept during the transition.
    assert {"eu_blue_card", "has_relocation"} <= cols
    conn.close()


def test_scan_evidence_tables_exist(db_path):
    conn = sqlite3.connect(db_path)
    tables = _tables(conn)
    assert {"scan_runs", "scan_log"} <= tables
    conn.close()


def test_legacy_tables_are_dropped(db_path):
    conn = sqlite3.connect(db_path)
    assert not (_tables(conn) & LEGACY_TABLES)
    conn.close()


def test_scan_run_roundtrip(db_path):
    db.start_scan_run(db_path, "R1", method="quick", ats_companies=3, career_companies=5)
    db.record_scan_log_rows(db_path, "R1", "ats", [
        {"Seed Name": "acme", "Company": "Acme", "Status": "ok",
         "Jobs Found": "2", "Duration Sec": "1.5", "Provider": "ashby"},
    ])
    db.finish_scan_run(db_path, "R1", targets_ok=1, targets_empty=0,
                       targets_error=0, jobs_found=2, status="completed")
    runs = db.list_scan_runs(db_path)
    assert len(runs) == 1
    row = runs[0]
    assert row["run_id"] == "R1" and row["method"] == "quick"
    assert row["status"] == "completed" and row["jobs_found"] == 2
    assert row["ats_companies"] == 3 and row["career_companies"] == 5
    log = db.get_scan_log(db_path, "R1")
    assert len(log) == 1
    assert log[0]["seed_name"] == "acme" and log[0]["jobs_found"] == 2


def test_initialize_is_idempotent(db_path):
    conn = sqlite3.connect(db_path)
    db.initialize(db_path)  # second call must not fail or duplicate
    assert not (_tables(conn) & LEGACY_TABLES)
    conn.close()
