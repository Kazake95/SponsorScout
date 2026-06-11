# SponsorScout v0.1.1

A local desktop tool that scans official ATS job boards and company career portals, detects visa sponsorship / relocation signals, and helps international candidates focus on EU-friendly roles.

No cloud backend. No accounts. Data stays on your machine in a local SQLite database.

**New in v0.1.1:** Italian language support, AI-powered CV & cover letter tailoring with any model, provider-agnostic AI backend (Gemini, OpenAI, OpenRouter, Groq, NVIDIA NIM, Ollama, and more).

---

## Requirements

- Python 3.10 or later
- pip
- tkinter (standard with Python on Windows and macOS; on Ubuntu/Debian: `sudo apt install python3-tk`)

---

## Installation

### 1. Clone or unzip

```bash
unzip SponsorScout_v0.1.1.zip
cd SponsorScout
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Or install as a package (gives you the `sponsorscout` and `sponsorscout-scan` CLI commands):

```bash
pip install -e .
```

---

## Running the app

```bash
python -m sponsorscout.main
```

Or if you installed with `pip install -e .`:

```bash
sponsorscout
```

On first launch you will be prompted to run an initial scan. Click **Yes** to fetch live jobs from the curated registry through official ATS APIs and robust company-portal discovery. Takes 1–3 minutes for the default registry.

---

## CLI usage

Scan all companies (sequential):

```bash
python -m sponsorscout.scripts.run_scan
```

Parallel scan (faster, 4 workers):

```bash
python -m sponsorscout.scripts.run_scan --parallel
```

Scan and remove duplicates in one step:

```bash
python -m sponsorscout.scripts.run_scan --parallel --dedup
```

Scan a single company:

```bash
python -m sponsorscout.scripts.run_scan --company "Adyen"
```

Discover extra company portals before scanning:

```bash
python -m sponsorscout.scripts.run_scan \
  --discover "data analyst" \
  --country Germany \
  --domain example.com \
  --sponsorship-only \
  --search-engine eu \
  --remote-filter "Remote EU" \
  --parallel
```

Discovery combines curated ATS probing, supplied company domains/careers URLs, embedded ATS-link detection, robust HTML career-page extraction, and search fallbacks across Google, DuckDuckGo, and EU-oriented engines. Use `--domain` multiple times when expanding EU company coverage.

Import additional companies from a CSV:

```bash
python -m sponsorscout.scripts.import_companies path/to/companies.csv
```

---

## Adding your own companies

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

For `ats_type` use one of: `greenhouse`, `lever`, `ashby`, `workable`, `workday`, `personio`, `recruitee`, `bamboohr`, `smartrecruiters`, `teamtailor`, `jobvite`, `icims`, `homerun`, `freshteam`, `breezy`, `welcometothejungle`, `manatal`, `official_careers`.

Use `official_careers` when no known ATS API exists. The fallback now probes common paths like `/careers`, `/jobs`, `/open-positions`, detects embedded ATS board links, and extracts likely job cards with role/country/sponsorship/remote filters.

---

## Project structure

```
sponsorscout/
├── connectors/        # One file per ATS — fetch_jobs() returns list of job dicts
│   ├── __init__.py    # CONNECTORS registry + get_connector()
│   ├── greenhouse.py
│   ├── lever.py
│   ├── ashby.py
│   ├── workday.py
│   ├── personio.py
│   ├── teamtailor.py
│   ├── smartrecruiters.py
│   ├── bamboohr.py
│   ├── recruitee.py
│   ├── workable.py
│   ├── jobvite.py
│   ├── icims.py
│   └── official_careers.py  # HTML fallback for custom career pages
│
├── core/
│   ├── scanner.py           # Orchestrates scans (sequential + parallel)
│   ├── sponsorship.py       # Keyword scoring, EU Blue Card, relocation detection
│   ├── portal_search.py     # Robust company careers portal probing/extraction
│   ├── normalizer.py        # Country/title/location normalisation
│   ├── dedup.py             # Fingerprint-based job and company deduplication
│   ├── discovery_engine.py  # Auto-find companies via search + ATS fingerprinting
│   ├── verification.py      # mark_verified / mark_expired helpers
│   ├── verification_service.py  # HTTP liveness checker (14 dead-job phrases)
│   ├── persistence.py       # upsert_job, save_company, mark_job_expired
│   ├── scoring.py           # Match score vs. user profile
│   ├── http_client.py       # requests Session with retry + UA
│   └── url_normalizer.py    # Strip tracking params, normalise URLs
│
├── db/
│   ├── schema.sql     # Full schema (applied on initialize())
│   └── database.py    # All SQL queries: search, stats, discovery queue, etc.
│
├── models/
│   └── job.py         # Job dataclass
│
├── services/
│   ├── background_scanner.py  # Daemon thread scanner with pause/resume
│   ├── ats_health.py          # Record success/failure per ATS connector
│   ├── browser_fetcher.py     # Lightweight HTTP page fetcher (no browser needed)
│   ├── country_config.py      # Ordered country list from profile JSON
│   ├── profile.py             # Loads default_profile.json
│   ├── registry_loader.py     # Reads company_registry_seed.csv
│   └── source_policy.py       # Classifies job source (verified vs discovery)
│
├── scripts/
│   ├── run_scan.py         # CLI: --parallel --dedup --company
│   └── import_companies.py # CLI: import CSV of companies
│
├── ui/
│   └── app.py    # Full tkinter GUI (search, dashboard, tools, health)
│
├── i18n.py            # Internationalisation: translation dicts + locale persistence
│
├── data/
│   ├── company_registry_seed.csv  # Curated companies with ATS tokens
│   ├── company_registry_expanded.csv # Optional expanded EU/company portal registry
│   ├── default_profile.json       # User matching profile (skills, titles, countries)
│   └── country_profile.json       # EU priority tiers for scoring
│
└── main.py        # Entry point → ui/app.py:main()

