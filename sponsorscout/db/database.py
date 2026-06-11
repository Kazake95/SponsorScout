from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from sponsorscout.paths import DB_PATH, ensure_user_data_dir

logger = logging.getLogger(__name__)


@contextmanager
def _get_conn(db_path=DB_PATH):
    """Context manager for database connections ensuring proper cleanup."""
    conn = None
    try:
        db_path = Path(db_path).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        ensure_user_data_dir()
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # B3 fix: WAL allows concurrent readers but only one writer. Without a
        # busy_timeout, parallel scanners would fail with "database is locked"
        # the moment two threads tried to commit at the same time.
        conn.execute("PRAGMA busy_timeout=5000")
        # Performance: NORMAL is safe with WAL; reduces fsync overhead.
        conn.execute("PRAGMA synchronous=NORMAL")
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def get_connection(db_path=DB_PATH):
    db_path = Path(db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_user_data_dir()
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # B3 fix: WAL allows concurrent readers but only one writer. Without a
    # busy_timeout, parallel scanners would fail with "database is locked"
    # the moment two threads tried to commit at the same time.
    conn.execute("PRAGMA busy_timeout=5000")
    # Performance: NORMAL is safe with WAL; reduces fsync overhead.
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _apply_migrations(conn):
    """Apply schema migrations safely (idempotent via column existence checks)."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    migrations = [
        ("remote_type", "ALTER TABLE jobs ADD COLUMN remote_type TEXT DEFAULT 'onsite'"),
        ("eu_blue_card", "ALTER TABLE jobs ADD COLUMN eu_blue_card INTEGER DEFAULT 0"),
        ("has_relocation", "ALTER TABLE jobs ADD COLUMN has_relocation INTEGER DEFAULT 0"),
        # BUGFIX: support the new "Experience" filter (v0.4.2).
        ("experience_level", "ALTER TABLE jobs ADD COLUMN experience_level TEXT DEFAULT ''"),
    ]
    for col, sql in migrations:
        if col not in existing_cols:
            try:
                conn.execute(sql)
            except Exception as exc:
                logger.exception("Failed to apply migration for column %s", col)
                raise

    # New tables and indexes that depend on migration-added columns.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS company_discovery_queue (
            id INTEGER PRIMARY KEY,
            careers_url TEXT UNIQUE NOT NULL,
            ats_type TEXT DEFAULT 'official_careers',
            company_name TEXT DEFAULT '',
            country TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_discovery_status ON company_discovery_queue(status);
    """)

    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}

    if "remote_type" in existing_cols:
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_remote ON jobs(remote_type)")
        except Exception as exc:
            logger.exception("Failed to create idx_jobs_remote: %s", exc)

    if "experience_level" in existing_cols:
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_experience ON jobs(experience_level) WHERE experience_level IS NOT NULL AND experience_level != ''"
            )
        except Exception as exc:
            logger.exception("Failed to create idx_jobs_experience: %s", exc)

    conn.commit()

    # Sanity check that essential migration columns exist.
    expected_cols = {"remote_type", "eu_blue_card", "has_relocation", "experience_level"}
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    missing = expected_cols - existing_cols
    if missing:
        logger.error(
            "Database schema verification failed: missing columns %s",
            sorted(missing),
        )
        raise RuntimeError(
            f"Database initialization failed; missing columns: {', '.join(sorted(missing))}"
        )


def initialize(db_path=DB_PATH):
    conn = get_connection(db_path)
    try:
        conn.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        conn.commit()
        _apply_migrations(conn)
        # Create the ats_health table at startup so callers don't need to
        # call ensure_table() on every record_success/record_failure call.
        from sponsorscout.services.ats_health import ensure_table
        ensure_table(conn)
        # Fix country/location mismatch for any existing records
        from sponsorscout.db.migrate_countries import migrate_job_countries
        migrate_job_countries(conn)
        conn.commit()
    finally:
        conn.close()


