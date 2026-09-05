"""Live verification of _LiveIngester: rows appended to a scanner CSV
mid-scan must become queryable in the DB before the scan finishes."""
import csv, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, "/media/My_Files/My_codes/SponsorScout")

from sponsorscout.scanning import pipeline

COLUMNS = ["Canonical Job ID", "Job URL", "Job Title", "Hiring Company",
           "Company Name", "Seed Name", "Job Location", "Target Country",
           "Visa Sponsorship", "Relocation Support", "EU Blue Card",
           "Support Confidence", "Sponsorship History Score",
           "Job Type", "Raw Location", "Industry Type", "Provider"]

def row(i):
    return {"Canonical Job ID": f"ID{i}", "Job URL": f"https://x.example/job/{i}",
            "Job Title": f"Engineer {i}", "Hiring Company": "Acme",
            "Company Name": "Acme", "Seed Name": "acme",
            "Job Location": "Berlin, Germany", "Target Country": "Germany",
            "Visa Sponsorship": "Y", "Relocation Support": "Y",
            "EU Blue Card": "Y", "Support Confidence": "0.8",
            "Sponsorship History Score": "50", "Job Type": "Full-time",
            "Raw Location": "Berlin", "Industry Type": "Software",
            "Provider": "greenhouse"}

tmp = Path(tempfile.mkdtemp())
db_path = str(tmp / "t.db")
csv_path = tmp / "run_ats_jobs.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    csv.DictWriter(f, fieldnames=COLUMNS).writeheader()

from sponsorscout.db import database as db
db.initialize(db_path)

seen = set()
live = pipeline._LiveIngester(db_path, "R1", [(csv_path, "direct")], seen,
                              interval=0.5)
live.start()

# company 1 finishes -> appends 3 rows
with open(csv_path, "a", newline="", encoding="utf-8") as f:
    csv.DictWriter(f, fieldnames=COLUMNS).writerows([row(i) for i in range(3)])
time.sleep(1.5)
s = db.get_dashboard_stats(db_path)
print("after 3 rows:", s)
assert s["verified_jobs"] == 3, "live ingest failed for batch 1"

# company 2 finishes -> appends 2 more (one duplicate canonical id)
with open(csv_path, "a", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS)
    w.writerow(row(3)); w.writerow(row(0))  # row 0 = dup canonical id
time.sleep(1.5)
s = db.get_dashboard_stats(db_path)
print("after 2 more rows (1 dup):", s)
assert s["verified_jobs"] == 4, "unexpected count"

# stop, then run final bulk ingest as run_scan does
live.stop(); live.join(timeout=5)
ing, dups = pipeline._ingest_output_csv(db_path, csv_path, "R1", "direct", set())
print("final pass ingested:", ing, "dups:", dups)
assert (ing, dups) == (4, 1), "final pass counts differ from bulk-only behaviour"

s = db.get_dashboard_stats(db_path)
print("final stats:", s)
assert s["verified_jobs"] == 4 and s["sponsored_jobs"] == 4
print("LIVE_INGESTER_OK")