tests/             # pytest suite
```

---

## Customising your match profile

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

## Supported ATS connectors

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
| Homerun / Freshteam / Breezy / WTTJ / Manatal | Connector-specific public or HTML endpoints | ⚠️ Varies |
| official_careers | Multi-path portal crawler + embedded ATS detection | — |

The `official_careers` fallback is intentionally broad so it does not miss relevant EU roles hidden behind custom company portals. It extracts likely job cards, skips social/legal/noise links, and applies the same remote/sponsorship keyword logic used by the main search filters.

---

## Discovery and filters

Search results can be filtered by:

- Country, with EU/EMEA remote jobs included where relevant.
- Sponsorship score, EU Blue Card, and relocation support.
- Remote type: EU, EMEA, global, remote-only, or hybrid.
- Experience level inferred from job title.
- Sort mode: best match, latest, or sponsored first.

Discovery filters are available from the CLI:

```bash
python -m sponsorscout.scripts.run_scan --discover "analytics engineer" --country Netherlands
python -m sponsorscout.scripts.run_scan --domain https://company.example/careers --sponsorship-only
python -m sponsorscout.scripts.run_scan --domain example.com --remote-filter "Remote EMEA"
python -m sponsorscout.scripts.run_scan --discover "data engineer" --search-engine google
python -m sponsorscout.scripts.run_scan --discover "data analyst" --search-engine eu
```

`--search-engine` accepts `all`, `eu`, or a comma-separated list from:
`google`, `duckduckgo`, `startpage`, `qwant`, `ecosia`, `mojeek`, `swisscows`.
The `eu` shortcut uses Startpage, Qwant, Ecosia, Mojeek, and Swisscows.

Set `SPONSORSCOUT_LOAD_EXPANDED=1` before running a scan to include `company_registry_expanded.csv`:

```bash
SPONSORSCOUT_LOAD_EXPANDED=1 python -m sponsorscout.scripts.run_scan --parallel
```

Developer expansion details are in [docs/backend_expansion.md](docs/backend_expansion.md).

---

## Data stays local

- Everything mutable is stored in your per-user SponsorScout data directory:
  `~/.sponsorscout` by default, including `sponsorscout.db`
- No telemetry, no accounts, no cloud sync
- Delete `~/.sponsorscout` to reset completely, or set
  `SPONSORSCOUT_DATA_DIR` / `SPONSORSCOUT_DB_PATH` for a custom location

---

## Running tests

```bash
pip install pytest
pytest tests/ -q
```

Expected: **80 passed**.


## Windows installation

Windows users get a **single self-contained `SponsorScout.exe`** built with PyInstaller `--onefile`. No installer wizard, no admin rights needed, no Python install required on the target machine.

### Build the .exe (developer side, on a Windows machine)

Prerequisites on the build machine:

- **Windows 10/11** (64-bit)
- **Python 3.10+** from [python.org](https://www.python.org/downloads/windows/) (tick **"Add python.exe to PATH"** during install)
- **PowerShell 5+** (already installed on every modern Windows)

In the project root, open PowerShell and run:

```powershell
cd path\to\SponsorScout
.\build_exe.ps1
```

The script will:
1. Upgrade `pip`
2. Install `requirements.txt` + `pyinstaller`
3. Run the test suite (skips on failure)
4. Run `pyinstaller --onefile --windowed --icon sponsorscout/data/sponsorscout.ico …`
5. Output the binary to `dist\SponsorScout.exe`

The .exe is **fully self-contained** — all Python, all data files (CSV, JSON, icons), all ATS connector code is bundled inside. Typical size: ~30 MB.

### Install the .exe (end user side)

1. Copy `dist\SponsorScout.exe` to any folder you like (e.g. `C:\Program Files\SponsorScout\` or just your Desktop).
2. Double-click it. The main window opens.

No additional files needed. The SQLite database is created in the per-user SponsorScout data directory on first run, so the app does not write into Program Files or a random launch folder.

#### Optional: pin to Start Menu / Taskbar

1. Right-click `SponsorScout.exe` → **Create shortcut**
2. Right-click the shortcut → **Pin to Start** (or **Pin to taskbar**)
3. (Optional) Right-click → **Properties** → **Change Icon…** → pick `sponsorscout.ico` from the source tree for a custom icon

#### Optional: add to PATH so you can launch from any terminal

```powershell
$env:Path += ";C:\Program Files\SponsorScout"
# Or permanently:
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\SponsorScout", "User")
```

Then from any PowerShell / cmd window:

```powershell
SponsorScout.exe
```

### Headless / CI builds

`build_exe.ps1` works on any Windows host with Python 3.10+. For fully unattended CI builds:

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

The resulting `dist\SponsorScout.exe` is the only artifact you need to ship.

### Common Windows-specific notes

- **SmartScreen warning**: A fresh, unsigned `.exe` triggers "Windows protected your PC" the first time. Click **More info** → **Run anyway**. To eliminate this, sign the binary with a code-signing certificate (`signtool sign /fd SHA256 /a dist\SponsorScout.exe`).
- **Antivirus false positives**: PyInstaller binaries are occasionally flagged. Submit a false-positive report to your AV vendor or sign the binary.
- **Path with spaces**: Always OK — the .exe uses absolute internal paths.
- **tkinter on Windows**: Already bundled with the official python.org installer, so PyInstaller picks it up automatically. No extra steps.

---

## Internationalisation (i18n)

SponsorScout supports multiple languages via the header dropdown in the top-right corner.

**Currently supported:**

| Locale | Language |
|--------|----------|
| `en` | English |
| `it` | Italiano |

Your language choice is saved to `~/.sponsorscout/locale.json` and restored on next launch.

### Adding a new language

1. Open `sponsorscout/i18n.py`.
2. Add a new entry to the `LANGUAGES` dict with your locale code and translated strings:

```python
LANGUAGES = {
    "en": { ... },
    "it": { ... },
    "fr": {
        "Search": "Recherche",
        "Dashboard": "Tableau de bord",
        "Applications": "Candidatures",
        "ATS Health": "Santé ATS",
        "Tools": "Outils",
        "Ready": "Prêt",
        # ... translate all strings
    },
}
```

3. The `_("...")` wrapper in `app.py` automatically picks up the active locale.
4. The language dropdown in the header updates when the user selects a new language.

---

## AI Features

SponsorScout includes a provider-agnostic AI backend for job rating, CV tailoring, and cover letter generation.

### Supported AI providers

| Provider | API format | Notes |
|----------|-----------|-------|
| Google Gemini | `generateContent` REST API | Free tier available; recommended |
| OpenAI | `/v1/chat/completions` | Requires API key |
| OpenRouter | `/v1/chat/completions` | Access to many models |
| Groq | `/v1/chat/completions` | Fast inference |
| Together AI | `/v1/chat/completions` | Open-source models |
| NVIDIA NIM | `/v1/chat/completions` | Enterprise models |
| Ollama | `/v1/chat/completions` | Local/free, no API key needed |
| Custom endpoint | Any `/v1/chat/completions` compatible | User provides full URL |

### Setting up AI

1. Go to **Tools** → **AI Settings**.
2. Select your provider (e.g. `gemini`).
3. Paste your API key → click **Save Key**.
4. Pick a model from the suggestion chips or type any model name → click **Save**.
5. Optionally customise the prompts (job rating, CV tailoring, cover letter).

### How AI features work

- **Job Rating**: Select a job in Search → click "Rate this job". The AI rates it 1–10 and gives an eligibility verdict.
- **CV Tailoring**: Paste your CV once in the AI Tailor tab → select a job → click "Tailor My CV". The AI rewrites your CV for that specific role.
- **Cover Letter**: Same workflow — click "Write Cover Letter" to generate a personalised letter.
- **Base Cover Letter Template**: Optional — paste a cover letter you like as a style reference for future generations.

### Provider-specific notes

- **Gemini**: Free tier has rate limits. The app retries automatically on 429 errors with exponential backoff.
- **Ollama**: Run `ollama serve` locally first. No API key needed.
- **Custom**: Paste the full chat-completions URL (e.g. `http://localhost:11434/v1/chat/completions`).

---

## Build packages

- Linux .deb: `./build_deb.sh` (creates `dist/sponsorscout_<version>_amd64.deb`, installs to `/opt/sponsorscout/`, launcher at `/usr/bin/sponsorscout`)
- Windows .exe: `build_exe.ps1` (creates `dist/SponsorScout.exe`, single-file self-contained)
- Source: `pip install .` or `pip install -e .` (gives you the `sponsorscout` and `sponsorscout-scan` CLI entry points)

---

## License

This project is licensed under the [MIT License](LICENSE).
