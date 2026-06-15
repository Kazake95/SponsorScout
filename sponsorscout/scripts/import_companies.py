"""
Import companies from a CSV or plain URL list.

CSV format (full):
  name,country,ats_type,careers_url,ats_board_token
  Acme,Germany,greenhouse,https://boards.greenhouse.io/acme,acme

Plain URL list (one URL per line — ATS auto-detected):
  https://boards.greenhouse.io/stripe
  https://jobs.lever.co/vercel
  https://careers.booking.com

Usage:
  python3 -m sponsorscout.scripts.import_companies companies.csv
  python3 -m sponsorscout.scripts.import_companies urls.txt
"""
import csv
import sys
from pathlib import Path
from sponsorscout.db.database import initialize, get_connection, DB_PATH
from sponsorscout.core.persistence import save_company
from sponsorscout.core.discovery_engine import detect_ats, _extract_company_name


def _from_csv(path: Path, conn) -> int:
    count = 0
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Auto-detect ATS if not specified
            if not row.get("ats_type"):
                row["ats_type"] = detect_ats(row.get("careers_url", ""))
            if not row.get("name"):
                row["name"] = _extract_company_name(
                    row.get("careers_url", ""), row.get("ats_type", ""))
            save_company(conn, row)
            count += 1
    return count


def _from_urls(path: Path, conn) -> int:
    count = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        url = raw_line.strip()
        if not url or url.startswith("#"):
            continue
        ats  = detect_ats(url)
        name = _extract_company_name(url, ats) or url
        save_company(conn, {
            "name": name,
            "country": "",
            "ats_type": ats,
            "careers_url": url,
            "ats_board_token": "",
        })
        count += 1
    return count


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        raise SystemExit(1)

    initialize(DB_PATH)
    conn = get_connection(DB_PATH)

    if path.suffix.lower() == ".csv":
        n = _from_csv(path, conn)
    else:
        n = _from_urls(path, conn)

    conn.close()
    print(f"Imported {n} company/companies from {path.name}.")
    print("Run 'sponsorscout-scan --parallel' to fetch their jobs.")


if __name__ == "__main__":
    main()
