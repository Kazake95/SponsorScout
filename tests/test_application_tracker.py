from sponsorscout.db.database import initialize, upsert_application, list_applications

def test_application_tracker(tmp_path):
    db = tmp_path / "sponsorscout.db"
    initialize(db)
    upsert_application(db, "https://example.com/job", "Example", "Data Analyst", status="saved", notes="test")
    rows = list_applications(db)
    assert len(rows) == 1
    assert rows[0]["company"] == "Example"
