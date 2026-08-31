"""Seed CSV management.

Canonical sources of truth are the bundled CSVs shipped in
``sponsorscout/data`` (synced from the project-root ``company_ATS_seed.csv`` /
``company_Career_seed.csv``).  On first run the app copies them into the
per-user data directory (``~/.sponsorscout/seeds``) and ALL edits (in-app Data
Management tab, or manual CSV editing by the end-user) happen on those mutable
copies.  This keeps a packaged build read-only and lets users add companies.

Both scanners read the v6-style simple schema:
    name, ats_type, careers_url, industry, sponsorship_history,
    english_friendly, remote_score
and the career scanner additionally understands the v7 optional columns
    seed_name, canonical_name, source_type, target_country, scope_policy,
    provider, board_slug, notes
which are preserved when present.
"""
from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import List, Tuple

from sponsorscout.paths import SEEDS_DIR, ensure_user_data_dir

BASE_COLUMNS = [
    "name", "ats_type", "careers_url", "industry",
    "sponsorship_history", "english_friendly", "remote_score",
]

EXTRA_COLUMNS = [
    "seed_name", "canonical_name", "source_type", "target_country",
    "scope_policy", "provider", "board_slug", "notes",
]

SUPPORTED_ATS_TYPES = (
    "official_careers", "ashby", "greenhouse", "lever", "smartrecruiters",
    "personio", "recruitee", "workable", "workday",
)

SCOPE_POLICIES = ("global", "seed_url", "job_location")
SOURCE_TYPES = ("direct_employer", "recruiter")


def _bundled_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "seeds"


def bundled_ats_path() -> Path:
    return _bundled_dir() / "company_ATS_seed.csv"


def bundled_career_path() -> Path:
    return _bundled_dir() / "company_Career_seed.csv"


def user_ats_path() -> Path:
    return SEEDS_DIR / "company_ATS_seed.csv"


def user_career_path() -> Path:
    return SEEDS_DIR / "company_Career_seed.csv"


def ensure_user_seeds(force: bool = False) -> Tuple[Path, Path]:
    """Copy bundled seeds to the user data dir on first run.

    Returns the paths of the mutable user copies.  When ``force`` is set the
    user copies are replaced with the bundled defaults (used by the
    "Reset to bundled defaults" action).
    """
    ensure_user_data_dir()
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)
    for bundled, user in (
        (bundled_ats_path(), user_ats_path()),
        (bundled_career_path(), user_career_path()),
    ):
        if force or not user.exists():
            shutil.copyfile(bundled, user)
    return user_ats_path(), user_career_path()


def read_seed_rows(path: Path) -> dict:
    """Read a seed CSV into ``{"columns": [...], "rows": [dict, ...]}``.

    Row dicts contain only the columns actually present in the file (plus
    empty-string padding for missing BASE_COLUMNS).  No validation is
    performed here - callers use :func:`validate_row`.
    """
    if not path.exists():
        return {"columns": list(BASE_COLUMNS), "rows": []}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = [(h or "").strip() for h in (reader.fieldnames or [])]
        rows = []
        for raw in reader:
            row = {h: (raw.get(h) or "").strip() for h in headers}
            for col in BASE_COLUMNS:
                row.setdefault(col, "")
            rows.append(row)
        return {"columns": headers, "rows": rows}


def validate_row(row: dict) -> List[str]:
    """Return validation problems for one seed row (empty list = valid).

    Mirrors the rules enforced by both scanner scripts so the UI rejects a
    bad row before the scanners do.
    """
    errors: List[str] = []
    name = (row.get("name") or "").strip()
    ats_type = (row.get("ats_type") or "").strip().lower()
    url = (row.get("careers_url") or "").strip()
    scope = (row.get("scope_policy") or "").strip().lower()
    source_type = (row.get("source_type") or "").strip().lower()

    if not name:
        errors.append("name is required")
    if not ats_type:
        errors.append("ats_type is required")
    elif ats_type not in SUPPORTED_ATS_TYPES:
        errors.append(f"ats_type must be one of: {', '.join(SUPPORTED_ATS_TYPES)}")
    if not url:
        errors.append("careers_url is required")
    elif url and not url.startswith(("http://", "https://")):
        errors.append("careers_url must start with http:// or https://")
    if scope and scope not in SCOPE_POLICIES:
        errors.append(f"scope_policy must be one of: {', '.join(SCOPE_POLICIES)}")
    if source_type and source_type not in SOURCE_TYPES:
        errors.append(f"source_type must be one of: {', '.join(SOURCE_TYPES)}")
    for col in ("sponsorship_history", "english_friendly", "remote_score"):
        raw = (row.get(col) or "").strip()
        if raw:
            try:
                value = int(raw)
                if not 0 <= value <= 100:
                    errors.append(f"{col} must be an integer between 0 and 100")
            except ValueError:
                errors.append(f"{col} must be an integer between 0 and 100")
    return errors
def validate_file(path: Path) -> Tuple[bool, List[str]]:
    """Validate every row of a seed file.

    Returns (ok, problems) where problems is a list of ``"line N: msg"``
    strings.  Duplicate (name + careers_url) pairs are also flagged.
    """
    data = read_seed_rows(path)
    problems: List[str] = []
    seen: set = set()
    for idx, row in enumerate(data["rows"], start=2):
        for msg in validate_row(row):
            problems.append(f"line {idx}: {msg}")
        key = ((row.get("name") or "").casefold(),
               (row.get("careers_url") or "").casefold())
        if key in seen:
            problems.append(f"line {idx}: duplicate (name, careers_url)")
        seen.add(key)
    return (not problems, problems)


def write_seed_rows(path: Path, columns: List[str], rows: List[dict]) -> int:
    """Write seed CSV.  Returns number of rows written."""
    cols = list(columns) if columns else list(BASE_COLUMNS)
    # Ensure all required columns exist in the header even if the input file
    # lacked them (scanners expect name/ats_type/careers_url).
    for col in BASE_COLUMNS:
        if col not in cols:
            cols.append(col)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in cols})
    return len(rows)


def auto_detect_ats_type(url: str) -> str:
    """Best-effort ATS type detection from a careers URL.

    Uses the ATS hostname/path fingerprinting rules from
    ``core/ats_detection``.  Falls back to ``official_careers`` when no known
    signature matches (conservative: the career crawler can still scan it).
    """
    from sponsorscout.core.ats_detection import detect_ats_from_links

    try:
        detected, _token = detect_ats_from_links([url])
        return detected or "official_careers"
    except Exception:
        return "official_careers"