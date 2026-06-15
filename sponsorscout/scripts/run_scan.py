"""
CLI scan runner — supports sequential and parallel modes, with progress output.
Usage:
    python -m sponsorscout.scripts.run_scan            # sequential
    python -m sponsorscout.scripts.run_scan --parallel  # parallel (faster)
    python -m sponsorscout.scripts.run_scan --dedup     # run dedup after scan
"""
from __future__ import annotations

import argparse
import sys
from sponsorscout.db.database import initialize, get_connection, DB_PATH
from sponsorscout.services.registry_loader import load_seed_registry
from sponsorscout.core.scanner import scan_all
from sponsorscout.core.dedup import dedup_jobs_in_db, dedup_companies_in_db
from sponsorscout.core.discovery_engine import (
    SEARCH_ENGINE_ALIASES,
    SEARCH_ENGINES,
    discover_companies_from_search,
    auto_register_companies,
)


def main():
    parser = argparse.ArgumentParser(description="SponsorScout job scanner")
    parser.add_argument("--parallel", action="store_true", help="Scan companies in parallel")
    parser.add_argument("--dedup", action="store_true", help="Run dedup after scanning")
    parser.add_argument("--company", type=str, default=None, help="Only scan one company by name")
    parser.add_argument("--discover", type=str, default=None, help="Discover and register companies/portals for this role or keyword before scanning")
    parser.add_argument("--country", type=str, default="", help="Country filter for discovery, e.g. Germany")
    parser.add_argument("--domain", action="append", default=[], help="Company domain/careers URL to probe during discovery. Can be repeated")
    parser.add_argument("--sponsorship-only", action="store_true", help="During discovery, keep portals with sponsorship/relocation signals")
    parser.add_argument("--remote-filter", default="All", choices=["All", "Remote EU", "Remote EMEA", "Remote Global", "Remote Only", "Hybrid"], help="Remote filter for portal discovery")
    parser.add_argument(
        "--search-engine",
        default="eu",
        help=(
            "Search fallback provider: eu (default), all, or comma-separated engines. "
            f"Available: {', '.join(sorted(SEARCH_ENGINES | SEARCH_ENGINE_ALIASES))}"
        ),
    )
    args = parser.parse_args()

    initialize(DB_PATH)
    companies = load_seed_registry()

    if args.discover or args.domain:
        conn = get_connection(DB_PATH)
        candidates = discover_companies_from_search(
            args.discover or "",
            country=args.country,
            domains=args.domain,
            sponsorship_only=args.sponsorship_only,
            remote_filter=args.remote_filter,
            search_engine=args.search_engine,
            limit=50,
        )
        registered = auto_register_companies(conn, candidates, country=args.country)
        conn.close()
        print(f"Discovery: registered {len(registered)} companies/portals.")
        companies_by_name = {c.get("name", "").strip().lower(): c for c in companies}
        for company in registered:
            companies_by_name.setdefault(company.get("name", "").strip().lower(), company)
        companies = list(companies_by_name.values())

    if args.company:
        companies = [c for c in companies if args.company.lower() in c.get("name", "").lower()]
        if not companies:
            print(f"No company matching '{args.company}' found in registry.")
            sys.exit(1)

    print(f"Scanning {len(companies)} companies (parallel={args.parallel})…")
    results = scan_all(companies, db_path=DB_PATH, parallel=args.parallel)
    print(f"Scan complete. {len(results)} jobs processed.")

    if args.dedup:
        conn = get_connection(DB_PATH)
        job_dupes = dedup_jobs_in_db(conn)
        co_dupes = dedup_companies_in_db(conn)
        conn.close()
        print(f"Dedup: removed {job_dupes} duplicate jobs, {co_dupes} duplicate companies.")


if __name__ == "__main__":
    main()
