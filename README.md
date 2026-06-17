# SponsorScout

A privacy-first desktop tool for discovering visa-sponsoring jobs in Europe. Scans 17 ATS platforms and company career portals, detects sponsorship and relocation signals, and helps international candidates focus on EU-friendly roles.

Fully local. No accounts. No cloud. Data stays on your machine in a SQLite database.

---

## Features

- **Background mode** — minimize to system tray and keep scanning silently
- **17 ATS connectors** — Greenhouse, Lever, Ashby, Workable, Workday, Personio, Recruitee, BambooHR, SmartRecruiters, Teamtailor, Jobvite, iCIMS, Homerun, Freshteam, Breezy, Welcome to the Jungle, Manatal
- **Official careers fallback** — probes company career pages when no known ATS API exists
- **Portal discovery engine** — auto-finds career pages via search + embedded ATS link detection
- **Sponsorship scoring** — keyword-based scoring with EU Blue Card and relocation detection
- **Application tracker** — track job application status (Applied, Interview, Offer, Rejected)
- **AI-assisted tools** — job rating, CV tailoring, and cover letter generation via browser-based copy-paste (no API keys required)
- **Search objectives** — preset filters: Balanced, Strict Quality, Visa Sponsor, Local EU, Remote EMEA, Blue Card
- **Internationalisation** — English and Italian, switchable from the header dropdown
- **Fully local data** — SQLite database with WAL mode, stored in your user data directory

---

## Requirements

- Python 3.10 or later (tested on 3.10–3.13)
- pip
- tkinter (standard with Python on Windows and macOS; on Ubuntu/Debian: `sudo apt install python3-tk`)

---

## Quick Start

### 1. Clone or unzip

```bash
git clone https://github.com/Kazake95/SponsorScout_Final_Build_Ready.git
cd SponsorScout
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Or install as a package (gives you CLI commands):

```bash
pip install -e .
```

### 3. Launch

```bash
python -m sponsorscout.main
```

Or if installed with `pip install -e .`:

```bash
sponsorscout
```

On first launch you'll be prompted to run an initial scan. Click **Yes** to fetch live jobs from the curated registry. Takes 1–3 minutes for the default registry.

---

## Running the App

**GUI mode:**

```bash
sponsorscout
# or
python -m sponsorscout.main
```

**Background mode (system tray):**

```bash
sponsorscout --background
# or
python -m sponsorscout.main --background
```

The app minimizes to the system tray and keeps running in the background. Right-click the tray icon to restore the window or quit.

Requires the `pystray` package (included in `requirements.txt`). On Linux you may also need `python3-appindicator` or `libappindicator-gtk3` for tray support.

---

## CLI Commands

### Scan companies

```bash
# Scan all companies sequentially
sponsorscout-scan
# or
python -m sponsorscout.scripts.run_scan

# Parallel scan (4 workers, faster)
sponsorscout-scan --parallel

# Scan and deduplicate
sponsorscout-scan --parallel --dedup

# Scan a single company
sponsorscout-scan --company "Adyen"
```

### Discovery mode

Discover extra company portals before scanning:

```bash
sponsorscout-scan \
  --discover "data analyst" \
  --country Germany \
  --domain example.com \
  --sponsorship-only \
  --search-engine eu \
  --remote-filter "Remote EU" \
  --parallel