def search_jobs(db_path, title="", company="", country="All", source_type="All",
                verified_only=True, sponsorship_only=False, active_only=True,
                remote_filter="All", eu_blue_card_only=False, relocation_only=False,
                experience_filter="All", sort_by="best"):
    conn = None
    try:
        conn = get_connection(db_path)
        # BUGFIX (v0.4.2): the SELECT now also pulls `experience_level` and
        # `first_seen_at` so the UI can render the new filter chip and the
        # new "Latest" sort. The COALESCE on experience_level means legacy
        # rows with NULL/'' show up under 'All' rather than getting filtered
        # out by the experience filter.
        query = """SELECT title, company, country, location, source_type, source_name,
                   trust_score, freshness_score, sponsorship_score, match_score,
                   verified_active, is_expired, url, last_verified_at, description,
                   first_seen_at,
                   COALESCE(remote_type, 'onsite') as remote_type,
                   COALESCE(eu_blue_card, 0) as eu_blue_card,
                   COALESCE(has_relocation, 0) as has_relocation,
                   COALESCE(experience_level, '') as experience_level
                   FROM jobs WHERE 1=1"""
        params = []
        if title:
            query += " AND lower(title) LIKE ?"
            params.append(f"%{title.lower()}%")
        if company:
            query += " AND lower(company) LIKE ?"
            params.append(f"%{company.lower()}%")
        if country and country != "All":
            # Match jobs whose country matches the filter, or remote roles
            # that are explicitly EU/EMEA remote and therefore relevant to the
            # selected country.
            query += (
                " AND (country = ? "
                "OR (country = '' AND remote_type IN ('remote_eu','remote_emea')) )"
            )
            params.append(country)
        if source_type and source_type != "All":
            query += " AND source_type = ?"
            params.append(source_type)
        if verified_only:
            query += " AND verified_active = 1"
        if active_only:
            query += " AND is_expired = 0"
        if sponsorship_only:
            query += " AND sponsorship_score >= 70"
        if remote_filter and remote_filter != "All":
            if remote_filter == "Remote EU":
                query += " AND remote_type = 'remote_eu'"
            elif remote_filter == "Remote EMEA":
                query += " AND remote_type IN ('remote_eu', 'remote_emea')"
            elif remote_filter == "Remote Global":
                query += " AND remote_type IN ('remote_eu', 'remote_emea', 'remote_global', 'remote')"
            elif remote_filter == "Hybrid":
                query += " AND remote_type = 'hybrid'"
            elif remote_filter == "Remote Only":
                query += " AND remote_type IN ('remote_eu', 'remote_emea', 'remote_global', 'remote')"
        if eu_blue_card_only:
            query += " AND eu_blue_card = 1"
        if relocation_only:
            query += " AND has_relocation = 1"
        if experience_filter and experience_filter != "All":
            # BUGFIX: previous version had no experience filter, so users
            # couldn't separate "Senior Engineer" from "Entry Level" jobs.
            # The 'All' option also matches NULL/empty so legacy rows are
            # not silently dropped from the result set.
            if experience_filter == "Any (incl. unknown)":
                pass  # no filter
            elif experience_filter == "Unknown / Not classified":
                query += " AND (experience_level IS NULL OR experience_level = '')"
            else:
                query += " AND experience_level = ?"
                params.append(experience_filter.lower())
        # BUGFIX (v0.4.2): new sort modes. Default 'best' keeps the old
        # behavior (trust, freshness, match, sponsorship). 'latest' sorts
        # by when the job first appeared in the database so users see the
        # freshest postings first. 'sponsorship' is a shortcut for "show me
        # the most sponsorship-likely jobs first".
        if sort_by == "latest":
            query += " ORDER BY first_seen_at DESC, trust_score DESC"
        elif sort_by == "sponsorship":
            query += " ORDER BY sponsorship_score DESC, first_seen_at DESC, match_score DESC"
        else:  # 'best' or anything else
            query += " ORDER BY trust_score DESC, freshness_score DESC, match_score DESC, sponsorship_score DESC, last_verified_at DESC"
        rows = conn.execute(query, params).fetchall()
        return rows
    finally:
        if conn:
            conn.close()


# Canonical list of experience buckets for the UI dropdown. Order
# matters: this is the order they appear in the combobox.
EXPERIENCE_LEVELS = [
    "All",
    "Any (incl. unknown)",
    "Intern",
    "Entry",
    "Mid",
    "Senior",
    "Lead",
    "Exec",
    "Unknown / Not classified",
]

# Sort modes for the Search tab.
SORT_MODES = [
    ("Best match", "best"),
    ("Latest", "latest"),
    ("Sponsored first", "sponsorship"),
]


# BUGFIX (2024-Q4 round 2): the previous threshold of `>= 20` was too
# LOW for the `score()` function. The baseline is 20 with no signals at
# all, and most real jobs score exactly 20-30 even when there's no
# positive signal. With threshold 20 the "Sponsored" card was reporting
# ~98% of all jobs as sponsored, which is meaningless. We now use the
# 70-point threshold, which is what the Search tab's "Sponsored Only"
# filter already uses, so the dashboard and the search filter agree.
# A job must score >= 70 to be considered "sponsored" -- this is the
# level at which the text contained MULTIPLE positive signals, not just
# the baseline. The "Top companies by sponsorship score" table still
# uses the unfiltered MAX so users can see the gradient.
SPONSORSHIP_SCORE_THRESHOLD = 70


