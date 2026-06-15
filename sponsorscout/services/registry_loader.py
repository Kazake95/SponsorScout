"""Loads company registries from CSV files in the data/ directory.

SponsorScout merges all company registry CSVs shipped in `sponsorscout/data`.
It ignores non-registry CSVs such as remote portal catalogs.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Dict, Any, Iterable


COMPANY_REGISTRY_FIELDS = [
    "name",
    "country",
    "ats_type",
    "careers_url",
    "ats_board_token",
    "industry",
    "sponsorship_history",
    "english_friendly",
    "remote_score",
]

REMOTE_PORTAL_FIELDS = [
    "name",
    "url",
    "focus",
    "category",
]


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _clean_lines(path: Path) -> Iterable[str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        for line in f:
            if not line.lstrip().startswith("#"):
                yield line


def _parse_company_registry_row(row: list[str]) -> Dict[str, Any]:
    # Company registries have a fixed schema, but careers_url may contain
    # commas when query parameters are embedded directly in the CSV.
    if len(row) < len(COMPANY_REGISTRY_FIELDS):
        row = row + [""] * (len(COMPANY_REGISTRY_FIELDS) - len(row))

    if len(row) > len(COMPANY_REGISTRY_FIELDS):
        # Preserve the fixed suffix columns and fold any extra comma-split
        # fragments back into the careers URL column.
        prefix = row[:3]
        suffix_count = len(COMPANY_REGISTRY_FIELDS) - 4  # columns after careers_url
        suffix = row[-suffix_count:] if suffix_count else []
        careers_url_parts = row[3:-suffix_count] if suffix_count else row[3:]
        row = prefix + [",".join(careers_url_parts)] + suffix

    return {field: (row[idx] if idx < len(row) else "") for idx, field in enumerate(COMPANY_REGISTRY_FIELDS)}


def _parse_remote_portal_row(row: list[str]) -> Dict[str, Any]:
    # Focus text may contain commas; fold the middle fragments into one field.
    if len(row) < len(REMOTE_PORTAL_FIELDS):
        row = row + [""] * (len(REMOTE_PORTAL_FIELDS) - len(row))

    if len(row) > len(REMOTE_PORTAL_FIELDS):
        prefix = row[:2]
        category = row[-1]
        focus_parts = row[2:-1]
        row = prefix + [",".join(focus_parts), category]

    return {field: (row[idx] if idx < len(row) else "") for idx, field in enumerate(REMOTE_PORTAL_FIELDS)}


def _read_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    rows: List[Dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        cleaned = [line for line in f if not line.lstrip().startswith("#")]
    if not cleaned:
        return rows

    reader = csv.reader(cleaned)
    headers = next(reader, [])
    headers = [h.strip() for h in headers]

    for raw in reader:
        if not raw:
            continue

        lowered = {h.lower() for h in headers}
        if {"ats_type", "careers_url"} & lowered:
            row = _parse_company_registry_row(raw)
        elif {"url", "focus", "category"} <= lowered:
            row = _parse_remote_portal_row(raw)
        else:
            # Generic fallback: map as much as possible and keep extra fragments
            # in the last column.
            if len(raw) > len(headers) and headers:
                raw = raw[:len(headers)-1] + ["".join(raw[len(headers)-1:])]
            if len(raw) < len(headers):
                raw = raw + [""] * (len(headers) - len(raw))
            row = {headers[i]: raw[i] if i < len(raw) else "" for i in range(len(headers))}

        if row.get("name"):
            rows.append(row)

    return rows


def _registry_csv_files() -> List[Path]:
    """Return all company registry CSVs shipped with the app."""
    data_dir = _data_dir()
    files = sorted(data_dir.glob("*.csv"))
    # Deterministic preference: seed first, then expanded, then anything else.
    priority = {
        "company_registry_seed.csv": 0,
        "company_registry_expanded.csv": 1,
    }
    files.sort(key=lambda p: (priority.get(p.name, 2), p.name))
    return files


def _looks_like_company_registry(row: Dict[str, Any], source_name: str) -> bool:
    """Filter out non-company CSVs such as remote portal lists."""
    if not row.get("name"):
        return False
    category = (row.get("category") or "").strip().lower()
    if category in {"remote_portal", "job_board", "content"}:
        return False
    # Explicit company registry rows always include one of these fields.
    if row.get("careers_url") or row.get("ats_type") or row.get("country") or row.get("ats_board_token"):
        return True
    # File-name-based fallback for future registries.
    return "registry" in source_name.lower()


def load_seed_registry() -> List[Dict[str, Any]]:
    """Load and merge every company registry CSV under sponsorscout/data.

    Duplicate company names are de-duplicated by keeping the first occurrence
    (seed rows win over later registries).
    """
    merged: List[Dict[str, Any]] = []
    seen_names = set()

    for csv_path in _registry_csv_files():
        for row in _read_rows(csv_path):
            if not _looks_like_company_registry(row, csv_path.name):
                continue
            name = (row.get("name") or "").strip().lower()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            merged.append(row)

    return merged
