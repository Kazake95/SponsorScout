from sponsorscout.core.url_normalizer import normalize_url


def _norm_name(name: str) -> str:
    """Normalize company name for case/whitespace-insensitive dedup."""
    return " ".join((name or "").strip().lower().split())


def save_company(conn, company):
    """
    Insert or update a company.

    B1 fix: previous version used INSERT OR IGNORE on the UNIQUE name column,
    which silently dropped new companies whose name collided (case/whitespace).
    Now we use ON CONFLICT to UPDATE the existing row instead.
    """
    name = company.get("name", "").strip()
    if not name:
        return
    conn.execute(
        """INSERT INTO companies
           (name, country, ats_type, careers_url, industry,
            sponsorship_history_score, english_friendly_score, remote_score)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET
             country=excluded.country,
             ats_type=excluded.ats_type,
             careers_url=COALESCE(NULLIF(excluded.careers_url, ''), companies.careers_url),
             industry=COALESCE(NULLIF(excluded.industry, ''), companies.industry),
             sponsorship_history_score=excluded.sponsorship_history_score,
             english_friendly_score=excluded.english_friendly_score,
             remote_score=excluded.remote_score,
             updated_at=CURRENT_TIMESTAMP""",
        (
            name,
            company.get("country", ""),
            company.get("ats_type", ""),
            company.get("careers_url", ""),
            company.get("industry", ""),
            int(company.get("sponsorship_history", company.get("sponsorship_history_score", 0)) or 0),
            int(company.get("english_friendly", company.get("english_friendly_score", 0)) or 0),
            int(company.get("remote_score", 0) or 0),
        ),
    )
    conn.commit()


def save_discovery(conn, discovery):
    conn.execute(
        """INSERT INTO discoveries
           (company, job_title, job_url, source_name, source_type, verification_status, promoted_to_job)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            discovery.get("company", ""),
            discovery.get("job_title", discovery.get("title", "")),
            normalize_url(discovery.get("job_url", discovery.get("url", ""))),
            discovery.get("source_name", ""),
            discovery.get("source_type", ""),
            discovery.get("verification_status", "pending"),
            int(discovery.get("promoted_to_job", 0)),
        ),
    )
    conn.commit()


def upsert_job(conn, job):
    """
    B2 fix: previous version used INSERT OR IGNORE + an unconditional UPDATE
    keyed on url. If two jobs shared the same normalized URL, the UPDATE
    could silently rewrite the wrong row's columns. Now the INSERT/UPDATE
    preserves all persisted fields, including experience_level, while still
    using the unique job URL as the stable key.
    """
    normalized_url = normalize_url(job.get("url", ""))
    company_name = (job.get("company", "") or "").strip()
    if not normalized_url:
        return

    conn.execute(
        """INSERT INTO jobs
           (external_id, title, company, country, location, url, ats_source,
            source_type, source_subtype, source_name, description, trust_score, freshness_score,
            sponsorship_score, match_score, verified_active, is_expired,
            last_verified_at, remote_type, eu_blue_card, has_relocation, experience_level,
            industry)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(url) DO UPDATE SET
             title=excluded.title,
             company=excluded.company,
             country=excluded.country,
             location=excluded.location,
             ats_source=excluded.ats_source,
             source_type=excluded.source_type,
             source_subtype=excluded.source_subtype,
             source_name=excluded.source_name,
             description=excluded.description,
             trust_score=excluded.trust_score,
             freshness_score=excluded.freshness_score,
             sponsorship_score=excluded.sponsorship_score,
             match_score=excluded.match_score,
             verified_active=excluded.verified_active,
             is_expired=excluded.is_expired,
             last_seen_at=CURRENT_TIMESTAMP,
             updated_at=CURRENT_TIMESTAMP,
             remote_type=excluded.remote_type,
             eu_blue_card=excluded.eu_blue_card,
             has_relocation=excluded.has_relocation,
             experience_level=excluded.experience_level,
             industry=COALESCE(NULLIF(excluded.industry,''), industry)""",
        (
            job.get("external_id", ""),
            job.get("title", ""),
            company_name,
            job.get("country", ""),
            job.get("location", ""),
            normalized_url,
            job.get("ats_source", ""),
            job.get("source_type", "verified"),
            job.get("source_subtype", "direct"),
            job.get("source_name", ""),
            job.get("description", ""),
            int(job.get("trust_score", 0) or 0),
            int(job.get("freshness_score", 0) or 0),
            int(job.get("sponsorship_score", 0) or 0),
            int(job.get("match_score", 0) or 0),
            int(bool(job.get("verified_active", True))),
            int(bool(job.get("is_expired", False))),
            job.get("last_verified_at", None),
            job.get("remote_type", "onsite"),
            int(job.get("eu_blue_card", 0) or 0),
            int(job.get("has_relocation", 0) or 0),
            job.get("experience_level", ""),
            job.get("industry", ""),
        ),
    )
    conn.commit()


def mark_job_expired(conn, url: str):
    conn.execute(
        "UPDATE jobs SET verified_active=0, is_expired=1, freshness_score=0, updated_at=CURRENT_TIMESTAMP WHERE url=?",
        (normalize_url(url),)
    )
    conn.commit()
