#!/usr/bin/env python3
"""
Diagnostic scan script: runs a full scan of all companies in the registry
and produces a detailed CSV report of results per company.

This helps identify which companies return jobs, which are blocked by
bot protection, which have dead career pages, etc.

Usage:
    python -m sponsorscout.scripts.diagnose_scan [--output report.csv] [--parallel]
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure the package root is on sys.path when run directly
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sponsorscout.core.http_client import http_session, is_bot_blocked
from sponsorscout.services.registry_loader import load_seed_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("diagnose_scan")


def check_job_urls_in_html(html: str) -> bool:
    """Check if HTML contains job-like URL patterns."""
    if not html:
        return False
    import re
    # Check for common job URL patterns
    patterns = [
        r"(/|=)(job|jobs|career|careers|position|positions|role|roles|opening|openings|vacanc)",
        r"[a-z0-9_-]+/\d{5,}",
        r"(boards\.greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com|myworkdayjobs\.com)",
    ]
    return any(re.search(p, html, re.I) for p in patterns)


def diagnose_company(company: dict) -> dict:
    """Run diagnostic checks on a single company.

    Returns a dict with diagnostic results.
    """
    name = company.get("name", "unknown")
    careers_url = company.get("careers_url", "").rstrip("/")
    expected_ats = company.get("ats_type", "unknown")

    result = {
        "company": name,
        "careers_url": careers_url,
        "expected_ats": expected_ats,
        "status_code": 0,
        "html_size": 0,
        "bot_blocked": False,
        "has_job_links_static": False,
        "has_ats_links": False,
        "result_category": "",
        "render_success": False,
        "render_has_jobs": False,
        "notes": "",
    }

    if not careers_url:
        result["result_category"] = "NO_URL"
        result["notes"] = "no_careers_url"
        return result

    # --- Phase 1: Static HTTP fetch ---
    try:
        with http_session() as session:
            resp = session.get(careers_url, timeout=20, allow_redirects=True)
            html = resp.text or ""
            result["status_code"] = resp.status_code
            result["html_size"] = len(html)
            result["bot_blocked"] = is_bot_blocked(html, resp.status_code)
            result["has_job_links_static"] = check_job_urls_in_html(html)

            # Check for ATS links
            import re
            ats_pattern = re.compile(
                r"(boards\.greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com|"
                r"apply\.workable\.com|myworkdayjobs\.com|jobs\.personio\.|teamtailor\.com|"
                r"smartrecruiters\.com|bamboohr\.com|recruitee\.com|jobvite\.com|icims\.com|"
                r"breezy\.hr|freshteam\.com|run\.homerun\.co|welcometothejungle\.com|manatal\.com)",
                re.I,
            )
            result["has_ats_links"] = bool(ats_pattern.search(html or ""))

            if result["bot_blocked"]:
                result["result_category"] = "BOT_BLOCKED"
                result["notes"] = f"Static fetch blocked (status={resp.status_code})"

    except Exception as exc:
        result["result_category"] = "ERROR"
        result["notes"] = str(exc)
        return result

    # --- Phase 2: Playwright rendering ---
    # Always try Playwright for companies where static HTML has no job URLs
    # or if the page looks like an SPA (large HTML, no jobs in static)
    try:
        from sponsorscout.services.browser_fetcher import fetch_rendered_html, _playwright_available

        playwright_avail = _playwright_available()
        result["notes"] = f"playwright={'yes' if playwright_avail else 'no'}"

        if playwright_avail:
            rendered = fetch_rendered_html(careers_url, wait_ms=4000, timeout=30, force_browser=True)
            if rendered and rendered.get("html"):
                rendered_html = rendered.get("html", "")
                result["render_success"] = True
                result["render_bot_blocked"] = rendered.get("bot_blocked", False)
                result["render_has_jobs"] = check_job_urls_in_html(rendered_html)

                # Try full job extraction on rendered HTML
                try:
                    from sponsorscout.core.portal_search import extract_jobs_from_html
                    portal_jobs = extract_jobs_from_html(careers_url, rendered_html, limit=5)
                    result["render_jobs_found"] = len(portal_jobs)
                except Exception:
                    result["render_jobs_found"] = -1
            else:
                err = rendered.get("error", "no_html") if rendered else "no_render"
                result["notes"] += f" | render_error={err}"
        else:
            result["notes"] += " | playwright_unavailable"

        # Final categorization
        if result["bot_blocked"]:
            result["result_category"] = "BOT_BLOCKED"
        elif result.get("render_jobs_found", 0) > 0:
            result["result_category"] = "JOBS_FOUND"
        elif result["has_job_links_static"]:
            result["result_category"] = "STATIC_JOBS"
        elif result["render_success"] and not result.get("render_bot_blocked"):
            result["result_category"] = "RENDERED_NO_JOBS"
        else:
            result["result_category"] = "STATIC_NO_JOBS"

    except Exception as exc:
        result["notes"] += f" | render_crash={exc}"


    return result


def main():
    parser = argparse.ArgumentParser(description="Diagnostic scan of all companies")
    parser.add_argument("--output", "-o", default="diagnostic_report.csv",
                        help="Output CSV path (default: diagnostic_report.csv)")
    parser.add_argument("--parallel", "-p", action="store_true",
                        help="Run scans in parallel (faster but more load)")
    args = parser.parse_args()

    print("=" * 70)
    print("  SponsorScout Diagnostic Scan")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Load all companies
    companies = load_seed_registry()
    print(f"\nLoaded {len(companies)} companies from registry\n")

    results = []
    total = len(companies)
    for i, company in enumerate(companies, 1):
        name = company.get("name", "?")
        print(f"[{i}/{total}] {name}...", end=" ", flush=True)

        result = diagnose_company(company)
        results.append(result)

        # Print quick summary with emoji
        cat = result["result_category"]
        if cat == "JOBS_FOUND":
            print(f"✅ {result.get('render_jobs_found', '?')} jobs")
        elif cat == "STATIC_JOBS":
            print(f"📄 static has job links")
        elif cat == "BOT_BLOCKED":
            print(f"🔒 blocked (status={result['status_code']})")
        elif cat == "RENDERED_NO_JOBS":
            print(f"⚡ rendered no jobs")
        elif cat == "STATIC_NO_JOBS":
            print(f"⚠️  static={result['html_size']}b, no jobs")
        elif cat == "NO_URL":
            print(f"⏭️  no URL")
        elif cat == "ERROR":
            print(f"❌ error: {result['notes'][:50]}")
        else:
            print(f"❓ {cat}")

        # Small delay between requests
        time.sleep(0.3)

    # Write detailed report
    fieldnames = [
        "company", "careers_url", "expected_ats", "result_category",
        "status_code", "html_size", "bot_blocked",
        "has_job_links_static", "has_ats_links",
        "render_success", "render_has_jobs", "render_jobs_found",
        "notes",
    ]
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    # Print summary
    total_companies = len(results)
    jobs_found = sum(1 for r in results if r["result_category"] == "JOBS_FOUND")
    static_jobs = sum(1 for r in results if r["result_category"] == "STATIC_JOBS")
    blocked = sum(1 for r in results if r["result_category"] == "BOT_BLOCKED")
    rendered_no_jobs = sum(1 for r in results if r["result_category"] == "RENDERED_NO_JOBS")
    static_no_jobs = sum(1 for r in results if r["result_category"] == "STATIC_NO_JOBS")
    errors = sum(1 for r in results if r["result_category"] == "ERROR")
    no_url = sum(1 for r in results if r["result_category"] == "NO_URL")

    print("\n" + "=" * 70)
    print("  DIAGNOSTIC SUMMARY")
    print("=" * 70)
    print(f"  Total companies:          {total_companies}")
    print(f"  ✅ Jobs found (render):    {jobs_found}")
    print(f"  📄 Job links (static):     {static_jobs}")
    print(f"  🔒 Bot-blocked:            {blocked}")
    print(f"  ⚡ Rendered, no jobs:      {rendered_no_jobs}")
    print(f"  ⚠️  Static page, no jobs:  {static_no_jobs}")
    print(f"  ❌ Errors:                 {errors}")
    print(f"  ⏭️  No URL:                 {no_url}")
    print(f"\n  Full report: {args.output}")
    print("=" * 70)


if __name__ == "__main__":
    main()