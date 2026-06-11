"""
One-time migration: re-derive country from location for all existing jobs.

Run automatically on app startup via initialize(), or manually:
    python3 -m sponsorscout.db.migrate_countries
"""
from __future__ import annotations
from sponsorscout.core.location_country import country_from_location


def migrate_job_countries(conn) -> int:
    """
    Re-derive country from location string for every job in the DB.
    Returns number of rows updated.

    B17 fix: previous version was called from initialize() on every app
    start and would silently overwrite any country a user had manually
    corrected. Now we only update jobs whose current country is either
    empty or one of the legacy placeholder values ("Remote", ""), so
    manual fixes survive subsequent launches.
    """
    rows = conn.execute(
        "SELECT id, location, country FROM jobs"
    ).fetchall()

    # Country values that indicate the job needs (re)derivation. Anything
    # else (e.g. a user-corrected "United States" on a job the auto-deriver
    # had misclassified) is left alone.
    LEGACY_OR_EMPTY = {"", "remote"}

    updated = 0
    for row in rows:
        old_country = row["country"] or ""
        if old_country.lower() not in LEGACY_OR_EMPTY:
            continue
        location = row["location"] or ""
        new_country = country_from_location(location, fallback=old_country)
        if new_country and new_country != old_country:
            conn.execute(
                "UPDATE jobs SET country=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_country, row["id"])
            )
            updated += 1

    if updated:
        conn.commit()
    return updated


if __name__ == "__main__":
    from sponsorscout.db.database import get_connection, DB_PATH
    conn = get_connection(DB_PATH)
    n = migrate_job_countries(conn)
    conn.close()
    print(f"Updated {n} job country records.")
