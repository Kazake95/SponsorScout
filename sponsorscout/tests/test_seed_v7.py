"""Seed validation tests (v7 career seed + ATS seed).

Mirrors the career scanner's seed-reader validation so seed regressions
(wrong-name rows like the Deliveroo/Detectify mix-up, bad URLs, invalid
scope policies, duplicate targets) fail here instead of mid-scan.

Run:  pytest tests/test_seed_v7.py
"""
import csv
from pathlib import Path

import pytest

CANDIDATE_DIRS = [
    Path(__file__).resolve().parent.parent,          # repo root checkout
    Path(__file__).resolve().parent.parent / "sponsorscout" / "data" / "seeds",
    Path.cwd(),
]


def _find_seed(filename: str) -> Path:
    for d in CANDIDATE_DIRS:
        p = d / filename
        if p.exists():
            return p
    pytest.skip(f"{filename} not found next to repo root or in sponsorscout/data/seeds")


def _load(filename: str):
    with open(_find_seed(filename), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_career_seed_loads_and_validates():
    rows = _load("company_Career_seed.csv")
    assert len(rows) >= 130, f"unexpected row count: {len(rows)}"
    seen = set()
    for n, r in enumerate(rows, 2):
        name = (r.get("name") or r.get("seed_name") or "").strip()
        url = (r.get("careers_url") or "").strip()
        assert name, f"line {n}: missing name"
        assert url.startswith(("http://", "https://")) and "..." not in url, \
            f"line {n} {name}: bad URL {url!r}"
        st = (r.get("source_type") or "direct_employer").strip().lower()
        assert st in ("direct_employer", "recruiter"), f"line {n} {name}: bad source_type"
        sp = (r.get("scope_policy") or "global").strip().lower()
        assert sp in ("global", "seed_url", "job_location"), f"line {n} {name}: bad scope"
        for col in ("sponsorship_history", "english_friendly", "remote_score"):
            raw = (r.get(col) or "").strip()
            if raw:
                assert raw.isdigit() and 0 <= int(raw) <= 100, \
                    f"line {n} {name}: bad {col}={raw!r}"
        key = (name.casefold(), (r.get("target_country") or "Global").casefold(),
               url.casefold())
        assert key not in seen, f"line {n} {name}: duplicate target"
        seen.add(key)


def test_career_seed_no_misnamed_rows():
    """Row names must match their URL host (Deliveroo-vs-Detectify guard)."""
    rows = _load("company_Career_seed.csv")
    for r in rows:
        host = r["careers_url"].lower()
        first_token = r["name"].strip().lower().split()[0]
        generic_hosts = ("greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com",
                         "workable.com", "personio.", "smartrecruiters", "recruitee.com",
                         "amazon.jobs", "ikea.com", "timretailrecruiting", "gruppopam.it",
                         "gruppo", "lavoro", "minorhotels", "coopalleanza", "talent.com",
                         "tellento", "successfactors", "phenompeople", "eightfold",
                         "oraclecloud.com", "myworkdaysite", "wd1.", "wd3.", "wd5.")
        if any(h in host for h in generic_hosts):
            continue
        assert first_token[:4] in host or host.split("/")[2][:4] in first_token, \
            f"suspicious: name={r['name']!r} url={r['careers_url']!r}"


def test_career_seed_v7_providers():
    """API-backed rows must name a supported provider + slug."""
    rows = _load("company_Career_seed.csv")
    supported = {"greenhouse", "ashby", "lever", "personio", "recruitee", "workable",
                 "auto", "", "oracle", "deel", "custom", "teamtailor"}
    by_name = {r["name"]: r for r in rows}
    assert by_name["Pitch"]["provider"] == "workable"
    assert by_name["Pitch"]["board_slug"] == "pitch-software"
    assert by_name["Spendesk"]["board_slug"] == "spendesk"
    assert by_name["Ikea Italia"]["scope_policy"] == "job_location"
    for r in rows:
        assert (r.get("provider") or "") in supported, f"{r['name']}: bad provider"


def test_ats_seed_loads():
    rows = _load("company_ATS_seed.csv")
    assert len(rows) >= 40, f"unexpected row count: {len(rows)}"
    for r in rows:
        assert r["name"].strip()
        assert r["careers_url"].strip().startswith(("http://", "https://"))
