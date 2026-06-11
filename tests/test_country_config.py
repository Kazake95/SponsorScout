from sponsorscout.services.country_config import ordered_countries

def test_country_order():
    countries = ordered_countries()
    assert "Ireland" in countries
    assert "Netherlands" in countries
    assert "United Arab Emirates" in countries
