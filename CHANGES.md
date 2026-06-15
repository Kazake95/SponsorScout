# Job-scraping robustness fixes

This package addresses the "many companies (Bolt, Shopify, etc.) return 0 jobs
from their official careers page" issue. Three independent root causes were
identified and fixed in `sponsorscout/core/portal_search.py` and
`sponsorscout/services/browser_fetcher.py`.

## 1. Curated "verified" careers_url is often a landing page, not a job list

For companies with `ats_type=official_careers`, the scanner passes
`is_verified=True`, which previously made `crawl_official_careers` fetch
**only** that one URL. If that page is a marketing landing page (e.g.
`shopify.com/careers`) with no job cards and no "next" pagination links, the
crawl ended immediately with 0 jobs — even though the actual listings live a
click away at `/careers/positions`, `/careers/search`, etc.

**Fix**: new `careers_path_fallbacks()` helper. If the verified URL yields 0
jobs (after the existing render/rescue passes), `crawl_official_careers` now
probes the standard `CAREERS_PATHS` sub-paths for the same domain before
giving up. `CAREERS_PATHS` also gained a few more common patterns
(`/careers/search`, `/careers/all-jobs`, `/find-a-job`, etc.).

## 2. SPA boards that fetch jobs via XHR/GraphQL, never inlining them into the DOM

Some boards (Bolt-style Vue/React apps) load job data from a JSON/GraphQL API
after the page renders. `page.content()` only reflects what ends up in the
DOM — if the framework keeps job data in JS state without writing it back to
markup the extraction found nothing, even with Playwright.

**Fix**: `browser_fetcher._render_with_playwright` now registers a
`page.on("response", ...)` listener (`_register_json_capture`) that captures
small JSON responses from URLs that look job/career/API-related. These
captured blobs are returned as `captured_json` and fed into
`portal_search.extract_jobs_from_html(..., extra_json_blobs=...)`, which runs
the same job-shape heuristics (`_collect_jobs_from_json`) against them.

## 3. Job "cards" with no `<a href>` — client-side router / data attributes only

Many SPA job cards are `<div>`s with an `onclick` handler that calls a JS
router (`router.push(...)`, `location.href = ...`) or only carry a
`data-job-id` and rely on JS to navigate — there's no real link for the
existing anchor-based extraction to find.

**Fix**: `_extract_div_job_cards` now:
- recognizes more card container patterns (`data-testid*="job"`, `li[class*="job"]`, etc.)
- parses `onclick`/`onmousedown` handlers for `location.href=`, `router.push(...)`, `navigate(...)`, etc.
- falls back to synthesizing `/jobs/{id}` from `data-job-id` / `data-position-id` / `data-vacancy-id` / `data-employment-id`
- no longer requires a heading element — falls back to the container's own text as the title

## Bonus fix: false-positive "Search jobs" links blocking the fallback