```

Use `--domain` multiple times when expanding EU company coverage.

`--search-engine` accepts `all`, `eu`, or a comma-separated list from:
`google`, `duckduckgo`, `startpage`, `qwant`, `ecosia`, `mojeek`, `swisscows`.

The `eu` shortcut uses Startpage, Qwant, Ecosia, Mojeek, and Swisscows.

### Import companies

```bash
# Import from CSV
sponsorscout-import path/to/companies.csv
# or
python -m sponsorscout.scripts.import_companies path/to/companies.csv
```

### Diagnose a scan

```bash
python -m sponsorscout.scripts.diagnose_scan
```

### Expanded registry

Set `SPONSORSCOUT_LOAD_EXPANDED=1` to include the expanded company registry:

```bash
SPONSORSCOUT_LOAD_EXPANDED=1 sponsorscout-scan --parallel
```

---

## Windows Installation

Windows users get a **proper setup wizard** built with Inno Setup.

### Build the installer (developer)

Prerequisites:

- **Windows 10/11** (64-bit)
- **Python 3.10+** from [python.org](https://www.python.org/downloads/windows/) (tick "Add python.exe to PATH")
- **PowerShell 5+**
- **Inno Setup 6+** from [jrsoftware.org](https://jrsoftware.org/isdl.php) (add `ISCC.exe` to PATH)

```powershell
cd path\to\SponsorScout
.\build_exe.ps1
```

The script installs dependencies, runs tests, builds with PyInstaller, and compiles the Inno Setup installer.

### Install (end user)

1. Download `sponsorscout-<version>-setup.exe`.
2. Double-click to launch the wizard.
3. Accept the license, choose the install location (default: `C:\Program Files\SponsorScout`), and finish.
4. The app launches automatically.

The installer:

- Creates `%APPDATA%\SponsorScout` for user data
- Adds Start Menu and optional Desktop shortcuts
- Registers in "Apps & Features" for clean uninstall

### Uninstall

**Settings → Apps → Apps & features → SponsorScout → Uninstall**

This removes:

- Program Files directory
- Start Menu and Desktop shortcuts
- Registry entries
- **All user data** in `%APPDATA%\SponsorScout` (database, profiles, logs)

> ⚠️ Uninstalling removes all local data permanently. Back up anything you need first.

### Notes

- **SmartScreen warning**: Unsigned installer triggers "Windows protected your PC." Click **More info** → **Run anyway**. Sign the binary with a code-signing certificate to eliminate this.
- **Antivirus false positives**: PyInstaller binaries are occasionally flagged. Submit a false-positive report to your AV vendor.
- **Path with spaces**: Always OK — the app uses absolute internal paths.
- **tkinter on Windows**: Bundled with the official python.org installer. No extra steps.

---

## Linux Installation

### Debian/Ubuntu package

```bash
./build_deb.sh
```

Creates `dist/sponsorscout_<version>_amd64.deb`, installs to `/opt/sponsorscout/`, launcher at `/usr/bin/sponsorscout`.

### Source install

```bash
pip install .
```

---

## AI Features

SponsorScout includes AI-assisted tools for job rating, CV tailoring, and cover letter generation.

### Browser-based workflow (no API keys needed)

The default workflow uses web-based AI chat sites:

1. Go to **Tools** → **AI Settings** and select your preferred chat site (ChatGPT, Gemini, Claude, Mistral, or Perplexity).
2. Select a job in Search → click **Rate this job**. The app builds a prompt and opens the chat site in your browser.
3. Copy the prompt, paste it into the chat, and paste the AI's response back into SponsorScout.
4. Same workflow for **CV Tailoring** and **Cover Letter** generation.

### API-based workflow (optional)

If you prefer direct API calls, SponsorScout also supports Google Gemini and OpenAI-compatible endpoints. Set your API key in **Tools** → **AI Settings** to enable the API buttons.

### Customisable prompts

All prompts (job rating, CV tailoring, cover letter) are customisable in the AI Settings tab. You can also set a **Base Cover Letter Template** as a style reference for future generations.

---

## Adding Your Own Companies

Edit `sponsorscout/data/company_registry_seed.csv` and add a row:

```
name,country,ats_type,careers_url,ats_board_token,...
Monzo,United Kingdom,greenhouse,https://boards.greenhouse.io/monzo,monzo,...
```

**`ats_board_token`** is the slug used in the ATS API URL:

| ATS | Where to find the token | Example |
|---|---|---|
| Greenhouse | `boards.greenhouse.io/{token}` | `monzo` |
| Lever | `jobs.lever.co/{token}` | `databricks` |
| Ashby | `jobs.ashbyhq.com/{token}` | `linear` |
| Workable | `apply.workable.com/{token}` | `workable` |
| Workday | `{token}.wd1.myworkdayjobs.com/…/{site}` | tenant=`ing`, site=`ING` |
| Personio | `{token}.jobs.personio.com` | `pleo` |
| Recruitee | `{token}.recruitee.com` | `bynder` |
| BambooHR | `{token}.bamboohr.com` | `bamboohr` |
| SmartRecruiters | `jobs.smartrecruiters.com/{token}` | `SmartRecruiters` |
| Teamtailor | `{token}.teamtailor.com` | leave blank |
| Jobvite | `jobs.jobvite.com/{token}` | leave blank |
| iCIMS | custom per client | leave blank |

Use `official_careers` as the `ats_type` when no known ATS API exists. The fallback probes common paths (`/careers`, `/jobs`, `/open-positions`), detects embedded ATS board links, and extracts likely job cards with role/country/sponsorship/remote filters.

---

## Search Objectives

The Search tab includes objective presets to keep results narrow and high-signal:

| Preset | Description |
|--------|-------------|
| Balanced | Default mix of match quality and breadth |
| Strict quality | Tighter skill and title matching |
| Visa sponsor | Prioritises explicit sponsorship signals |
| Local EU | Focuses on EU-based roles |
| Remote EMEA | Includes remote positions across EMEA |
| Blue Card focus | Targets EU Blue Card-eligible roles |

These presets filter the same shared database, so you can switch between job-search goals without rescanning.

---

## Application Tracker

The Applications tab lets you track the status of jobs you've applied to:

- **Applied** — you've submitted an application
- **Interview** — interview stage
- **Offer** — received an offer
- **Rejected** — application was rejected

Filter, sort, and manage your application pipeline from one place.

---

## Project Structure

```
sponsorscout/
├── connectors/          # One file per ATS — fetch_jobs() returns job dicts
│   ├── __init__.py      # Connector registry + get_connector()
│   ├── base.py          # Base connector class
│   ├── common.py        # Shared helpers
│   ├── greenhouse.py
│   ├── lever.py
│   ├── ashby.py
│   ├── workable.py
│   ├── workday.py
│   ├── personio.py
│   ├── teamtailor.py
│   ├── smartrecruiters.py
│   ├── bamboohr.py
│   ├── recruitee.py
│   ├── jobvite.py
│   ├── icims.py
│   ├── homerun.py
│   ├── freshteam.py
│   ├── breezy.py
│   ├── welcometothejungle.py
│   ├── manatal.py
│   └── official_careers.py  # HTML fallback for custom career pages
│
├── core/
│   ├── scanner.py              # Orchestrates scans (sequential + parallel)
│   ├── discovery_engine.py     # Auto-find companies via search + ATS fingerprinting
│   ├── portal_search.py        # Company career page probing/extraction
│   ├── sponsorship.py          # Keyword scoring, EU Blue Card, relocation detection
│   ├── scoring.py              # Match score vs. user profile
│   ├── ats_detection.py        # Detect embedded ATS links on career pages
│   ├── normalizer.py           # Country/title/location normalisation
│   ├── location_country.py     # Country detection from text
│   ├── dedup.py                # Fingerprint-based job and company deduplication
│   ├── persistence.py          # upsert_job, save_company, mark_job_expired
│   ├── verification.py         # mark_verified / mark_expired helpers
│   ├── verification_service.py # HTTP liveness checker (dead-job phrase detection)
│   ├── http_client.py          # requests Session with retry + UA
│   └── url_normalizer.py       # Strip tracking params, normalise URLs
│
├── db/
│   ├── database.py          # All SQL queries: search, stats, discovery queue, etc.
│   ├── schema.sql           # Full schema (applied on initialize())
│   └── migrate_countries.py # Country migration helper
│
├── models/
│   └── job.py              # Job dataclass
│
├── services/
│   ├── scan_coordinator.py  # Foreground scan coordinator (one-shot worker thread)
│   ├── ai_rating.py         # Prompt builders and response parsers for AI tools
│   ├── ai_webview.py        # Opens ChatGPT/Gemini/Claude/Mistral/Perplexity in browser
│   ├── ats_health.py        # Track success/failure per ATS connector
│   ├── browser_fetcher.py   # HTTP page fetcher with HTML parsing
│   ├── country_config.py    # Ordered country list from profile JSON
│   ├── objectives.py        # Search objective presets (Balanced, Visa Sponsor, etc.)
│   ├── profile.py           # Loads default_profile.json
│   ├── registry_loader.py   # Reads company_registry_seed.csv
│   └── source_policy.py     # Classifies job source (verified vs discovery)
│
├── scripts/
│   ├── run_scan.py          # CLI: --parallel --dedup --company --discover
│   ├── import_companies.py  # CLI: import CSV of companies
│   └── diagnose_scan.py     # Diagnostic tool for scan issues
│
├── ui/
│   ├── app.py              # Full tkinter GUI (tabs, system tray, header)
│   └── tabs/               # Tab modules
│
├── data/
│   ├── company_registry_seed.csv      # Curated companies with ATS tokens
│   ├── company_registry_expanded.csv  # Optional expanded registry
│   ├── default_profile.json           # User matching profile (skills, titles, countries)
│   ├── country_profile.json           # EU priority tiers for scoring
│   ├── sponsorscout.ico               # App icon
│   ├── sponsorscout.png               # App icon
│   └── icons/                         # Multi-size icons for system tray
│
├── i18n.py        # Internationalisation: translation dicts + locale persistence
├── paths.py       # Data directory and file path resolution
└── main.py        # Entry point → ui/app.py:main()

