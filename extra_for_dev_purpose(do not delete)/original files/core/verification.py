from datetime import datetime, timezone

def mark_verified(job: dict):
    job["verified_active"] = True
    job["is_expired"] = False
    job["last_verified_at"] = datetime.now(timezone.utc).isoformat()
    job["trust_score"] = max(int(job.get("trust_score", 0)), 90)
    job["freshness_score"] = 100
    return job

def mark_expired(job: dict):
    job["verified_active"] = False
    job["is_expired"] = True
    job["freshness_score"] = 0
    return job
