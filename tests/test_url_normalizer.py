
from sponsorscout.core.url_normalizer import normalize_url

def test_normalize_url_strips_tracking():
    url = "https://Example.com/jobs/?utm_source=linkedin&x=1&b=2"
    assert normalize_url(url) == "https://example.com/jobs?b=2&x=1"
