# SponsorScout — Complete Technical Documentation

**Version:** 0.1.1 | **License:** MIT | **Python:** ≥ 3.10  
**Platform:** Windows / Linux / macOS (Desktop GUI with PySide6)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Scan Pipeline](#scan-pipeline)
4. [Job Classification](#job-classification)
5. [UI Reference](#ui-reference)
6. [Database](#database)
7. [Core Utilities](#core-utilities)
8. [Scanning Engine](#scanning-engine)
9. [Developer Guide — Project Structure](#developer-guide--project-structure)
10. [Developer Guide — Common Tasks](#developer-guide--common-tasks)
11. [Design Patterns & Pitfalls](#design-patterns--pitfalls)

---

## Overview

SponsorScout discovers job postings with verified visa-sponsorship potential from:
- **ATS boards** (Greenhouse, Lever, Ashby, Workday, Personio, etc.) via public APIs
- **Company career pages** via browser-based crawling (Playwright)

It classifies each job for visa sponsorship, relocation support, and EU Blue Card eligibility using context-aware analysis of job descriptions.

Results are stored in SQLite and presented through a 5-tab desktop interface.

### Quick Start

```bash
pip install -e .
python -m sponsorscout.main
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `SPONSORSCOUT_DATA_DIR` | Override data directory |
| `SPONSORSCOUT_DB_PATH` | Override database path |

---
## UI Reference

**Main Window:** Navy header (#1d2d44) + 5-tab QTabWidget. Logo 28×28, "SponsorScout" 20px bold, subtitle, language combo (10 locales). First-run: if 0 companies + 0 jobs → prompt. Language switching: set_locale() → retranslate() on all tabs.

**Tab 1: Dashboard** — 6 stat cards (Total Companies, Verified Jobs, Sponsored Jobs, Remote Jobs, EU Blue Card, Applications). Tables: Top Companies by Sponsorship (10 rows), Jobs by Country. Buttons: "Rescan Companies" (→ Tools quick scan), "Refresh".

**Tab 2: Search** — Filters: Title/Company/Location (QLineEdit), Country/Remote (QComboBox), Sponsor/Blue Card/Reloc (QCheckBox), Regex (QCheckBox). Results: 9 columns (Title, Company, Country, Location, Sponsor, Blue Card, Reloc, Remote, Posted). Verdicts: Y (confirmed), N (excluded), ? (unknown). Double-click opens URL; right-click → Open/Save/Copy.

**Tab 3: Applications** — Status pipeline: saved → applied → interview → offer → rejected. Table: Company, Title, Status, Saved on, URL. Edit form on selection: Status combo + Notes + Save/Cancel.

**Tab 4: Tools** — Scanner: Method (Quick/Full), Start/Stop, progress log (QPlainTextEdit). History: scan runs table + double-click → per-company scan_log dialog. Data quality: Dedup companies/jobs, Clear expired/unknowns. Freshness: Verify links button + results table (background thread).

**Tab 5: Data Management** — Sub-tabs: ATS Seeds | Career Seeds. Editable seed table. Actions: Add/Edit/Delete (SeedRowDialog), Import CSV, Export CSV, Reset to bundled defaults. SeedRowDialog: base fields (name, ats_type, url, industry, 3 scores) + advanced (seed_name, canonical_name, target_country, provider, board_slug, notes, source_type, scope_policy). URL auto-detects ATS type.

**Styling:** Colors: HEADER_BG=#1d2d44, ACCENT=#3a7bd5, CARD_BG=#ffffff, BODY_BG=#f0f2f5. QSS ~75 lines. Fusion style + forced light palette.

## Architecture

```
main.py → QApplication → SponsorScoutApp (QMainWindow, 5 tabs)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        DashboardTab    SearchTab      ApplicationsTab
              │               │               │
              ▼               ▼               ▼
         ToolsTab ──── ScanCoordinator ──→ pipeline.run_scan()
              │               │
        DataMgmtTab     seed_manager       ▼
                              │    ┌─────────────────────┐
                              ▼    │ ATS Scanner (API)   │
                        user seeds  └─────────────────────┘
                                       │
                                       ▼
                               ┌─────────────────────┐
                               │ Career Scanner      │
                               │ (Browser/Playwright)│
                               └─────────────────────┘
                                       │
                                       ▼
                               ┌─────────────────────┐
                               │ Pipeline Ingestion  │
                               │ • Dedup             │
                               │ • Score derivation  │
                               │ • DB upsert         │
                               └─────────────────────┘
                                       │
                                       ▼
                               ┌─────────────────────┐
                               │ SQLite (sponsorscout.db) │
                               └─────────────────────┘
```

**Key Modules:**
- Entry: sponsorscout/main.py — Bootstraps Qt app, loads locale, launches window
- UI: sponsorscout/ui/ — 5 tab widgets + main window + QSS stylesheet
- App logic: sponsorscout/application/ — ScanCoordinator (threaded scan runner), SeedManager (CSV ops)
- Scanning: sponsorscout/scanning/ — ATS scanner (API), Career scanner (browser), Pipeline (orchestration+ingestion), JD Support (visa detection)
- Core: sponsorscout/core/ — HTTP client, URL normalizer, ATS detection, location→country, persistence
- DB: sponsorscout/db/database.py — SQLite schema, migrations, queries
- Connectors: sponsorscout/connectors/ — 20+ ATS-specific API connectors
- i18n: sponsorscout/i18n/ — 10 locales

---

## Scan Pipeline

### Phase 1: Seed Loading & Company Sync
Read user seed CSVs (mutable copies), merge bundled seeds → user copies (appends new, preserves edits), persist each unique company to DB.

**Seed schema (v6 base):** name, ats_type, careers_url, industry, sponsorship_history, english_friendly, remote_score
**Extra (v7 career):** seed_name, canonical_name, source_type, target_country, scope_policy, provider, board_slug, notes

### Phase 2a: ATS Scan (ATSScanner)
1. Read seed CSV, optionally filter by only_companies
2. Preflight check (Google, Greenhouse API, Ashby API, Lever API, SmartRecruiters API) — unless skipped
3. Query ATS API for each company via appropriate connector
4. Write CSVs to SCAN_OUTPUT_DIR: *_jobs.csv, *_recruiter.csv, *_quarantine.csv, *_scan_log.csv

### Phase 2b: Career Scan (CareerScanner, Full only)
1. Playwright browser crawl for JS-rendered pages
2. HTTP fallback for static pages
3. JS helpers: deep DOM query, visibility checks, job URL detection
4. Location: 1000+ cities → country mapping, ISO-2, US states, CA provinces
5. Same output CSV structure

### Phase 3: Ingestion
Dedup by canonical_job_id, then upsert_job for each row. Also ingests *_recruiter.csv and *_scan_log.csv.

### Score Derivation (Locked Decision #3)
```python
def derive_sponsorship_score(verdict, confidence, history):
    v = str(verdict).strip().lower()
    if v == "y":   base = 70
    elif v == "n": return 0
    else:          return 35  # Unknown — neutral, no bonuses
    conf = max(0, min(1, float(confidence or 0)))
    hist = max(0, min(100, int(history or 0)))
    return int(round(max(0, min(100, base + conf*20 + hist*0.10))))
```

### Summary Dict
{"run_id": str, "method": "quick"|"full", "status": "completed"|"partial"|"cancelled"|"error", "cancelled": bool, "ingested": int, "duplicates": int, "log_rows": int, "artifacts": {"ats": {...}, "career": {...}}, "errors": [str, ...]}

---

## Job Classification (jd_support.py)
---

## Database

**Connection:** PRAGMA journal_mode=WAL, foreign_keys=ON, busy_timeout=5000. REGEXP function backed by Python re. Row factory: sqlite3.Row.

**Tables:**
- **companies**: name TEXT UNIQUE, country, ats_type, careers_url, industry, sponsorship_history_score (0-100), english_friendly_score (0-100), remote_score (0-100), created_at, updated_at. Upsert: ON CONFLICT(name) DO UPDATE.
- **jobs** (40+ cols): url TEXT UNIQUE (stable key), title, company, country, location, ats_source, source_type, source_subtype, description, trust_score, freshness_score, sponsorship_score (0-100), match_score, verified_active (1/0), is_expired (1/0), last_verified_at, remote_type, eu_blue_card (0/1 derived), has_relocation (0/1 derived), experience_level, industry (backfilled), ai_score, + scan evidence columns (visa_sponsorship, relocation_support, eu_blue_card_verdict, etc.).
- **discoveries**: company, job_title, job_url, source_name, source_type, verification_status, promoted_to_job.
- **applications**: job_url TEXT UNIQUE, company, title, status (saved/applied/interview/offer/rejected), applied_at, notes.
- **scan_runs**: run_id TEXT PK, method, started_at, finished_at, status, jobs_found, jobs_duplicates, targets_ok/empty/error, error, created_at.
- **scan_log**: run_id, seed_name, company, source_type, target_country, status, provider, jobs_found, quarantined, duplicates, rejected_scope, error, diagnostics, duration_sec, seed_url.

**Migrations:** Idempotent — check column existence before ALTER. Recent: remote_type, eu_blue_card, has_relocation, experience_level, source_subtype, industry, ai_score, scan evidence columns.
**location_country.py:** country_from_location(raw, fallback) → str. Strategies: 1) global/remote patterns → "" 2) country name match 3) parenthetical "Remote (Netherlands)" 4) comma-split right-to-left (country, ISO-2 with US state disambiguation, US state, CA province) 5) city lookup (1000+) 6) fallback. Data: ISO2_TO_COUNTRY (50+), US_STATES_ABBR/FULL, CA_PROVINCES_FULL, COUNTRY_NAMES, CITY_TO_COUNTRY (1000+), _AMBIGUOUS_US_STATES.

**persistence.py:** save_company() upsert ON CONFLICT(name) DO UPDATE. upsert_job(): defense in depth (verdicts recompute booleans), industry backfill, full 40+ col preservation. mark_job_expired(): verified_active=0, is_expired=1, freshness_score=0.

---

## Scanning Engine
**ATSScanner:** Preflight: probes Google/Greenhouse/Ashby/Lever/SmartRecruiters APIs. Retry: 3 attempts, 1.5s backoff, 35s timeout. SEED_UPGRADE: InnoGames→EU Lever, Avomind→recruiter. KNOWN_BOARD_ISSUES: surfaces empty/404 boards. BAD_HOSTS: blocks glassdoor/indeed/linkedin/etc. Output: 35-col CSV + 15-col scan log + recruiter + quarantine. Cancellation: cancel_event checked between targets, never interrupts in-flight requests.

**CareerScanner:** Playwright browser for JS pages, HTTP fallback. JS_HELPERS: querySelectorAllDeep (shadow DOM), isVisible, isBadScope, looksJobUrl (two-pass), firstGoodLine (multi-pass title), badLocationRe (rejects departments/brands/contract words). Location: COUNTRIES_AND_REGIONS + KNOWN_CITIES + Chinese cities, diacritic-insensitive (Wrocław↔wroclaw, München↔munchen). JS-based pagination traversal.
**Pipeline (pipeline.py):** run_scan(method, db_path, cancel_event, progress). method: "quick" (ATS only) | "full" (ATS+Career). Flow: 1) Load+merge seeds 2) Sync companies to DB 3) ATS scan → CSV artifacts 4) If full: career scan → CSV artifacts 5) Ingest: dedup (canonical_job_id) → upsert_job → copy scan_log rows 6) Finalize scan_runs 7) Return summary. Error handling: status="error" if ingested==0, "cancelled" if stopped, "partial" if some errors, "completed" otherwise.

---

## Developer Guide — Project Structure

```
sponsorscout/
├── main.py, paths.py, pyproject.toml
├── application/scan_coordinator.py, seed_manager.py
├── scanning/pipeline.py, common.py, jd_support.py
│   ├── ats/ats_scanner.py
│   └── career/career_scanner.py
├── core/http_client.py, url_normalizer.py, ats_detection.py,
│   location_country.py, persistence.py
├── db/database.py
├── connectors/base.py + 20+ ATS connectors
├── ui/app.py, style.py, tabs/{dashboard,search,applications,tools,data_management}.py
├── i18n/__init__.py (10 locales: en, it, de, fr, es, nl, pt, pl, ru, kz)
└── data/seeds/, icons/
```

Dev Setup: pip install -e . ; pip install -e ".[dev]" ; playwright install chromium. Env vars: SPONSORSCOUT_DATA_DIR, SPONSORSCOUT_DB_PATH, PLAYWRIGHT_BROWSERS_PATH.

---

## Developer Guide — Common Tasks

**New ATS Connector:** 1) Create connectors/newats.py inheriting BaseConnector, set ats_name, implement fetch_jobs() 2) Add to SUPPORTED_ATS_TYPES 3) Add URL fingerprint to ats_detection.py 4) Test with seed CSV.

**New UI Tab:** 1) Create ui/tabs/newtab.py (QWidget with refresh(), retranslate()) 2) Export in ui/tabs/__init__.py 3) Wire in ui/app.py:_build_tabs() and retranslate().

---

## Developer Guide — Project Structure

```
sponsorscout/
├── main.py, paths.py, pyproject.toml
├── application/scan_coordinator.py, seed_manager.py
├── scanning/pipeline.py, common.py, jd_support.py
│   ├── ats/ats_scanner.py
│   └── career/career_scanner.py
├── core/http_client.py, url_normalizer.py, ats_detection.py,
│   location_country.py, persistence.py
├── db/database.py
├── connectors/base.py + 20+ ATS connectors
├── ui/app.py, style.py, tabs/{dashboard,search,applications,tools,data_management}.py
├── i18n/__init__.py (10 locales: en, it, de, fr, es, nl, pt, pl, ru, kz)
└── data/seeds/, icons/
```

Dev Setup: pip install -e . ; pip install -e ".[dev]" ; playwright install chromium. Env vars: SPONSORSCOUT_DATA_DIR, SPONSORSCOUT_DB_PATH, PLAYWRIGHT_BROWSERS_PATH.

---

## Developer Guide — Common Tasks

**New ATS Connector:** 1) Create connectors/newats.py inheriting BaseConnector, set ats_name, implement fetch_jobs() 2) Add to SUPPORTED_ATS_TYPES 3) Add URL fingerprint to ats_detection.py 4) Test with seed CSV.

**New UI Tab:** 1) Create ui/tabs/newtab.py (QWidget with refresh(), retranslate()) 2) Export in ui/tabs/__init__.py 3) Wire in ui/app.py:_build_tabs() and retranslate().

**Modify Visa Detection:** scanning/jd_support.py — JDSupportDetector. Never keyword-only, always context-aware. Verdicts Y/N/Unknown only. Update VISA_CONCEPTS, RELOCATION_CONCEPTS, POSITIVE_VERBS, NEGATION, REQUIREMENT, CONDITIONAL, SCOPE. Add EXTRA_LANGS for new languages.

**DB Schema Changes:** db/database.py — _apply_migrations(). Check existing_cols before ALTER. Update persistence.py if special handling needed.

**Localization:** i18n/__init__.py — add to locale dict.

---

## Design Patterns & Pitfalls

**Patterns:** 1) Deferred imports (heavy modules in functions/threads) 2) Signal-based thread communication (Qt signals from worker threads) 3) Context managers (http_session() auto-close) 4) Defense in depth (verdicts recompute booleans) 5) Idempotent operations (migrations, seed merging, upserts) 6) No silent drops (quarantine→CSV, empty results logged).

**Pitfalls:** cf-ray/cf_clearance as bot detection (false positives) → use exclusive markers only. Sorting query params → preserve order. INSERT OR IGNORE → ON CONFLICT DO UPDATE. Not checking cancel_event → check between targets. Qt import before QApplication → deferred imports. Fabricating "No" → return "Unknown". Bare build_session() → use http_session() context manager.

**Build:** Linux .deb (build_deb.sh) / Windows .exe (build_exe.ps1) — PyInstaller, bundles Chromium. Inno Setup sets PLAYWRIGHT_BROWSERS_PATH in HKCU\Environment.

**Testing:** 1) Start app 2) Add companies 3) Run scan (Quick/Full) 4) Verify Dashboard/Search 5) Test cancellation 6) Test i18n 7) Test data management edits.
**Modify Visa Detection:** scanning/jd_support.py — JDSupportDetector. Never keyword-only, always context-aware. Verdicts Y/N/Unknown only. Update VISA_CONCEPTS, RELOCATION_CONCEPTS, POSITIVE_VERBS, NEGATION, REQUIREMENT, CONDITIONAL, SCOPE. Add EXTRA_LANGS for new languages.

**DB Schema Changes:** db/database.py — _apply_migrations(). Check existing_cols before ALTER. Update persistence.py if special handling needed.

**Localization:** i18n/__init__.py — add to locale dict.

---

## Design Patterns & Pitfalls

**Patterns:** 1) Deferred imports (heavy modules in functions/threads) 2) Signal-based thread communication (Qt signals from worker threads) 3) Context managers (http_session() auto-close) 4) Defense in depth (verdicts recompute booleans) 5) Idempotent operations (migrations, seed merging, upserts) 6) No silent drops (quarantine→CSV, empty results logged).

**Pitfalls:** cf-ray/cf_clearance as bot detection (false positives) → use exclusive markers only. Sorting query params → preserve order. INSERT OR IGNORE → ON CONFLICT DO UPDATE. Not checking cancel_event → check between targets. Qt import before QApplication → deferred imports. Fabricating "No" → return "Unknown". Bare build_session() → use http_session() context manager.

**Build:** Linux .deb (build_deb.sh) / Windows .exe (build_exe.ps1) — PyInstaller, bundles Chromium. Inno Setup sets PLAYWRIGHT_BROWSERS_PATH in HKCU\Environment.

**Testing:** 1) Start app 2) Add companies 3) Run scan (Quick/Full) 4) Verify Dashboard/Search 5) Test cancellation 6) Test i18n 7) Test data management edits.