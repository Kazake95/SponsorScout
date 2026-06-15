CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    country TEXT NOT NULL,
    ats_type TEXT NOT NULL,
    careers_url TEXT NOT NULL,
    industry TEXT DEFAULT '',
    sponsorship_history_score INTEGER DEFAULT 0,
    english_friendly_score INTEGER DEFAULT 0,
    remote_score INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    external_id TEXT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    country TEXT DEFAULT '',
    location TEXT DEFAULT '',
    url TEXT UNIQUE NOT NULL,
    ats_source TEXT DEFAULT '',
    source_type TEXT DEFAULT 'verified',
    source_name TEXT DEFAULT '',
    description TEXT DEFAULT '',
    trust_score INTEGER DEFAULT 0,
    freshness_score INTEGER DEFAULT 0,
    sponsorship_score INTEGER DEFAULT 0,
    match_score INTEGER DEFAULT 0,
    verified_active INTEGER DEFAULT 0,
    is_expired INTEGER DEFAULT 0,
    first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TEXT,
    remote_type TEXT DEFAULT 'onsite',
    eu_blue_card INTEGER DEFAULT 0,
    has_relocation INTEGER DEFAULT 0,
    -- BUGFIX: added in v0.1.1 to support the new "Experience" filter
    -- (intern / entry / mid / senior / lead / exec). Derived by the
    -- normalizer at scan time from the job title; stored as a TEXT
    -- because experience-level is a soft enum (the model never changes)
    -- and a tiny one. NULL means "not yet classified" (legacy rows).
    experience_level TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- B2 fix: case/whitespace-insensitive uniqueness on company name to prevent
-- duplicates like 'ING' / 'ing' / '  Ing  ' from coexisting.
CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_name_norm
    ON companies(LOWER(TRIM(name)));

CREATE TABLE IF NOT EXISTS discoveries (
    id INTEGER PRIMARY KEY,
    company TEXT DEFAULT '',
    job_title TEXT DEFAULT '',
    job_url TEXT DEFAULT '',
    source_name TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    verification_status TEXT DEFAULT 'pending',
    promoted_to_job INTEGER DEFAULT 0,
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY,
    job_url TEXT UNIQUE NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'saved',
    applied_at TEXT,
    next_followup_at TEXT,
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(title, company, description);


CREATE TABLE IF NOT EXISTS ats_health (
    ats_name TEXT PRIMARY KEY,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0,
    avg_response_ms REAL DEFAULT 0,
    last_success TEXT,
    last_failure TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_country ON jobs(country);
CREATE INDEX IF NOT EXISTS idx_jobs_sponsorship ON jobs(sponsorship_score);
CREATE INDEX IF NOT EXISTS idx_jobs_verified ON jobs(verified_active, is_expired);
CREATE INDEX IF NOT EXISTS idx_jobs_match ON jobs(match_score);
CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url);
CREATE INDEX IF NOT EXISTS idx_jobs_firstseen ON jobs(first_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_sponsored_fresh ON jobs(sponsorship_score DESC, first_seen_at DESC);

-- Remote classification columns (added in v0.4)
CREATE TABLE IF NOT EXISTS company_discovery_queue (
    id INTEGER PRIMARY KEY,
    careers_url TEXT UNIQUE NOT NULL,
    ats_type TEXT DEFAULT 'official_careers',
    company_name TEXT DEFAULT '',
    country TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_discovery_status ON company_discovery_queue(status);
