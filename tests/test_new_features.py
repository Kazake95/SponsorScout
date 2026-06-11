"""Tests for features added in v0.4: remote classification, EU Blue Card,
sponsorship detection, dedup, normalizer, connectors, discovery engine."""
import pytest
import sqlite3
from pathlib import Path

import sponsorscout.services.ai_rating as ai_rating


# ── Sponsorship detection ──────────────────────────────────────────────────

from sponsorscout.core.sponsorship import score, detect_sponsorship_keywords, classify_remote

def test_score_positive_strong():
    assert score("We provide visa sponsorship for this role") >= 45

def test_score_eu_blue_card():
    assert score("EU Blue Card supported for all hires") >= 45

def test_score_negative_kills():
    assert score("No visa sponsorship. Must have right to work.") == 0

def test_score_relocation_moderate():
    s = score("Relocation package available")
    assert 20 < s < 60  # moderate signal only

def test_classify_remote_eu():
    assert classify_remote("This is a Remote EU position") == "remote_eu"

def test_classify_remote_global():
    assert classify_remote("Work from anywhere globally, fully remote") == "remote_global"

def test_classify_hybrid():
    assert classify_remote("Hybrid work model, 2 days per week in office") == "hybrid"

def test_classify_onsite():
    assert classify_remote("Based in Berlin, Germany") == "onsite"

def test_detect_keywords_full():
    d = detect_sponsorship_keywords("visa sponsorship. EU Blue Card. Relocation package for international candidates.")
    assert d["visa_sponsorship"]
    assert d["eu_blue_card"]
    assert d["relocation"]
    assert d["international"]

def test_detect_keywords_negative():
    d = detect_sponsorship_keywords("No sponsorship available. Local candidates only.")
    assert d["negative"]


# ── Normalizer ────────────────────────────────────────────────────────────

from sponsorscout.core.normalizer import normalize_country, normalize_title, normalize_location, normalize_job

def test_normalize_country_uk():
    assert normalize_country("uk") == "United Kingdom"
    assert normalize_country("U.K.") == "United Kingdom"
    assert normalize_country("gb") == "United Kingdom"

def test_normalize_country_germany():
    assert normalize_country("de") == "Germany"
    assert normalize_country("Deutschland") == "Germany"

def test_normalize_title_strips_gender():
    assert normalize_title("Engineer (m/f/d)") == "Engineer"
    assert normalize_title("Developer [M/W/D]") == "Developer"
    assert normalize_title("Manager (F/M/X)") == "Manager"

def test_normalize_title_clean():
    assert normalize_title("Data Scientist") == "Data Scientist"

def test_normalize_location_remote():
    loc = normalize_location("Remote – Europe")
    assert "Remote" in loc

def test_normalize_job_dict():
    raw = {"title": "Eng (m/f/d)", "company": "Acme", "country": "de",
           "location": "Berlin", "url": "https://example.com/job/1",
           "description": "test", "ats_source": "greenhouse"}
    result = normalize_job(raw, "verified", "greenhouse")
    assert result["title"] == "Eng"
    assert result["country"] == "Germany"


def test_normalize_job_requires_company():
    raw = {"title": "Data Analyst", "company": "", "country": "de",
           "location": "Berlin", "url": "https://example.com/job/1",
           "description": "test", "ats_source": "greenhouse"}
    with pytest.raises(ValueError, match="company"):
        normalize_job(raw, "verified", "greenhouse")


def test_rate_job_parses_markdown_json(monkeypatch):
    monkeypatch.setattr(ai_rating, "_call_ai", lambda *args, **kwargs: 
        "```json\n{\"rating\": 8, \"verdict\": \"Good fit\", \"pros\": [\"Visa support\"], \"cons\": [\"Some travel required\"]}\n```"
    )
    result = ai_rating.rate_job(
        title="Software Engineer",
        company="Acme",
        country="Germany",
        description="Great role",
        sponsorship_score=80,
        remote_type="remote_eu",
        eu_blue_card=True,
        has_relocation=False,
        api_key="test-key",
    )
    assert result.get("error") is None
    assert result["rating"] == 8
    assert result["verdict"] == "Good fit"
    assert result["pros"] == ["Visa support"]


