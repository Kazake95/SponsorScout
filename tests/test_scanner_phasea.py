import logging

from sponsorscout.db.database import initialize, get_connection
from sponsorscout.core.scanner import scan_all

class DummyConnector:
    def __init__(self, jobs):
        self._jobs = jobs
    def fetch_jobs(self, company):
        return self._jobs

def test_scanner_marks_expired(tmp_path, monkeypatch):
    db = tmp_path / "sponsorscout.db"
    initialize(db)

    companies = [{
        "name": "ExampleCo",
        "country": "Netherlands",
        "ats_type": "greenhouse",
        "careers_url": "https://example.com/careers",
        "industry": "SaaS",
        "sponsorship_history": 90,
        "english_friendly": 95,
        "remote_score": 80,
    }]

    job = {
        "external_id": "1",
        "title": "Data Analyst",
        "company": "ExampleCo",
        "country": "Netherlands",
        "location": "Remote",
        "url": "https://example.com/jobs/1?utm_source=linkedin",
        "description": "SQL Power BI Visa sponsorship available",
        "ats_source": "greenhouse",
    }

    monkeypatch.setattr("sponsorscout.core.scanner.get_connector", lambda ats: DummyConnector([job]))
    first = scan_all(companies, db_path=db)
    assert len(first) == 1

    conn = get_connection(db)
    row = conn.execute("SELECT url, verified_active, is_expired FROM jobs").fetchone()
    assert row["verified_active"] == 1
    assert row["is_expired"] == 0
    assert row["url"] == "https://example.com/jobs/1"

    monkeypatch.setattr("sponsorscout.core.scanner.get_connector", lambda ats: DummyConnector([]))
    second = scan_all(companies, db_path=db)
    assert len(second) == 0

    row2 = conn.execute("SELECT url, verified_active, is_expired FROM jobs").fetchone()
    assert row2["verified_active"] == 0
    assert row2["is_expired"] == 1
    conn.close()


def test_scanner_skips_invalid_jobs(tmp_path, monkeypatch, caplog):
    """Job with empty URL should be skipped and counted as a per-job error."""
    db = tmp_path / "sponsorscout.db"
    initialize(db)

    companies = [{
        "name": "ExampleCo",
        "country": "Netherlands",
        "ats_type": "greenhouse",
        "careers_url": "https://example.com/careers",
        "industry": "SaaS",
        "sponsorship_history": 90,
        "english_friendly": 95,
        "remote_score": 80,
    }]

    bad_job = {
        "external_id": "1",
        "title": "Data Analyst",
        "company": "ExampleCo",
        "country": "Netherlands",
        "location": "Remote",
        "url": "",  # invalid URL after normalization
        "description": "SQL Power BI Visa sponsorship available",
        "ats_source": "greenhouse",
    }

    monkeypatch.setattr("sponsorscout.core.scanner.get_connector", lambda ats: DummyConnector([bad_job]))
    caplog.set_level(logging.ERROR)
    result = scan_all(companies, db_path=db)

    assert result == []
    assert "Failed to normalize or persist job" in caplog.text

    conn = get_connection(db)
    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == 0
    conn.close()


def test_scanner_skips_jobs_missing_required_fields(tmp_path, monkeypatch, caplog):
    """Job with missing title should also be skipped gracefully."""
    db = tmp_path / "sponsorscout.db"
    initialize(db)

    companies = [{
        "name": "ExampleCo",
        "country": "Netherlands",
        "ats_type": "greenhouse",
        "careers_url": "https://example.com/careers",
        "industry": "SaaS",
        "sponsorship_history": 90,
        "english_friendly": 95,
        "remote_score": 80,
    }]

    bad_job = {
        "external_id": "2",
        "title": "",  # missing title
        "company": "ExampleCo",
        "country": "Netherlands",
        "location": "Berlin",
        "url": "https://example.com/jobs/2",
        "description": "SQL Power BI",
        "ats_source": "greenhouse",
    }

    monkeypatch.setattr("sponsorscout.core.scanner.get_connector", lambda ats: DummyConnector([bad_job]))
    caplog.set_level(logging.ERROR)
    result = scan_all(companies, db_path=db)

    assert result == []
    assert "Failed to normalize or persist job" in caplog.text

    conn = get_connection(db)
    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == 0
    conn.close()