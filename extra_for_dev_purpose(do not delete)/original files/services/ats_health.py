
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sponsorscout.db.database import get_connection

def ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ats_health (
            ats_name TEXT PRIMARY KEY,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0,
            avg_response_ms REAL DEFAULT 0,
            last_success TEXT,
            last_failure TEXT
        )
        """
    )
    conn.commit()

def _update_rate(row_success: int, row_failure: int) -> float:
    total = row_success + row_failure
    return 0.0 if total <= 0 else round((row_success / total) * 100.0, 2)

def record_success(conn, ats_name: str, response_ms: float | None = None) -> None:
    row = conn.execute(
        "SELECT success_count, failure_count, avg_response_ms FROM ats_health WHERE ats_name = ?",
        (ats_name,),
    ).fetchone()
    now = datetime.now(timezone.utc).isoformat()

    if row is None:
        success_count = 1
        failure_count = 0
        avg = float(response_ms or 0.0)
    else:
        success_count = int(row[0]) + 1
        failure_count = int(row[1])
        prev_avg = float(row[2] or 0.0)
        total_before = success_count + failure_count - 1
        avg = float(response_ms or 0.0) if total_before <= 0 else round((prev_avg * total_before + float(response_ms or 0.0)) / (total_before + 1), 2)

    conn.execute(
        """
        INSERT INTO ats_health (ats_name, success_count, failure_count, success_rate, avg_response_ms, last_success, last_failure)
        VALUES (?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(ats_name) DO UPDATE SET
            success_count = excluded.success_count,
            failure_count = excluded.failure_count,
            success_rate = excluded.success_rate,
            avg_response_ms = excluded.avg_response_ms,
            last_success = excluded.last_success
        """,
        (ats_name, success_count, failure_count, _update_rate(success_count, failure_count), avg, now),
    )
    conn.commit()

def record_failure(conn, ats_name: str, response_ms: float | None = None) -> None:
    row = conn.execute(
        "SELECT success_count, failure_count, avg_response_ms FROM ats_health WHERE ats_name = ?",
        (ats_name,),
    ).fetchone()
    now = datetime.now(timezone.utc).isoformat()

    if row is None:
        success_count = 0
        failure_count = 1
        avg = float(response_ms or 0.0)
    else:
        success_count = int(row[0])
        failure_count = int(row[1]) + 1
        prev_avg = float(row[2] or 0.0)
        total_before = success_count + failure_count - 1
        avg = float(response_ms or 0.0) if total_before <= 0 else round((prev_avg * total_before + float(response_ms or 0.0)) / (total_before + 1), 2)

    conn.execute(
        """
        INSERT INTO ats_health (ats_name, success_count, failure_count, success_rate, avg_response_ms, last_success, last_failure)
        VALUES (?, ?, ?, ?, ?, NULL, ?)
        ON CONFLICT(ats_name) DO UPDATE SET
            success_count = excluded.success_count,
            failure_count = excluded.failure_count,
            success_rate = excluded.success_rate,
            avg_response_ms = excluded.avg_response_ms,
            last_failure = excluded.last_failure
        """,
        (ats_name, success_count, failure_count, _update_rate(success_count, failure_count), avg, now),
    )
    conn.commit()

def get_rows(db_path) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT ats_name, success_count, failure_count, success_rate, avg_response_ms, last_success, last_failure FROM ats_health ORDER BY success_rate DESC, success_count DESC, ats_name ASC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
