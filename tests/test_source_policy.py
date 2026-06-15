from sponsorscout.services.source_policy import classify_source

def test_verified_source():
    source_type, trust, discovery_only = classify_source("greenhouse")
    assert source_type == "verified"
    assert trust == 100
    assert discovery_only is False

def test_modern_ats_sources_are_verified():
    source_type, trust, discovery_only = classify_source("ashby")
    assert source_type == "verified"
    assert trust >= 90
    assert discovery_only is False

def test_discovery_source():
    source_type, trust, discovery_only = classify_source("indeed")
    assert source_type == "discovery"
    assert discovery_only is True