`JOB_URL_RE` matches bare category paths like `/careers/positions` (the regex
allows the keyword to be at the end of the path). A "Search jobs" link
pointing at that category page was being counted as a single "job", which
prevented the new 0-jobs fallback (#1) from ever firing. Expanded the
`junk_titles` list in `_looks_like_job` with ~40 generic "go to the job list"
CTA phrases ("search jobs", "browse roles", "view all jobs", "find a job",
"current openings", etc.) so these are correctly rejected.

## Robustness for infinite-scroll / "load more" SPA boards

`_render_with_playwright`'s scroll logic was a fixed 4-step scroll. It's now
`_scroll_and_expand()`: scrolls to the bottom repeatedly (up to 8 rounds),
clicking any visible "Load more / Show more jobs / View more" button it
finds, and stops once `document.body.scrollHeight` stops growing.

## Testing

- All 93 pre-existing tests still pass.
- 6 new tests in `tests/test_portal_search_robustness.py` cover each fix
  above with synthetic HTML/JSON (no live network access required).

## Notes / next steps

- This sandbox has no network access to bolt.eu / shopify.com etc., so these
  changes were validated against synthetic fixtures that reproduce the same
  HTML/JSON shapes, not against the live sites. Run
  `python -m sponsorscout.scripts.diagnose_scan` after applying this patch to
  confirm the JOBS_FOUND / STATIC_JOBS counts improve for the companies that
  were previously returning 0.
- Make sure Playwright's Chromium browser is actually installed
  (`playwright install chromium`) — if it isn't, every SPA-only company will
  still return 0 jobs regardless of these fixes, since `_playwright_available()`
  only checks that the *package* imports, not that a browser binary exists.
  Consider bundling/checking for this in the packaged `.exe`/`.deb` builds.

## 4. Country filter dropdown is now dynamic too

`ordered_countries()` (used to populate the "Country:" filter in the Search
tab) previously read *only* the hand-curated EU-priority list in
`data/country_profile.json`, independent of what's actually in the CSV
registries. Companies for Canada, Cyprus, France, and the United States
existed in the data but had no way to be selected via the country filter
(only reachable through "All").

**Fix**: `ordered_countries()` keeps the curated EU-priority groups in their
existing order, then appends (alphabetically) any additional countries found
in `load_seed_registry()` that aren't already covered. So adding companies
for a brand-new country in a CSV makes that country automatically selectable
in the dropdown — no edits to `country_profile.json` needed.

4 new tests added to `tests/test_country_config.py` (102 total now pass).

## Reminder: ats_type values must match a known connector

`registry_loader` merges any CSV with the right columns automatically, but
the `ats_type` column is looked up against a fixed set of ~18 connector keys
(`greenhouse`, `lever`, `workable`, `ashby`, `workday`, `personio`,
`teamtailor`, `smartrecruiters`, `bamboohr`, `recruitee`, `jobvite`, `icims`,
`homerun`, `freshteam`, `breezy`, `welcometothejungle`, `manatal`,
`official_careers`). A typo or unrecognized value returns no connector and,
if the careers-page crawl also finds nothing, that company silently scans to
0 jobs with no error. Leave `ats_type` blank or set it to `official_careers`
if you're unsure — the crawler in `portal_search.py` (improved above) will
auto-detect an embedded ATS from the careers page.

## 5. Build scripts / installer fixes

### 5a. installer.iss wouldn't actually compile via build_exe.ps1

`build_exe.ps1` step `[4/4]` invokes ISCC with
`/DMyAppVersion=$Version` (read from `pyproject.toml`), but `installer.iss`
unconditionally did `#define MyAppVersion "0.1.1"`. Inno Setup's
preprocessor errors on redefining a constant that was already supplied via
`/D` ("Redeclaration of MyAppVersion"), so the installer-build step would
fail on any machine that actually has Inno Setup installed.

**Fix**: wrapped the definition in the standard `#ifndef` guard:

```
#ifndef MyAppVersion
  #define MyAppVersion "0.1.1"
#endif
```

Now `build_exe.ps1`'s `/DMyAppVersion=<version from pyproject.toml>` takes
effect, while compiling `installer.iss` directly (without `/D`) still falls
back to "0.1.1".

### 5b. Windows installer's PLAYWRIGHT_BROWSERS_PATH doesn't reach the first launch

`build_exe.ps1` bundles Chromium into `dist\SponsorScout\_playwright`, and
`installer.iss` writes `PLAYWRIGHT_BROWSERS_PATH={app}\_playwright` to
`HKCU\Environment`. However, registry-based environment variable changes
don't propagate to processes started immediately afterward by the same
installer (Inno's `[Run]` "Launch SponsorScout" step) — only new process
trees started after the next login/Explorer-restart see it. So the very
first run after install would have Playwright look in its default cache
location, find nothing, and every SPA career portal would return 0 jobs
again — the exact symptom from the original report, just from a different
cause.

The Linux `.deb` doesn't have this problem because its launcher script
(`/usr/bin/sponsorscout`) `export`s the variable directly before `exec`.

**Fix**: `sponsorscout/paths.py` now has
`_configure_bundled_playwright_browsers_path()`, run at import time. When
running as a frozen build (`sys.frozen`) with a `_playwright` directory next
to the executable, and `PLAYWRIGHT_BROWSERS_PATH` isn't already set, it sets
the env var itself — making the bundled Chromium discoverable on the very
first launch regardless of registry propagation timing. The `[Registry]`
entry in `installer.iss` is left in place as a harmless secondary signal for
any other tooling that reads it.

4 new tests in `tests/test_paths_playwright_bundle.py` (106 total now pass).

### 5c. build_deb.sh only warns if Chromium isn't found at build time

If `~/.cache/ms-playwright/chromium*` doesn't exist when `build_deb.sh` runs,
it prints a `WARNING` but still produces a `.deb` with no bundled browser —
every SPA career portal will return 0 jobs on systems that install it. Not
changed in this patch (it's a build-environment hygiene issue rather than a
code bug), but consider making this `exit 1` so a broken package can't be
silently shipped, e.g.:

```bash
else
  echo "ERROR: No Chromium directory found in $PLAYWRIGHT_BROWSERS_PATH" >&2
  exit 1
fi
```


