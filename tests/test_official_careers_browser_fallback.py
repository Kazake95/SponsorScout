from sponsorscout.core import portal_search
from sponsorscout.services.registry_loader import load_seed_registry


class _Resp:
    def __init__(self, url, text, status_code=200):
        self.url = url
        self.text = text
        self.status_code = status_code


class _Session:
    def get(self, url, timeout=20, allow_redirects=True):
        # Static HTML deliberately contains no job listings — only a hydrated
        # SPA shell — but is intentionally >200 bytes so it passes the
        # length guard inside crawl_official_careers and the JS-render
        # fallback path is invoked.
        shell = (
            '<html><body><div id="root"></div>'
            + '<!-- hydrated by client-side bundle; see https://acme.com/careers for rendered view -->'
            + '<nav><a href="/about">About</a><a href="/blog">Blog</a>'
            + '<a href="/contact">Contact</a></nav>'
            + '<footer>© Acme Inc.</footer>'
            + '</body></html>'
        )
        return _Resp(url, shell)


def test_crawl_official_careers_uses_rendered_html_when_static_page_is_empty(monkeypatch):
    def _rendered(url, **kwargs):
        return {
            "url": url,
            "title": "Open roles",
            "html": """
                <html><body>
                  <a href="https://jobs.lever.co/acme/123">Senior Analyst</a>
                  <a href="https://jobs.ashbyhq.com/acme">Open roles</a>
                </body></html>
            """,
            "status": 200,
            "rendered_by": "playwright",
        }

    monkeypatch.setattr(portal_search, "fetch_rendered_html", _rendered)

    jobs, ats_links = portal_search.crawl_official_careers(
        _Session(),
        "https://acme.com/careers",
        max_pages=2,
        limit=20,
    )

    assert len(jobs) >= 1
    assert jobs[0].title == "Senior Analyst"
    assert "https://jobs.lever.co/acme/123" in ats_links


def test_registry_loader_skips_remote_portal_catalogs():
    rows = load_seed_registry()
    names = {row["name"] for row in rows}
    assert "Shopify" in names
    assert "Veriff" in names
    assert "RemoteOK" not in names


def test_registry_loader_parses_company_rows_with_commas_in_careers_url():
    rows = load_seed_registry()
    ikea = next(row for row in rows if row["name"] == "Ikea Italia")
    assert ikea["careers_url"].startswith("https://jobs.ikea.com/it/lavori-di-ricerca?")
    assert ikea["ats_type"] == "official_careers"
    assert ikea["country"] == "Italy"
