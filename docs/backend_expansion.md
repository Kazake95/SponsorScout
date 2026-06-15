# Backend Expansion Guide

This guide explains how developers can expand SponsorScout with more EU job sources without weakening data quality.

## Data model

Mutable data lives in the per-user app directory (`~/.sponsorscout` by default):

- `sponsorscout.db`: SQLite database.
- `sponsorscout.db-wal` / `sponsorscout.db-shm`: SQLite WAL files.
- AI settings, prompts, CV text, and provider settings.

Override locations for development:

```bash
export SPONSORSCOUT_DATA_DIR=/tmp/sponsorscout-dev
export SPONSORSCOUT_DB_PATH=/tmp/sponsorscout-dev/sponsorscout.db
```

Schema lives in `sponsorscout/db/schema.sql`; idempotent migrations live in `sponsorscout/db/database.py`.

## Adding companies to the registry

Add stable, high-quality company sources to:

- `sponsorscout/data/company_registry_seed.csv` for default production coverage.
- `sponsorscout/data/company_registry_expanded.csv` for broader optional coverage.

CSV shape:

```csv
name,country,ats_type,careers_url,ats_board_token,industry,sponsorship_history,english_friendly,remote_score
ExampleCo,Germany,greenhouse,https://boards.greenhouse.io/exampleco,exampleco,SaaS,80,90,70
```

Prefer official ATS boards over third-party aggregators. Use `official_careers` only when no supported ATS API exists.

## Discovering new portals

Use the scanner discovery flags to register new portals:

```bash
python -m sponsorscout.scripts.run_scan \
  --discover "data analyst" \
  --country Germany \
  --domain example.com \
  --sponsorship-only \
  --search-engine eu \
  --remote-filter "Remote EU"
```

Discovery flow:

1. Curated ATS slug probing from `DISCOVERY_CANDIDATES`.
2. Supplied domain/careers URL probing via `core/portal_search.py`.
3. Embedded ATS link detection.
4. HTML job-card extraction for custom portals.
5. Search-engine fallback for public ATS URLs.

Supported search fallbacks:

- `google`
- `duckduckgo`
- `startpage`
- `qwant`
- `ecosia`
- `mojeek`
- `swisscows`

Use `--search-engine all` for every provider, `--search-engine eu` for the EU-oriented group, or a comma-separated list such as `--search-engine google,qwant`.

## Adding a new ATS connector

1. Create `sponsorscout/connectors/<ats_name>.py`.
2. Implement `fetch_jobs(company)` returning dictionaries with:
   `external_id`, `title`, `company`, `country`, `location`, `url`, `description`, `ats_source`.
3. Register it in `sponsorscout/connectors/__init__.py`.
4. Add URL fingerprints and company-name extraction in `sponsorscout/core/discovery_engine.py`.
5. Add source trust in `sponsorscout/services/source_policy.py`.
6. Add registry rows using the new `ats_type`.
7. Add tests for connector parsing and discovery detection.

Keep connector output normalized enough for `core/normalizer.py`; scanner/persistence handles final scoring, sponsorship detection, deduplication, and SQLite upserts.

## Improving portal extraction

General company portals use `sponsorscout/core/portal_search.py`.

Useful extension points:

- Add common careers paths to `CAREERS_PATHS`.
- Add role words to `ROLE_KEYWORDS`.
- Add ATS domains to `ATS_LINK_RE`.
- Tune `JOB_URL_RE` / `SKIP_URL_RE` when a portal produces noisy links.
- Add country or remote signals in `core/sponsorship.py` and `core/location_country.py`.

Add regression tests in `tests/test_portal_search.py` before changing broad patterns.

## Quality checks

Run:

```bash
./my_venv/bin/python -m pytest -q
```

For a targeted scan:

```bash
SPONSORSCOUT_DB_PATH=/tmp/sponsorscout-test.db \
python -m sponsorscout.scripts.run_scan --company "Adyen" --parallel --dedup
```

Review dashboard stats after a scan:

- Verified active jobs should increase.
- Sponsored jobs should only include high-signal roles.
- ATS Health should show failures by connector, not silently hide broken sources.

## Adding a new language (i18n)

SponsorScout uses `sponsorscout/i18n.py` for translation. To add a new language:

1. Open `sponsorscout/i18n.py`.
2. Add a new locale key to the `LANGUAGES` dictionary with all translated strings:

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
        # ... translate all ~160 strings
    },
}
```

3. Every user-facing string in `app.py` is wrapped with `_("...")`, which automatically picks up the active locale.
4. The locale preference is saved to `~/.sponsorscout/locale.json`.
5. Add a test in `tests/test_new_features.py` to verify the new locale loads without errors.

### Key translation categories

- **Tab names**: Search, Dashboard, Applications, ATS Health, Tools, AI Tailor
- **Filter labels**: Title, Company, Country, Sponsorship, Remote, Experience, Sort
- **Button text**: Search, Clear, Scan Now, Refresh, Discover, Run, Save
- **AI features**: Rate this job, Tailor My CV, Write Cover Letter, How to use
- **Status messages**: Ready, Scanning…, Scan complete, Discovery done.
- **Error/confirmation dialogs**: Saved, Reset, Empty, No job selected, etc.

### Architecture notes

- `set_locale(code)` sets the active locale (thread-local in-memory variable).
- `get_locale()` returns the current locale code (default `"en"`).
- `_("string")` looks up the string in `LANGUAGES[locale]`, falling back to English if not found.
- `load_saved_locale()` restores the user's preference from `~/.sponsorscout/locale.json` on startup.
- The header dropdown in `app.py` shows `get_available_locales()` and calls `set_locale()` + prompts for restart.

## AI Service (`services/ai_rating.py`)

The AI backend is provider-agnostic, supporting Google Gemini and any OpenAI-compatible endpoint.

### Provider architecture

```python
# Two API paths in _call_ai():
if provider == "gemini":
    # Google's generateContent REST API
    url = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}"
    ...
else:
    # OpenAI-compatible: /v1/chat/completions
    url = f"{base_url}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    ...
```

### Adding a new provider

To add support for a provider with a non-standard API (e.g. Anthropic Messages API):

1. Add the provider key to `DEFAULT_BASE_URLS` in `sponsorscout/services/ai_rating.py`.
2. Add a new branch in `_call_ai_once()` alongside the existing `gemini` and `openai` paths.
3. Add suggested models to `SUGGESTED_MODELS_BY_PROVIDER`.
4. Add the provider to the `prov_combo` values in `app.py` `_build_tools_tab()`.
5. Add a default base URL in `_DEFAULT_URLS` for auto-fill on provider selection.

### JSON response parsing

`_parse_ai_json()` has 5 fallback strategies to handle varying model output formats:

1. **Strict JSON** — `json.loads()` on cleaned text
2. **Extracted `{...}` block** — finds the first JSON object in text with markdown wrappers
3. **Single-quote replacement** — converts Python-style `'key': 'val'` to `"key": "val"`
4. **`ast.literal_eval`** — handles Python dict/bool syntax (`True`/`False`)
5. **Regex extraction** — last resort: extracts `"rating": N` from raw text

### Retry logic

The `_call_ai()` wrapper retries on transient errors (429, 500, 502, 503, 504) with exponential backoff (1s, 2s, 4s). Non-retryable errors (401, 403, 404) fail immediately.

## Data-quality rules

- Prefer official source URLs.
- Keep EU roles first; global/US-only sources should stay optional.
- Never mark third-party aggregator results as verified unless the job URL resolves to the official company or ATS page.
- Keep `source_policy.py` trust scores conservative for HTML-only connectors.
- Do not store secrets in registry CSV files.