def test_rate_job_parses_single_quote_json(monkeypatch):
    monkeypatch.setattr(ai_rating, "_call_ai", lambda *args, **kwargs: 
        "```json\n{'rating': 7, 'verdict': 'Strong fit', 'pros': ['Visa support'], 'cons': ['Some travel required']}\n```"
    )
    result = ai_rating.rate_job(
        title="Software Engineer",
        company="Acme",
        country="Germany",
        description="Great role",
        sponsorship_score=80,
        remote_type="remote_eu",
        eu_blue_card=True,
        has_relocation=False,
        api_key="test-key",
    )
    assert result.get("error") is None
    assert result["rating"] == 7
    assert result["verdict"] == "Strong fit"
    assert result["pros"] == ["Visa support"]


def test_openai_compatible_base_url_does_not_duplicate_v1():
    assert ai_rating._chat_completions_url("https://integrate.api.nvidia.com/v1") == (
        "https://integrate.api.nvidia.com/v1/chat/completions"
    )
    assert ai_rating._chat_completions_url("https://api.groq.com/openai/v1") == (
        "https://api.groq.com/openai/v1/chat/completions"
    )
    assert ai_rating._chat_completions_url("https://api.openai.com") == (
        "https://api.openai.com/v1/chat/completions"
    )
    assert ai_rating._chat_completions_url(
        "https://example.com/v1/chat/completions",
        exact=True,
    ) == "https://example.com/v1/chat/completions"


def test_nvidia_provider_is_supported(monkeypatch, tmp_path):
    provider_file = tmp_path / "provider.txt"
    monkeypatch.setattr(ai_rating, "PROVIDER_PATH", provider_file)
    monkeypatch.delenv("SPONSORSCOUT_AI_PROVIDER", raising=False)
    ai_rating.save_provider("nvidia")
    assert ai_rating.load_provider() == "nvidia"
    assert ai_rating.DEFAULT_BASE_URLS["nvidia"].endswith("/v1")
    assert ai_rating.SUGGESTED_MODELS_BY_PROVIDER["nvidia"]


def test_ai_404_error_mentions_provider_model_mismatch():
    msg = ai_rating._format_ai_http_error(
        404,
        "google/gemma-4-31b-it",
        "nvidia",
        "https://integrate.api.nvidia.com/v1/chat/completions",
        "model not found",
    )
    assert "provider 'nvidia'" in msg
    assert "model ID is not available" in msg


def test_normalize_job_uses_fallback_company():
    raw = {"title": "Data Analyst", "company": "", "country": "de",
           "location": "Berlin", "url": "https://example.com/job/1",
           "description": "test", "ats_source": "greenhouse"}
    result = normalize_job(raw, "verified", "greenhouse", fallback_company="Acme")
    assert result["company"] == "Acme"


# ── Dedup ──────────────────────────────────────────────────────────────────

from sponsorscout.core.dedup import job_fingerprint, dedup_jobs, dedup_jobs_in_db, dedup_companies_in_db

def test_fingerprint_consistent():
    fp1 = job_fingerprint("Engineer", "Acme", "Berlin", "https://example.com/1")
    fp2 = job_fingerprint("Engineer", "Acme", "Berlin", "https://example.com/1")
    assert fp1 == fp2

def test_fingerprint_case_insensitive():
    fp1 = job_fingerprint("engineer", "acme", "berlin", "https://example.com/1")
    fp2 = job_fingerprint("ENGINEER", "ACME", "BERLIN", "https://example.com/1")
    assert fp1 == fp2

def test_dedup_jobs_removes_exact_duplicates():
    jobs = [
        {"title": "Eng", "company": "Acme", "location": "Berlin", "url": "https://x.com/1"},
        {"title": "Eng", "company": "Acme", "location": "Berlin", "url": "https://x.com/1"},
    ]
    result = dedup_jobs(jobs)
    assert len(result) == 1

