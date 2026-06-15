from sponsorscout.db.database import initialize, get_dashboard_stats

def test_dashboard_empty(tmp_path):
    db = tmp_path / "sponsorscout.db"
    initialize(db)
    stats = get_dashboard_stats(db)
    assert stats["companies"] == 0
    assert stats["verified_jobs"] == 0
