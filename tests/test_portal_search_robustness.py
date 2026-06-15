"""Tests for the robustness improvements to official-careers scraping.

These cover the common reasons a curated ``careers_url`` returns 0 jobs:

1. The curated URL is a marketing landing page (e.g. shopify.com/careers)
   that has no job listings of its own and no "next" links — the crawler
   should fall back to standard CAREERS_PATHS sub-paths for the same domain.
2. The job board is a pure SPA that fetches job data via an XHR/GraphQL API
   and never inlines it into the DOM (e.g. Bolt) — captured network JSON
   responses should be parsed the same way as embedded <script> JSON.
3. Job "cards" use a client-side router (onclick / data-job-id) instead of
   a real <a href> — these should still be recovered as job links.
"""
from __future__ import annotations

from collections import deque

from sponsorscout.core.portal_search import (
    careers_path_fallbacks,
    crawl_official_careers,
    extract_jobs_from_html,
    likely_careers_urls,
)
from sponsorscout.core.url_normalizer import normalize_url


def test_extract_jobs_from_captured_network_json():
    """SPA boards that fetch job data via XHR should be parsed from captured JSON."""
    captured = [
        {
            "jobs": [
                {
                    "title": "Senior Backend Engineer",
                    "absolute_url": "/en/careers/positions/12345",
                    "location": "Tallinn, Estonia",
                    "description": "Visa sponsorship available.",
                },
                {
                    "title": "Data Analyst",
                    "absolute_url": "/en/careers/positions/67890",
                    "location": "Berlin, Germany",
                },
            ]
        }
    ]
    jobs = extract_jobs_from_html(
        "https://bolt.eu/en/careers/positions/",
        "<html><body><div id='app'></div></body></html>",
        extra_json_blobs=captured,
    )
    urls = {j.url for j in jobs}
    assert "https://bolt.eu/en/careers/positions/12345" in urls
    assert "https://bolt.eu/en/careers/positions/67890" in urls


def test_extract_jobs_from_onclick_router_card():
    """Job cards using client-side router onclick handlers should be recovered."""
    html = """
    <html><body>
    <div class="job-card" onclick="router.push('/careers/jobs/9988-platform-engineer')">
      <h3>Platform Engineer</h3>
      <span class="location">Amsterdam, Netherlands</span>
      <p>Visa sponsorship available for this role.</p>
    </div>
    </body></html>
    """
    jobs = extract_jobs_from_html("https://example.com/careers", html)
    assert any(j.url == "https://example.com/careers/jobs/9988-platform-engineer" for j in jobs)
    matched = [j for j in jobs if j.url.endswith("9988-platform-engineer")][0]
    assert matched.title == "Platform Engineer"


def test_extract_jobs_from_data_job_id_card():
    """Job cards with only a data-job-id (no href) synthesize a /jobs/{id} URL."""
    html = """
    <html><body>
    <div class="job-card" data-job-id="55321">
      <h3>Senior Data Scientist</h3>
      <span>Remote EU</span>
    </div>
    </body></html>
    """
    jobs = extract_jobs_from_html("https://example.com/careers", html)
    assert any(j.url == "https://example.com/jobs/55321" for j in jobs)


def test_careers_path_fallbacks_excludes_seen():
    base = "https://www.shopify.com/careers"
    seen = {normalize_url(base)}
    fallbacks = careers_path_fallbacks(base, exclude=seen)
    assert normalize_url(base) not in fallbacks
    assert any(u.endswith("/careers/positions") for u in fallbacks)


def test_likely_careers_urls_verified_returns_single_url():
    urls = likely_careers_urls("https://www.shopify.com/careers", is_verified=True)
    assert urls == ["https://www.shopify.com/careers"]


def test_crawl_official_careers_falls_back_when_landing_page_has_no_jobs(monkeypatch):
    """A verified careers_url that's a landing page should fall back to
    standard CAREERS_PATHS sub-paths and still find jobs."""
    import sponsorscout.core.portal_search as ps

    # Avoid real Playwright/network calls — pretend rendering adds nothing.
    def fake_fetch_rendered_html(url, wait_ms=2500, timeout=25, force_browser=True):
        return {"html": "", "url": url, "captured_json": [], "found_jobs": False, "bot_blocked": False, "status": 200}

    monkeypatch.setattr(ps, "fetch_rendered_html", fake_fetch_rendered_html)

    landing_html = """
    <html><body>
    <h1>Careers at Acme</h1>
    <p>We're hiring across the globe. Search open roles below.</p>
    <a href="/careers/positions">Search jobs</a>
    <a href="/about">About us</a>
    </body></html>
    """

    positions_html = """
    <html><body>
    <h1>Open Positions</h1>
    <ul>
      <li><a href="/careers/positions/1001-backend-engineer">Backend Engineer - Visa sponsorship available</a></li>
      <li><a href="/careers/positions/1002-data-analyst">Data Analyst - Remote EU</a></li>
    </ul>
    </body></html>
    """

    class FakeResp:
        def __init__(self, text, status_code=200, url=""):
            self.text = text
            self.status_code = status_code
            self.url = url

    class FakeSession:
        def get(self, url, timeout=20, allow_redirects=True):
            norm = normalize_url(url)
            if norm == normalize_url("https://acme.example/careers"):
                return FakeResp(landing_html, url=url)
            if norm == normalize_url("https://acme.example/careers/positions"):
                return FakeResp(positions_html, url=url)
            return FakeResp("", status_code=404, url=url)

    jobs, _ats_links = crawl_official_careers(
        FakeSession(), "https://acme.example/careers", is_verified=True, max_pages=8
    )

    titles = {j.title for j in jobs}
    assert "Backend Engineer - Visa sponsorship available" in titles
    assert "Data Analyst - Remote EU" in titles