def test_dedup_jobs_keeps_different():
    jobs = [
        {"title": "Eng", "company": "Acme", "location": "Berlin", "url": "https://x.com/1"},
        {"title": "PM", "company": "Acme", "location": "Berlin", "url": "https://x.com/2"},
    ]
    result = dedup_jobs(jobs)
    assert len(result) == 2


# ── Discovery engine ──────────────────────────────────────────────────────

from sponsorscout.core.discovery_engine import detect_ats, _extract_company_name

def test_detect_ats_ashby():
    assert detect_ats("https://jobs.ashbyhq.com/Linear") == "ashby"

def test_detect_ats_greenhouse():
    assert detect_ats("https://boards.greenhouse.io/stripe") == "greenhouse"

def test_detect_ats_lever():
    assert detect_ats("https://jobs.lever.co/monzo") == "lever"

def test_detect_ats_workday():
    assert detect_ats("https://amazon.wd1.myworkdayjobs.com/en-US/External") == "workday"

def test_detect_ats_teamtailor():
    assert detect_ats("https://jobs.teamtailor.com/companies/acme") == "teamtailor"

def test_detect_ats_smartrecruiters():
    assert detect_ats("https://jobs.smartrecruiters.com/Acme") == "smartrecruiters"

def test_detect_ats_bamboohr():
    assert detect_ats("https://acme.bamboohr.com/jobs") == "bamboohr"

def test_extract_name_lever():
    assert _extract_company_name("https://jobs.lever.co/monzo", "lever") == "Monzo"

def test_extract_name_ashby():
    assert _extract_company_name("https://jobs.ashbyhq.com/linear", "ashby") == "Linear"

def test_extract_name_greenhouse():
    name = _extract_company_name("https://boards.greenhouse.io/stripe", "greenhouse")
    assert name == "Stripe"


# ── Database new columns ──────────────────────────────────────────────────

from sponsorscout.db.database import initialize, get_connection, search_jobs, get_dashboard_stats, enqueue_discovery, get_pending_discovery, mark_discovery_processed
from sponsorscout.core.persistence import upsert_job, save_company

@pytest.fixture
def test_db(tmp_path):
    db = tmp_path / "test.db"
    initialize(db)
    return db

def _insert_job(db, url, country="Germany", remote_type="onsite", eu_blue_card=0, has_relocation=0, sponsorship_score=20):
    conn = get_connection(db)
    upsert_job(conn, {
        "title": "Test Job", "company": "TestCo", "country": country,
        "location": "Berlin" if country else "Remote", "url": url,
        "description": "test",
        "ats_source": "greenhouse", "source_type": "verified", "source_name": "greenhouse",
        "trust_score": 90, "freshness_score": 100,
        "sponsorship_score": sponsorship_score, "match_score": 50,
        "verified_active": 1, "is_expired": 0,
        "remote_type": remote_type, "eu_blue_card": eu_blue_card, "has_relocation": has_relocation,
    })
    conn.close()

def test_initialize_upgrades_old_jobs_schema(tmp_path):
    db = tmp_path / "old_schema.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT NOT NULL, company TEXT NOT NULL, country TEXT DEFAULT '', location TEXT DEFAULT '', url TEXT UNIQUE NOT NULL, ats_source TEXT DEFAULT '', source_type TEXT DEFAULT 'verified', source_name TEXT DEFAULT '', description TEXT DEFAULT '', trust_score INTEGER DEFAULT 0, freshness_score INTEGER DEFAULT 0, sponsorship_score INTEGER DEFAULT 0, match_score INTEGER DEFAULT 0, verified_active INTEGER DEFAULT 0, is_expired INTEGER DEFAULT 0, first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP, last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP, last_verified_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.close()

    initialize(db)

    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "experience_level" in cols
    assert "remote_type" in cols
    assert "eu_blue_card" in cols
    assert "has_relocation" in cols
    conn.close()


