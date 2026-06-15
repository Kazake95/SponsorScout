
from sponsorscout.db.database import initialize, get_connection
from sponsorscout.services.ats_health import record_success, record_failure, get_rows

def test_ats_health(tmp_path):
    db = tmp_path / "sponsorscout.db"
    initialize(db)
    conn = get_connection(db)
    record_success(conn, "greenhouse", 120)
    record_failure(conn, "greenhouse", 220)
    conn.close()
    rows = get_rows(db)
    assert rows[0]["ats_name"] == "greenhouse"
    assert rows[0]["success_count"] == 1
    assert rows[0]["failure_count"] == 1
