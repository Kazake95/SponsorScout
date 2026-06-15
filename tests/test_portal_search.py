from sponsorscout.core.portal_search import extract_ats_links, extract_jobs_from_html, likely_careers_urls
from sponsorscout.core.discovery_engine import (
    _build_search_query,
    _clean_search_href,
    _extract_search_result_urls,
    _resolve_search_engines,
)


def test_likely_careers_urls_expands_company_domain():
    urls = likely_careers_urls("example.com")
    assert "https://example.com/careers" in urls
    assert "https://example.com/jobs" in urls


def test_extract_ats_links_from_embedded_careers_page():
    html = """
    <html><body>
      <a href="https://jobs.ashbyhq.com/acme">Open roles</a>
      <a href="/privacy">Privacy</a>
    </body></html>
    """
    links = extract_ats_links("https://acme.com/careers", html)
    assert links == ["https://jobs.ashbyhq.com/acme"]


def test_extract_jobs_honors_filters_for_sponsor_remote_eu_role():
    html = """
    <section class="job">
      <a href="/careers/jobs/data-analyst-berlin">Senior Data Analyst</a>
      <span>Berlin, Germany</span>
      <p>Visa sponsorship and relocation support available. Remote EU friendly.</p>
    </section>
    <section class="job">
      <a href="/careers/jobs/sales-manager">Sales Manager</a>
      <span>London, UK</span>
      <p>No visa sponsorship. On-site only.</p>
    </section>
    """
    jobs = extract_jobs_from_html(
        "https://acme.com/careers",
        html,
        query="data analyst",
        country="Germany",
        sponsorship_only=True,
        remote_filter="Remote EU",
    )
    assert len(jobs) == 1
    assert jobs[0].title == "Senior Data Analyst"
    assert jobs[0].url == "https://acme.com/careers/jobs/data-analyst-berlin"


def test_search_engine_resolver_supports_all_eu_and_csv():
    assert "google" in _resolve_search_engines("all")
    assert "startpage" in _resolve_search_engines("eu")
    assert _resolve_search_engines("google,qwant") == ["google", "qwant"]


def test_google_redirect_href_is_cleaned_to_ats_url():
    href = "/url?q=https%3A%2F%2Fjobs.ashbyhq.com%2Facme%2Fjobs%2F123&sa=U"
    assert _clean_search_href(href) == "https://jobs.ashbyhq.com/acme/jobs/123"


def test_extract_search_result_urls_filters_to_ats_links():
    html = """
    <a href="/url?q=https%3A%2F%2Fjobs.lever.co%2Facme%2Fabc&sa=U">ATS</a>
    <a href="https://example.com/blog">Noise</a>
    <a href="https://boards.greenhouse.io/acme/jobs/1">Job</a>
    """
    urls = _extract_search_result_urls(html, ["a[href]"])
    assert urls == [
        "https://jobs.lever.co/acme/abc",
        "https://boards.greenhouse.io/acme/jobs/1",
    ]


def test_search_query_includes_google_compatible_site_terms():
    q = _build_search_query("data analyst", "Germany")
    assert "data analyst" in q
    assert "Germany" in q
    assert "site:greenhouse.io" in q
    assert "site:ashbyhq.com" in q
