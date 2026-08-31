# SponsorScout

**Verified visa-sponsorship job discovery for international candidates.**

SponsorScout scans official company career pages and 17 ATS platforms, detects sponsorship and relocation signals, and helps you focus on EU-friendly roles — all from a local desktop app. No accounts. No cloud. No telemetry.

---

## What It Does

- Scans 17 ATS boards (Greenhouse, Lever, Ashby, Workable, Workday, Personio, BambooHR, SmartRecruiters, Teamtailor, Jobvite, iCIMS, Homerun, Freshteam, Breezy, Welcome to the Jungle, Manatal, Recruitee)
- Falls back to company career pages when no public ATS API exists
- Scores jobs for visa sponsorship likelihood, EU Blue Card eligibility, and relocation support
- Tracks applications through the pipeline
- Provides AI-assisted job rating, CV tailoring, and cover letter generation

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Launch
python3 -m sponsorscout.main
```

On first launch, click **Yes** in the welcome dialog to run an initial scan (1–3 minutes).

---

## Features

| Feature | Description |
|---------|-------------|
| **Multi-ATS scanning** | 17 connectors + career-page fallback crawler |
| **Sponsorship scoring** | Keyword-based signals: visa, sponsorship, relocation, EU Blue Card |
| **Search objectives** | Presets: Balanced, Strict Quality, Visa Sponsor, Local EU, Remote EMEA, Blue Card |
| **Application tracker** | Status pipeline: Saved → Applied → Interview → Offer → Rejected |
| **AI tools** | Job rating, CV tailoring, cover letter generation via web chat or direct API |
| **Internationalisation** | English and Italian; switch from the header dropdown |
| **Fully local** | SQLite database in your user data directory |

---

## Architecture

```
sponsorscout/
├── main.py                 # Entry point — localisation → DB init → UI
├── paths.py                # Runtime data directories
├── i18n.py                 # Translation strings + locale persistence
├── connectors/             # One file per ATS — fetch_jobs() → job dicts
│   └── base.py             # Abstract base + common helpers
├── core/
│   ├── scanner.py          # Scan orchestrator (sequential + parallel workers)
│   ├── discovery_engine.py # Auto-find career pages via search + ATS fingerprinting
│   ├── portal_search.py    # Career page probing and job-card extraction
│   ├── sponsorship.py      # Keyword scoring, Blue Card, relocation detection
│   ├── scoring.py          # Match score vs. user profile
│   ├── dedup.py            # Fingerprint-based job and company deduplication
│   ├── persistence.py      # upsert_job, save_company, mark_job_expired
│   ├── verification_service.py  # HTTP liveness checker for stale jobs
│   └── ...
├── db/
│   ├── database.py         # All SQL: search, stats, discovery queue, migrations
│   ├── schema.sql          # Base schema (jobs, companies, applications)
│   └── migrate_countries.py # Country/location normalisation migration
├── services/
│   ├── scan_coordinator.py # Foreground scan worker thread
│   ├── ai_rating.py        # Prompt builders + response parsers
│   ├── ai_webview.py       # Launches ChatGPT/Gemini/Claude/Mistral/Perplexity
│   ├── ai_config.py        # AI provider presets + config persistence
│   ├── ai_gateway.py       # Direct API call + connection test
│   ├── browser_fetcher.py  # HTTP fetcher + HTML parser
│   ├── country_config.py   # Ordered country list for scoring tiers
│   ├── objectives.py       # Search objective presets
│   ├── profile.py          # Loads default_profile.json
│   ├── registry_loader.py  # Reads company_registry_seed.csv
│   └── source_policy.py    # Classifies job source (verified vs discovery)
└── ui/
    └── app.py              # Full tkinter GUI — 7 tabs
```

### Tab order

1. **Dashboard** — stats, top companies, country breakdown
2. **Search** — filters, sort, objectives, AI rating panel
3. **Applications** — track pipeline status
4. **AI Tailor** — CV and cover letter rewriting
5. **AI Assistant** — browser-based AI chat workflow
6. **AI Settings** — provider, API key, model configuration
7. **Tools** — scanner, dedup, stale-data cleanup, AI prompt editor

---

## App Workflow

```
1. User launches app → main.py loads locale → initializes DB schema
2. If first run → welcome dialog offers to scan curated companies
3. Scan flow:
   a. Load company registry from CSV (seed or expanded)
   b. For each company:
      - Try known ATS connector (API or HTML fallback)
      - If no ATS, probe career-page URLs (/careers, /jobs, etc.)
      - Extract jobs with role, location, description
   c. Score each job: sponsorship signals, Blue Card, relocation, remote type
   d. Deduplicate across connectors
   e. Upsert into SQLite (new jobs / refresh existing)
4. Search / Dashboard reads from SQLite with optional objective filters
5. Application tracker manages status + notes per job URL
6. AI tools generate prompts or call configured API directly
```

### Data directory

| Platform | Location | Override env vars |
|----------|----------|-------------------|
| Linux / macOS | `~/.sponsorscout` | `SPONSORSCOUT_DATA_DIR` |
| Windows | `%APPDATA%\SponsorScout` | `SPONSORSCOUT_DB_PATH` |

Contents:
- `sponsorscout.db` — all jobs, companies, scan history
- `default_profile.json` — skills, titles, countries for match scoring
- `ai_prompts.json` — custom prompt templates
- `locale.json` — language preference

---

## Build

### Linux (.deb)

```bash
./build_deb.sh
```

Outputs `dist/sponsorscout_<version>_amd64.deb`.

### Windows (Inno Setup)

```powershell
.\build_exe.ps1
```

Outputs `dist\sponsorscout-<version>-setup.exe`. Requires Inno Setup 6.

---

## Requirements

- Python 3.10+
- tkinter (bundled with python.org Windows installer; on Ubuntu: `sudo apt install python3-tk`)
- Playwright Chromium (auto-downloaded on Linux install; on Windows downloaded on first run)

See `requirements.txt` for full dependency list.

---

## Adding Companies

Edit `sponsorscout/data/company_registry_seed.csv`:

```
name,country,ats_type,careers_url,ats_board_token
Monzo,United Kingdom,greenhouse,https://boards.greenhouse.io/monzo,monzo
```

Use `official_careers` as `ats_type` when no known ATS API exists. The fallback crawler probes common paths, detects embedded ATS links, and extracts job cards.

---

## Configuration

### Search objectives

Preset filter bundles (defined in `services/objectives.py`):

| Preset | Description |
|--------|-------------|
| Balanced | Default mix |
| Strict quality | Tighter skill/title matching |
| Visa sponsor | Prioritises sponsorship signals |
| Local EU | EU-based roles only |
| Remote EMEA | Remote roles across EMEA |
| Blue Card focus | EU Blue Card-eligible roles |

### AI providers

Configure in **Tools → AI Settings** or edit the config file:

- Google AI Studio (free tier)
- NVIDIA NIM (free credits)
- OpenAI
- Any OpenAI-compatible endpoint (vLLM, Ollama, LM Studio)

---

## License

MIT