def get_dashboard_stats(db_path):
    conn = None
    try:
        conn = get_connection(db_path)
        stats = {
            "companies": conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
            "verified_jobs": conn.execute("SELECT COUNT(*) FROM jobs WHERE verified_active = 1 AND is_expired = 0").fetchone()[0],
            "discovery_jobs": conn.execute("SELECT COUNT(*) FROM jobs WHERE source_type = 'discovery'").fetchone()[0],
            # BUGFIX (round 1): previous version used a per-company COUNT(DISTINCT)
            # with a `>= 50` threshold, which produced 0 in almost every real
            # dataset. We now count JOBS (not companies) at the same threshold
            # the Search tab's "Sponsored Only" filter uses, so the numbers
            # on the dashboard always agree with what the user can filter for.
            "sponsored_jobs": conn.execute(
                "SELECT COUNT(*) FROM jobs "
                "WHERE sponsorship_score >= ? AND verified_active = 1 AND is_expired = 0",
                (SPONSORSHIP_SCORE_THRESHOLD,),
            ).fetchone()[0],
            "sponsored_companies": conn.execute(
                "SELECT COUNT(DISTINCT company) FROM jobs "
                "WHERE sponsorship_score >= ? AND verified_active = 1 AND is_expired = 0",
                (SPONSORSHIP_SCORE_THRESHOLD,),
            ).fetchone()[0],
            "applications": conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0],
            "countries": conn.execute("SELECT COUNT(DISTINCT country) FROM jobs WHERE country <> ''").fetchone()[0],
            "recent_jobs": conn.execute("SELECT COUNT(*) FROM jobs WHERE first_seen_at >= datetime('now', '-7 days')").fetchone()[0],
            "remote_jobs": conn.execute("SELECT COUNT(*) FROM jobs WHERE remote_type IN ('remote_eu','remote_emea','remote_global','remote') AND verified_active=1 AND is_expired=0").fetchone()[0],
            "eu_blue_card_jobs": conn.execute("SELECT COUNT(*) FROM jobs WHERE eu_blue_card=1 AND verified_active=1 AND is_expired=0").fetchone()[0],
        }
        return stats
    finally:
        if conn:
            conn.close()


def get_dashboard_top_companies(db_path, limit=8):
    conn = None
    try:
        conn = get_connection(db_path)
        rows = conn.execute("""
            SELECT company, country, COUNT(*) as job_count, MAX(sponsorship_score) as max_sponsor, MAX(match_score) as max_match
            FROM jobs
            WHERE verified_active = 1 AND is_expired = 0
            GROUP BY company, country
            ORDER BY max_sponsor DESC, max_match DESC, job_count DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return rows
    finally:
        if conn:
            conn.close()


def get_dashboard_country_counts(db_path):
    conn = None
    try:
        conn = get_connection(db_path)
        rows = conn.execute("""
            SELECT country, COUNT(*) as count
            FROM jobs
            WHERE verified_active = 1 AND is_expired = 0 AND country <> ''
            GROUP BY country
            ORDER BY count DESC, country ASC
        """).fetchall()
        return rows
    finally:
        if conn:
            conn.close()


def get_dashboard_ats_health(db_path):
    from sponsorscout.services.ats_health import get_rows
    return get_rows(db_path)


def upsert_application(db_path, job_url, company, title, status="saved",
                       applied_at=None, next_followup_at=None, notes=""):
    conn = None
    try:
        conn = get_connection(db_path)
        conn.execute("""
            INSERT INTO applications (job_url, company, title, status, applied_at, next_followup_at, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(job_url) DO UPDATE SET
                company=excluded.company,
                title=excluded.title,
                status=excluded.status,
                applied_at=excluded.applied_at,
                next_followup_at=excluded.next_followup_at,
                notes=excluded.notes,
                updated_at=CURRENT_TIMESTAMP
        """, (job_url, company, title, status, applied_at, next_followup_at, notes))
        conn.commit()
    finally:
        if conn:
            conn.close()


def list_applications(db_path):
    conn = None
    try:
        conn = get_connection(db_path)
        rows = conn.execute(
            "SELECT company, title, status, applied_at, next_followup_at, notes, job_url FROM applications ORDER BY updated_at DESC"
        ).fetchall()
        return rows
    finally:
        if conn:
            conn.close()


def enqueue_discovery(db_path, careers_url: str, ats_type: str = "official_careers",
                      company_name: str = "", country: str = ""):
    conn = None
    try:
        conn = get_connection(db_path)
        conn.execute("""
            INSERT OR IGNORE INTO company_discovery_queue (careers_url, ats_type, company_name, country)
            VALUES (?, ?, ?, ?)
        """, (careers_url, ats_type, company_name, country))
        conn.commit()
    finally:
        if conn:
            conn.close()


def get_pending_discovery(db_path, limit: int = 20) -> list[dict]:
    conn = None
    try:
        conn = get_connection(db_path)
        rows = conn.execute(
            "SELECT * FROM company_discovery_queue WHERE status='pending' ORDER BY discovered_at ASC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if conn:
            conn.close()


def mark_discovery_processed(db_path, careers_url: str, status: str = "processed"):
    conn = None
    try:
        conn = get_connection(db_path)
        conn.execute(
            "UPDATE company_discovery_queue SET status=?, processed_at=CURRENT_TIMESTAMP WHERE careers_url=?",
            (status, careers_url)
        )
        conn.commit()
    finally:
        if conn:
            conn.close()


def delete_application(db_path, job_url: str):
    conn = None
    try:
        conn = get_connection(db_path)
        conn.execute("DELETE FROM applications WHERE job_url=?", (job_url,))
        conn.commit()
    finally:
        if conn:
            conn.close()
