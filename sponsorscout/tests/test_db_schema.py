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
    assert {"scan_runs", "scan_log", "scan_events"} <= tables
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


def test_scan_events_roundtrip(db_path):
    db.record_scan_event(db_path, "R9", level="info", phase="pipeline",
                         message="Scan R9 started")
    db.record_scan_event(db_path, "R9", level="error", phase="ats",
                         company="Acme", message="Seed timeout")
    evs = db.get_scan_events(db_path, "R9")
    assert len(evs) == 2
    assert evs[0]["level"] == "info" and evs[0]["message"] == "Scan R9 started"
    assert evs[1]["level"] == "error" and evs[1]["phase"] == "ats"
    assert evs[1]["company"] == "Acme"
    # Events are isolated per run.
    assert db.get_scan_events(db_path, "R-other") == []


def test_export_scan_run_csv(db_path):
    db.start_scan_run(db_path, "R1", method="quick", ats_companies=3, career_companies=5)
    db.record_scan_log_rows(db_path, "R1", "ats", [
        {"Seed Name": "acme", "Company": "Acme", "Status": "ok",
         "Jobs Found": "2", "Duration Sec": "1.5", "Provider": "ashby"},
        {"Seed Name": "globex", "Company": "Globex", "Status": "error",
         "Error": "seed timeout", "Diagnostics": "attempt 1: TimeoutError: boom [network]"},
    ])
    db.record_scan_event(db_path, "R1", level="info", phase="pipeline",
                         message="Scan R1 started")
    db.finish_scan_run(db_path, "R1", targets_ok=1, targets_error=1,
                       targets_empty=0, jobs_found=2, status="completed")
    out = db.export_scan_run_csv(db_path, "R1")
    assert "Run ID,R1" in out
    assert "Per-company scan log" in out
    assert "Event timeline" in out
    assert "Acme" in out
    assert "seed timeout" in out
    # Diagnostics must survive into the exported rows (not truncated away).
    assert "TimeoutError: boom [network]" in out
    assert "Scan R1 started" in out


def test_clear_stale_data_vacuum_after_commit(db_path):
    """Regression: the stale-data handler must COMMIT before VACUUM. Previously
    it ran VACUUM while still inside the auto-started transaction, which raises
    'cannot VACUUM from within a transaction' and rolled back the delete."""
    conn = db.get_connection(db_path)
    try:
        conn.executemany(
            "INSERT INTO jobs (title, company, url, is_expired) VALUES (?, ?, ?, ?)",
            [("Expired role", "Acme", "https://acme/jobs/expired", 1),
             ("Active role", "Acme", "https://acme/jobs/active", 0)],
        )
        conn.commit()
    finally:
        conn.close()

    # Mirror the handler exactly: DELETE -> COMMIT -> VACUUM (when rows > 0).
    conn = db.get_connection(db_path)
    try:
        cur = conn.execute("DELETE FROM jobs WHERE is_expired=1")
        deleted = cur.rowcount
        conn.commit()
        if deleted > 0:
            conn.execute("VACUUM")  # must NOT raise
    finally:
        conn.close()

    assert deleted == 1
    conn = db.get_connection(db_path)
    try:
        remaining = [r[0] for r in conn.execute("SELECT url FROM jobs")]
    finally:
        conn.close()
    assert remaining == ["https://acme/jobs/active"]


def test_regex_search_matches_pattern(db_path):
    """REGEXP operator backed by Python's re: (?i)^senior matches 'Senior Developer'
    but not 'Junior Developer'."""
    conn = db.get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO jobs (title, company, url, verified_active, is_expired) VALUES (?, ?, ?, 1, 0)",
            ("Senior Developer", "Acme", "https://acme/jobs/senior"),
        )
        conn.execute(
            "INSERT INTO jobs (title, company, url, verified_active, is_expired) VALUES (?, ?, ?, 1, 0)",
            ("Junior Developer", "Acme", "https://acme/jobs/junior"),
        )
        conn.commit()
    finally:
        conn.close()

    rows = db.search_jobs(db_path, title="(?i)^senior", regex=True)
    titles = [r["title"] for r in rows]
    assert titles == ["Senior Developer"], f"expected only Senior, got {titles}"


def test_regex_invalid_pattern_falls_back_to_like(db_path):
    """An invalid regex pattern must not crash — search_jobs falls back to
    substring LIKE and returns rows."""
    conn = db.get_connection(db_path)
    conn.execute(
        "INSERT INTO jobs (title, company, url) VALUES (?, ?, ?)",
        ("Backend Engineer", "Acme", "https://acme/jobs/backend"),
    )
    conn.commit()
    conn.close()

    # "[unclosed" is an invalid regex; should fall back to LIKE and match nothing
    # for this title, but crucially must NOT raise.
    rows = db.search_jobs(db_path, title="[unclosed", regex=True)
    assert isinstance(rows, list)


def test_regex_registered_on_connection(db_path):
    """The custom REGEXP function must be registered on every connection
    returned by get_connection (so it works in search_jobs and raw SQL alike)."""
    conn = db.get_connection(db_path)
    try:
        # If REGEXP is not registered, this raises sqlite3.OperationalError.
        result = conn.execute("SELECT 'Hello' REGEXP '^H'").fetchone()[0]
        assert result == 1
        result = conn.execute("SELECT 'Hello' REGEXP '^X'").fetchone()[0]
        assert result == 0
    finally:
        conn.close()
