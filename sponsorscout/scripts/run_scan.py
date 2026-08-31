"""CLI scan runner (PySide6 restart).

Usage:
    python -m sponsorscout.scripts.run_scan              # quick (API-first)
    python -m sponsorscout.scripts.run_scan --full        # full browser crawl
    python -m sponsorscout.scripts.run_scan --dedup       # run dedup after scanning
    python -m sponsorscout.scripts.run_scan --company X   # scan a single company

Wraps :func:`sponsorscout.scanning.pipeline.run_scan`, which runs the ATS
phase then the career phase and ingests the results into the database.
"""
from __future__ import annotations

import argparse
import sys

from sponsorscout.db.database import DB_PATH, get_connection, initialize
from sponsorscout.core.dedup import dedup_companies_in_db, dedup_jobs_in_db
from sponsorscout.scanning import pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="SponsorScout job scanner")
    parser.add_argument("--full", action="store_true",
                        help="Full browser crawl (slow) instead of quick API-first")
    parser.add_argument("--dedup", action="store_true",
                        help="Run dedup after scanning")
    parser.add_argument("--company", type=str, default=None,
                        help="Only scan one company by name")
    args = parser.parse_args()

    initialize(DB_PATH)
    method = "full" if args.full else "quick"

    if args.company:
        from sponsorscout.application import seed_manager
        matches = [r for r in seed_manager.load_seed_rows(
            seed_manager.user_ats_path())["rows"]
                   if args.company.lower() in (r.get("name") or "").lower()]
        matches += [r for r in seed_manager.load_seed_rows(
            seed_manager.user_career_path())["rows"]
                    if args.company.lower() in (r.get("name") or "").lower()]
        if not matches:
            print(f"No company matching '{args.company}' found in seeds.")
            sys.exit(1)
        print(f"Found {len(matches)} matching company/companies.")

    print(f"Scanning (method={method})…")
    summary = pipeline.run_scan(method=method, db_path=DB_PATH,
                                progress=lambda msg: print(msg, flush=True))
    status = summary.get("status", "error")
    print(f"Scan {status}: ingested={summary.get('ingested', 0)}, "
          f"duplicates={summary.get('duplicates', 0)}, "
          f"quarantined={summary.get('quarantined', 0)}")

    if args.dedup:
        conn = get_connection(DB_PATH)
        try:
            job_dupes = dedup_jobs_in_db(conn)
            co_dupes = dedup_companies_in_db(conn)
        finally:
            conn.close()
        print(f"Dedup: removed {job_dupes} duplicate jobs, "
              f"{co_dupes} duplicate companies.")


if __name__ == "__main__":
    main()
