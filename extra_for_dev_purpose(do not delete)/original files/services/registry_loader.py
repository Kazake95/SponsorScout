"""Loads company registries from CSV files in the data/ directory.

SponsorScout merges the two curated company registries (ATS and Career)
shipped in `sponsorscout/data`. Remote-portal CSVs are ignored.
"""
from __future__ import annotations

import csv
import re
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


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _clean_lines(path: Path) -> Iterable[str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                yield line


def _derive_country_from_url(url: str) -> str:
    """Guess country from URL domain or TLD."""
    if not url:
        return ""
    url_lower = url.lower()

    domain_map = {
        "zalando": "Germany", "siemens": "Germany", "booking": "Netherlands",
        "asml": "Netherlands", "ing": "Netherlands", "abnamro": "Netherlands",
        "kpn": "Netherlands", "mollie": "Netherlands", "bynder": "Netherlands",
        "bunq": "Netherlands", "optiver": "Netherlands", "adyen": "Netherlands",
        "picnic": "Netherlands", "bol": "Netherlands", "wolt": "Finland",
        "bolt": "Estonia", "pipedrive": "Estonia", "veriff": "Estonia",
        "wise": "United Kingdom", "monzo": "United Kingdom",
        "deliveroo": "United Kingdom", "revolut": "United Kingdom",
        "skyscanner": "United Kingdom", "ocado": "United Kingdom",
        "n26": "Germany", "personio": "Germany", "hellofresh": "Germany",
        "contentful": "Germany", "choco": "Germany", "sumup": "Germany",
        "raisin": "Germany", "doist": "Portugal", "factorial": "Spain",
        "glovo": "Spain", "spotify": "Sweden", "klarna": "Sweden",
        "king": "Sweden", "detectify": "Sweden", "planhat": "Sweden",
        "teamtailor": "Sweden", "voi": "Sweden", "quinyx": "Sweden",
        "airbyte": "United States", "databricks": "United States",
        "elastic": "United States", "retool": "United States",
        "stripe": "United States", "notion": "United States",
        "figma": "United States", "twilio": "United States",
        "netlify": "United States", "mixpanel": "United States",
        "vercel": "United States", "sentry": "United States",
        "mapbox": "United States", "dbt": "United States",
        "mentimeter": "Sweden", "luno": "United Kingdom",
        "typeform": "Spain", "homerun": "Belgium",
        "freshteam": "United States", "breezy": "United States",
        "welcometothejungle": "France", "manatal": "Thailand",
        "icims": "United States", "jobvite": "United States",
        "flix": "Germany", "forto": "Germany", "pitch": "Germany",
        "sap": "Germany", "audible": "United Kingdom", "babbel": "Germany",
        "cal": "United States", "celonis": "Germany", "moss": "Germany",
        "ohpen": "Netherlands", "bonial": "Germany", "deliveryhero": "Germany",
        "nexthink": "Switzerland", "avomind": "United Kingdom",
        "autodesk": "United States", "zendesk": "United States",
        "nxp": "Netherlands", "philips": "Netherlands",
        "simcorp": "Denmark", "prysmian": "Italy", "leonardo": "Italy",
        "caeli": "Germany", "clearvue": "Germany", "kaufland": "Germany",
        "aboutyou": "Germany", "buena": "Germany", "reisetopia": "Germany",
        "adjoe": "Germany", "konux": "Germany", "limehome": "Germany",
        "highsnobiety": "Germany", "navvis": "Germany", "anymind": "Japan",
        "appodeal": "United States", "doctolib": "France",
        "msd": "Netherlands", "exact": "Netherlands",
        "scorewarrior": "United Kingdom", "metaquotes": "Cyprus",
        "exness": "Cyprus", "hays": "Germany", "robertwalters": "Germany",
        "michaelpage": "Germany", "harnham": "United Kingdom",
        "talentor": "Germany", "kelly": "Germany", "devsdata": "Poland",
        "undutchables": "Netherlands", "huxley": "Netherlands",
        "morganmckinley": "Ireland", "sigmar": "Ireland",
        "reperio": "Ireland", "understanding": "United Kingdom",
        "lafosse": "United Kingdom", "nigelfrank": "United Kingdom",
        "esselunga": "Italy", "coop": "Italy", "conad": "Italy",
        "lidl": "Italy", "eurospin": "Italy", "pam": "Italy",
        "posteitaliane": "Italy", "fscareers": "Italy", "barilla": "Italy",
        "ferrero": "Italy", "lavazza": "Italy", "eni": "Italy",
        "enel": "Italy", "stellantis": "Italy", "intesasanpaolo": "Italy",
        "unicredit": "Italy", "tim": "Italy", "generali": "Italy",
        "luxottica": "Italy", "prada": "Italy", "angelini": "Italy",
        "snam": "Italy", "ikea": "Italy", "mcdonalds": "Italy",
        "amazon": "Italy", "decathlon": "Italy",
    }

    for domain, country in domain_map.items():
        if domain in url_lower:
            return country

    tld_map = {
        ".de": "Germany", ".fr": "France", ".nl": "Netherlands",
        ".it": "Italy", ".es": "Spain", ".pt": "Portugal", ".pl": "Poland",
        ".ie": "Ireland", ".dk": "Denmark", ".se": "Sweden", ".no": "Norway",
        ".fi": "Finland", ".at": "Austria", ".be": "Belgium",
        ".ch": "Switzerland", ".cz": "Czech Republic", ".hu": "Hungary",
        ".ro": "Romania", ".hr": "Croatia", ".si": "Slovenia",
        ".sk": "Slovakia", ".lt": "Lithuania", ".lv": "Latvia",
        ".ee": "Estonia", ".lu": "Luxembourg", ".mt": "Malta",
        ".cy": "Cyprus", ".gr": "Greece", ".co.uk": "United Kingdom",
    }

    for tld, country in tld_map.items():
        if tld in url_lower:
            return country

    return ""


def _extract_board_token_from_url(url: str, ats_type: str) -> str:
    """Derive ATS board token from URL for known ATS types."""
    if not url or ats_type in ("official_careers", "unknown", ""):
        return ""

    url_lower = url.lower()

    patterns = {
        "greenhouse": r"greenhouse\.io/([^/?#]+)",
        "lever": r"lever\.co/([^/?#]+)",
        "ashby": r"ashbyhq\.com/([^/?#]+)",
        "workday": r"([^/]+)\.wd\d+\.myworkdayjobs\.com",
        "workable": r"workable\.com/([^/?#]+)",
        "personio": r"([^/]+)\.jobs\.personio",
        "bamboohr": r"([^/]+)\.bamboohr\.com",
        "recruitee": r"([^/]+)\.recruitee\.com",
        "smartrecruiters": r"smartrecruiters\.com/([^/?#]+)",
        "teamtailor": r"([^/]+)\.teamtailor\.com",
    }

    pat = patterns.get(ats_type)
    if pat:
        m = re.search(pat, url_lower)
        return m.group(1) if m else ""

    return ""


def _parse_company_registry_row(row: list[str], headers: list[str]) -> Dict[str, Any]:
    """Parse a company registry row, handling both old 9-column and new 7-column formats."""
    result = {field: "" for field in COMPANY_REGISTRY_FIELDS}

    header_set = {h.lower().strip() for h in headers}
    is_new_format = "country" not in header_set and "ats_type" in header_set

    if is_new_format:
        # New format: name, ats_type, careers_url, [ignored metadata...]
        # Only use first 3 columns; ignore everything after
        if len(row) >= 3:
            result["name"] = row[0].strip()
            result["ats_type"] = row[1].strip()
            result["careers_url"] = row[2].strip()
        elif len(row) >= 2:
            result["name"] = row[0].strip()
            result["ats_type"] = row[1].strip()
        elif len(row) >= 1:
            result["name"] = row[0].strip()
    else:
        # Old format: name, country, ats_type, careers_url, ats_board_token, ...
        for idx, field in enumerate(COMPANY_REGISTRY_FIELDS):
            if idx < len(row):
                result[field] = row[idx].strip()

    # Auto-derive missing fields
    if not result["country"]:
        result["country"] = _derive_country_from_url(result["careers_url"])
    if not result["ats_board_token"] and result["ats_type"] not in ("official_careers", "unknown", ""):
        result["ats_board_token"] = _extract_board_token_from_url(result["careers_url"], result["ats_type"])

    return result


def _parse_remote_portal_row(row: list[str]) -> Dict[str, Any]:
    if len(row) < 4:
        row = row + [""] * (4 - len(row))
    return {
        "name": row[0].strip(),
        "url": row[1].strip(),
        "focus": row[2].strip(),
        "category": row[3].strip(),
    }


def _read_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    rows: List[Dict[str, Any]] = []

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        headers = [h.strip() for h in headers]

        if not headers:
            return rows

        for raw in reader:
            if not raw or not any(field.strip() for field in raw):
                continue

            first_item = raw[0].strip()
            if first_item.startswith("#") or not first_item:
                continue

            header_set = {h.lower() for h in headers}

            if {"ats_type", "careers_url"} & header_set:
                row = _parse_company_registry_row(raw, headers)
            elif {"url", "focus", "category"} <= header_set:
                row = _parse_remote_portal_row(raw)
            else:
                # Generic fallback
                row = {h: raw[i].strip() if i < len(raw) else "" for i, h in enumerate(headers)}

            name = (row.get("name") or "").strip()
            if name and not name.startswith("#"):
                rows.append(row)

    return rows


def _registry_csv_files() -> List[Path]:
    """Return the targeted company registry CSVs shipped with the app."""
    data_dir = _data_dir()
    files = []

    # User's updated CSVs (new source of truth)
    for filename in ("company_ATS_seed.csv", "company_Career_seed.csv"):
        p = data_dir / filename
        if p.exists():
            files.append(p)

    # Legacy files (backwards compatibility)
    for filename in ("company_registry_seed.csv", "company_registry_expanded.csv"):
        p = data_dir / filename
        if p.exists():
            files.append(p)

    # NOTE: remote_seed.csv is intentionally excluded — it contains job
    # aggregators, not companies, and should not be scanned.

    return files


def _looks_like_company_registry(row: Dict[str, Any], source_name: str) -> bool:
    """Filter out non-company CSVs such as remote portal lists."""
    if not row.get("name"):
        return False

    category = (row.get("category") or "").strip().lower()
    if category in {"remote_portal", "job_board", "content"}:
        return False

    # Must have a careers_url to be scannable
    if row.get("careers_url"):
        return True

    return "registry" in source_name.lower() or "ats" in source_name.lower() or "career" in source_name.lower()


def load_seed_registry() -> List[Dict[str, Any]]:
    """Load and merge company registry CSVs automatically.

    ATS seed is loaded first intentionally — it takes precedence over
    Career seed for duplicate names.
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
