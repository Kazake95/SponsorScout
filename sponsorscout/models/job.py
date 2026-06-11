from dataclasses import dataclass
from datetime import datetime

@dataclass
class Job:
    external_id: str
    title: str
    company: str
    country: str
    location: str
    url: str
    description: str = ""
    ats_source: str = ""
    source_type: str = "verified"
    source_name: str = ""
    trust_score: int = 100
    freshness_score: int = 100
    sponsorship_score: int = 0
    match_score: int = 0
    verified_active: bool = True
    is_expired: bool = False
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_verified_at: datetime | None = None
