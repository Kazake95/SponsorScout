"""Loads the company registry from a CSV file in the data/ directory.

Two registries are shipped with the app:

  * sponsorscout/data/company_registry_seed.csv       — the original 111-company
    curated set, ATS-specific (Greenhouse, Lever, Workday, etc.). This is
    the default and loads automatically on first scan.

  * sponsorscout/data/company_registry_expanded.csv   — the additional ~85
    companies / agencies harvested from the data-base.xlsx. Most of these
    are scraped via the generic HTML fallback (ats_type=official_careers)
    plus the new Homerun / Freshteam / Breezy / WTTJ / Manatal connectors.
    Opt-in via the environment variable SPONSORSCOUT_LOAD_EXPANDED=1.
"""
import csv
import os
from pathlib import Path
from typing import List, Dict, Any


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _read_csv_skipping_comments(path: Path) -> List[Dict[str, Any]]:
    """Read a CSV file, ignoring any comment lines that start with '#'."""
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        # Filter out comment lines so the CSV reader can parse cleanly
        cleaned = (line for line in f if not line.lstrip().startswith("#"))
        reader = csv.DictReader(cleaned)
        for row in reader:
            if row.get("name"):
                rows.append(row)
    return rows


def load_seed_registry() -> List[Dict[str, Any]]:
    """Load the default curated company registry.

    Behaviour controlled by the SPONSORSCOUT_LOAD_EXPANDED env var:
      * unset / "0" / "false"  → only company_registry_seed.csv is loaded
      * "1" / "true"            → both seed AND expanded registries are loaded
                                 and merged (seed entries win on name conflicts)

    Returns a list of dicts with keys: name, country, ats_type, careers_url,
    ats_board_token, industry, sponsorship_history, english_friendly, remote_score.
    """
    data_dir = _data_dir()
    seed_rows = _read_csv_skipping_comments(data_dir / "company_registry_seed.csv")

    load_expanded = os.environ.get("SPONSORSCOUT_LOAD_EXPANDED", "").lower() in (
        "1", "true", "yes",
    )
    if not load_expanded:
        return seed_rows

    expanded_rows = _read_csv_skipping_comments(data_dir / "company_registry_expanded.csv")
    if not expanded_rows:
        return seed_rows

    # Seed wins on name collisions (seed entries have higher trust).
    seed_names = {r["name"].strip().lower() for r in seed_rows}
    merged = list(seed_rows) + [
        r for r in expanded_rows
        if r["name"].strip().lower() not in seed_names
    ]
    return merged
