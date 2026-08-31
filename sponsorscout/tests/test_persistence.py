"""Tests for upsert_job verdict->boolean derivation and country fallback."""
from sponsorscout.core import persistence


def test_upsert_derives_booleans_from_verdicts(db_path):
    from sponsorscout.db import database as db
    conn = db.get_connection(db_path)
    persistence.upsert_job(conn, {
        "title": "Backend Engineer", "company": "Acme",
        "url": "https://jobs.example/1",
        "visa_sponsorship": "Y", "relocation_support": "Unknown",
        "eu_blue_card_verdict": "Y",
    })
    persistence.upsert_job(conn, {
        "title": "Intern", "company": "Beta",
        "url": "https://jobs.example/2",
        "visa_sponsorship": "N", "relocation_support": "Y",
        "eu_blue_card_verdict": "Unknown",
    })
    rows = [tuple(r) for r in conn.execute(
        "SELECT company, eu_blue_card, has_relocation FROM jobs ORDER BY id")]
    # Unknown must never be persisted as a hard Yes/No boolean.
    assert rows == [("Acme", 1, 0), ("Beta", 0, 1)], rows
    conn.close()


def test_upsert_country_falls_back_to_location(db_path):
    from sponsorscout.db import database as db
    conn = db.get_connection(db_path)
    persistence.upsert_job(conn, {
        "title": "Engineer", "company": "Acme",
        "url": "https://jobs.example/3",
        "location": "Amsterdam, Netherlands",
    })
    row = conn.execute("SELECT country, location FROM jobs").fetchone()
    assert row["country"] == "Netherlands"
    assert row["location"] == "Amsterdam, Netherlands"
    conn.close()


def test_upsert_keeps_existing_country_when_job_country_set(db_path):
    from sponsorscout.db import database as db
    conn = db.get_connection(db_path)
    persistence.upsert_job(conn, {
        "title": "Engineer", "company": "Acme",
        "url": "https://jobs.example/4",
        "country": "Germany", "location": "Remote",
    })
    assert conn.execute("SELECT country FROM jobs").fetchone()[0] == "Germany"
    conn.close()
