from dataclasses import dataclass
from datetime import datetime


@dataclass
class Job:
    """Domain model for a single job listing.

    Each field maps 1:1 to a column of the ``jobs`` table defined in
    ``sponsorscout/db/schema.sql``. Adding a new column to the DB without
    adding it here will silently keep flowing through as a dict key in
    scanner code, which is exactly the inconsistency that
    SponsorScout_Codebase_Analysis.md \u00a73.4 / \u00a75.6 warned about.
    """

    external_id: str
    title: str
    company: str
    country: str
    location: str
    url: str
    description: str = ""
    ats_source: str = ""
    source_type: str = "verified"
    # Phase 3: 'direct' for jobs scraped from a company's own careers page;
    # 'aggregator' for jobs sourced from aggregator/portal cards where the
    # company name is extracted per-card rather than inherited from the registry.
    source_subtype: str = "direct"
    source_name: str = ""
    trust_score: int = 100
    freshness_score: int = 100
    sponsorship_score: int = 0
    match_score: int = 0
    verified_active: bool = True
    is_expired: bool = False
    # Extended fields (added in v0.1.1 to support the new filtering UI).
    remote_type: str = "onsite"
    eu_blue_card: int = 0
    has_relocation: int = 0
    experience_level: str = ""
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_verified_at: datetime | None = None

    def to_record(self) -> dict:
        """Return a flat dict ready for ``upsert_job`` / DB writes."""
        return self.__dict__.copy()