tests/             # pytest suite
```

---

## Customising Your Match Profile

Edit `sponsorscout/data/default_profile.json`:

```json
{
  "skills": ["Python", "SQL", "dbt", "Spark"],
  "titles": ["Data Engineer", "Analytics Engineer", "Backend Engineer"],
  "countries": ["Netherlands", "Germany", "United Kingdom"]
}
```

Match scores update on the next scan.

---

## Supported ATS Connectors

| ATS | Method | Public API? |
|---|---|---|
| Greenhouse | `GET boards.greenhouse.io/api/v1/boards/{token}/jobs` | ✅ Yes |
| Lever | `GET api.lever.co/v0/postings/{token}?mode=json` | ✅ Yes |
| Ashby | `POST api.ashbyhq.com/posting-api/job-board/{slug}` | ✅ Yes |
| Workable | `GET apply.workable.com/api/v3/accounts/{slug}/jobs` | ✅ Yes |
| Workday | `POST {tenant}.wd1.myworkdayjobs.com/wday/cxs/…/jobs` | ✅ Yes |
| Personio | `GET {slug}.jobs.personio.com/xml` | ✅ Yes (XML) |
| Recruitee | `GET {slug}.recruitee.com/api/offers` | ✅ Yes |
| BambooHR | `GET {slug}.bamboohr.com/jobs/embed2/list` | ✅ Yes |
| SmartRecruiters | `GET api.smartrecruiters.com/v1/companies/{slug}/postings` | ✅ Yes |
| Teamtailor | `GET {company}.teamtailor.com/jobs.json` | ⚠️ Partial (no auth) |
| Jobvite | `GET jobs.jobvite.com/{slug}/feed?format=json` | ⚠️ Partial |
| iCIMS | HTML fallback (no standard public API) | ❌ Varies per client |
| Homerun | Connector-specific endpoints | ⚠️ Varies |
| Freshteam | Connector-specific endpoints | ⚠️ Varies |
| Breezy | Connector-specific endpoints | ⚠️ Varies |
| Welcome to the Jungle | Connector-specific endpoints | ⚠️ Varies |
| Manatal | Connector-specific endpoints | ⚠️ Varies |
| official_careers | Multi-path portal crawler + embedded ATS detection | — |

The `official_careers` fallback probes common career-page paths, detects embedded ATS board links, and extracts likely job cards with role/country/sponsorship/remote filters. It's used when no known ATS API is available.

---

## Data & Privacy

Everything is stored locally on your machine:

| Platform | Location |
|----------|----------|
| Linux / macOS | `~/.sponsorscout` |
| Windows | `%APPDATA%\SponsorScout` |

The data directory contains:

- `sponsorscout.db` — SQLite database (WAL mode) with all jobs, companies, and scan history
- `default_profile.json` — your matching profile
- `locale.json` — language preference
- `ai_prompts.json` — customised AI prompt templates

**No telemetry. No accounts. No cloud sync.**

Set a custom location:

```bash
export SPONSORSCOUT_DATA_DIR=/custom/path
# or
export SPONSORSCOUT_DB_PATH=/custom/path/sponsorscout.db
```

Delete the data directory to reset completely.

---

## Internationalisation

Switch languages from the dropdown in the top-right corner of the header.

| Locale | Language |
|--------|----------|
| `en` | English |
| `it` | Italiano |

Your language choice is saved and restored on next launch.

### Adding a new language

1. Open `sponsorscout/i18n.py`.
2. Add a new entry to the `LANGUAGES` dict:

```python
LANGUAGES = {
    "en": { ... },
    "it": { ... },
    "fr": {
        "Search": "Recherche",
        "Dashboard": "Tableau de bord",
        "Applications": "Candidatures",
        # ... translate all strings
    },
}
```

3. The `_("...")` wrapper in the UI automatically picks up the active locale.

---

## Running Tests

```bash
pip install pytest
pytest tests/ -q
```

---

## Build Packages

| Platform | Command | Output |
|----------|---------|--------|
| Linux .deb | `./build_deb.sh` | `dist/sponsorscout_<version>_amd64.deb` |
| Windows setup | `.\build_exe.ps1` | `dist\sponsorscout-<version>-setup.exe` |
| Source | `pip install .` | CLI entry points: `sponsorscout`, `sponsorscout-scan`, `sponsorscout-import` |

---

## License

This project is licensed under the [MIT License](LICENSE).