def test_upsert_job_persists_experience_level(test_db):
    conn = get_connection(test_db)
    upsert_job(conn, {
        "title": "Senior Engineer",
        "company": "Acme",
        "country": "Germany",
        "location": "Berlin",
        "url": "https://x.com/senior",
        "description": "Lead role",
        "ats_source": "greenhouse",
        "source_type": "verified",
        "source_name": "greenhouse",
        "trust_score": 50,
        "freshness_score": 50,
        "sponsorship_score": 70,
        "match_score": 60,
        "verified_active": 1,
        "is_expired": 0,
        "remote_type": "onsite",
        "eu_blue_card": 0,
        "has_relocation": 0,
        "experience_level": "senior",
    })
    row = conn.execute(
        "SELECT experience_level FROM jobs WHERE url=?",
        ("https://x.com/senior",)
    ).fetchone()
    assert row["experience_level"] == "senior"
    conn.close()


def test_search_jobs_experience_filter_and_latest_sort(tmp_path):
    db = tmp_path / "search.db"
    initialize(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO jobs (title, company, country, location, url, ats_source, source_type, source_name, description, trust_score, freshness_score, sponsorship_score, match_score, verified_active, is_expired, first_seen_at, remote_type, eu_blue_card, has_relocation, experience_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("Senior Engineer", "Acme", "Germany", "Berlin", "https://x.com/1", "greenhouse", "verified", "greenhouse", "Desc 1", 10, 10, 10, 10, 1, 0, "2026-06-01 00:00:00", "onsite", 0, 0, "senior"),
    )
    conn.execute(
        "INSERT INTO jobs (title, company, country, location, url, ats_source, source_type, source_name, description, trust_score, freshness_score, sponsorship_score, match_score, verified_active, is_expired, first_seen_at, remote_type, eu_blue_card, has_relocation, experience_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("Senior Developer", "Acme", "Germany", "Berlin", "https://x.com/2", "greenhouse", "verified", "greenhouse", "Desc 2", 12, 12, 12, 12, 1, 0, "2026-06-10 00:00:00", "onsite", 0, 0, "senior"),
    )
    conn.commit()
    conn.close()

    rows = search_jobs(db, experience_filter="Senior", sort_by="latest")
    assert len(rows) == 2
    assert rows[0]["url"] == "https://x.com/2"
    assert rows[1]["url"] == "https://x.com/1"


def test_eu_blue_card_filter(test_db):
    _insert_job(test_db, "https://x.com/1", eu_blue_card=1)
    _insert_job(test_db, "https://x.com/2", eu_blue_card=0)
    rows = search_jobs(test_db, eu_blue_card_only=True)
    assert len(rows) == 1

def test_relocation_filter(test_db):
    _insert_job(test_db, "https://x.com/1", has_relocation=1)
    _insert_job(test_db, "https://x.com/2", has_relocation=0)
    rows = search_jobs(test_db, relocation_only=True)
    assert len(rows) == 1

def test_remote_eu_filter(test_db):
    _insert_job(test_db, "https://x.com/1", remote_type="remote_eu")
    _insert_job(test_db, "https://x.com/2", remote_type="onsite")
    rows = search_jobs(test_db, remote_filter="Remote EU")
    assert len(rows) == 1

def test_remote_global_includes_eu(test_db):
    _insert_job(test_db, "https://x.com/1", remote_type="remote_eu")
    _insert_job(test_db, "https://x.com/2", remote_type="remote_global")
    _insert_job(test_db, "https://x.com/3", remote_type="onsite")
    rows = search_jobs(test_db, remote_filter="Remote Global")
    assert len(rows) == 2

def test_country_filter_includes_eu_remote_only(test_db):
    _insert_job(test_db, "https://x.com/1", country="Germany", remote_type="onsite")
    _insert_job(test_db, "https://x.com/2", country="", remote_type="remote_eu")
    _insert_job(test_db, "https://x.com/3", country="", remote_type="remote_global")
    rows = search_jobs(test_db, country="Germany")
    urls = {row['url'] for row in rows}
    assert "https://x.com/1" in urls
    assert "https://x.com/2" in urls
    assert "https://x.com/3" not in urls

def test_stats_include_remote_eu_blue_card(test_db):
    _insert_job(test_db, "https://x.com/1", remote_type="remote_global", eu_blue_card=1)
    stats = get_dashboard_stats(test_db)
    assert stats["remote_jobs"] == 1
    assert stats["eu_blue_card_jobs"] == 1

def test_discovery_queue(test_db):
    enqueue_discovery(test_db, "https://jobs.ashbyhq.com/Co", "ashby", "Co", "Germany")
    pending = get_pending_discovery(test_db)
    assert len(pending) == 1
    assert pending[0]["ats_type"] == "ashby"
    mark_discovery_processed(test_db, "https://jobs.ashbyhq.com/Co")
    pending2 = get_pending_discovery(test_db)
    assert len(pending2) == 0

def test_sponsorship_only_filter(test_db):
    _insert_job(test_db, "https://x.com/1", sponsorship_score=80)
    _insert_job(test_db, "https://x.com/2", sponsorship_score=10)
    rows = search_jobs(test_db, sponsorship_only=True)
    assert len(rows) == 1


# ── Location country derivation ───────────────────────────────────────────

from sponsorscout.core.location_country import country_from_location

def test_city_only_sao_paulo():
    assert country_from_location("São Paulo", fallback="Netherlands") == "Brazil"

def test_city_only_singapore():
    assert country_from_location("Singapore", fallback="Netherlands") == "Singapore"

def test_city_only_amsterdam():
    assert country_from_location("Amsterdam", fallback="Netherlands") == "Netherlands"

def test_city_comma_country():
    assert country_from_location("Amsterdam, Netherlands", fallback="") == "Netherlands"

def test_city_comma_us_state():
    assert country_from_location("New York, NY", fallback="") == "United States"
    assert country_from_location("San Francisco, CA", fallback="") == "United States"

def test_city_comma_ca_province():
    assert country_from_location("Toronto, ON", fallback="") == "Canada"

def test_remote_returns_empty():
    assert country_from_location("Remote", fallback="Netherlands") == ""
    assert country_from_location("Remote - EU", fallback="Netherlands") == ""
    assert country_from_location("Remote - US", fallback="Netherlands") == ""

def test_worldwide_returns_empty():
    assert country_from_location("Worldwide", fallback="Netherlands") == ""
    assert country_from_location("Multiple Locations", fallback="Netherlands") == ""

def test_empty_location_uses_fallback():
    assert country_from_location("", fallback="Germany") == "Germany"

def test_normalize_job_uses_location_country():
    from sponsorscout.core.normalizer import normalize_job
    raw = {
        "title": "Data Analyst",
        "company": "Adyen",
        "country": "Netherlands",   # company HQ
        "location": "São Paulo",     # actual job location
        "url": "https://boards.greenhouse.io/adyen/jobs/1",
        "description": "",
        "ats_source": "greenhouse",
    }
    result = normalize_job(raw, "verified", "greenhouse")
    assert result["country"] == "Brazil", f"Expected Brazil, got {result['country']!r}"
    assert result["location"] == "São Paulo"

def test_normalize_job_remote_no_country():
    from sponsorscout.core.normalizer import normalize_job
    raw = {
        "title": "Engineer", "company": "Acme", "country": "Netherlands",
        "location": "Remote", "url": "https://x.com/1", "description": "", "ats_source": "x",
    }
    result = normalize_job(raw, "verified", "x")
    assert result["country"] == ""

def test_country_filter_excludes_remote_global(test_db):
    _insert_job(test_db, "https://x.com/r", country="", remote_type="remote_global")
    _insert_job(test_db, "https://x.com/local", country="Germany", remote_type="onsite")
    rows = search_jobs(test_db, country="Germany")
    urls = [r["url"] for r in rows]
    assert "https://x.com/r" not in urls
    assert "https://x.com/local" in urls
