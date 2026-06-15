from sponsorscout.services.country_config import ordered_countries

def test_country_order():
    countries = ordered_countries()
    assert "Ireland" in countries
    assert "Netherlands" in countries
    assert "United Arab Emirates" in countries


def test_curated_groups_keep_their_order():
    """The hand-tuned EU-priority ordering must stay at the front."""
    countries = ordered_countries()
    assert countries[:7] == [
        "Ireland", "Netherlands", "Germany", "Belgium",
        "Luxembourg", "Austria", "Italy",
    ]


def test_registry_only_countries_are_appended():
    """Countries present in the CSV registries but not in the curated
    profile (e.g. Canada, Cyprus, France, United States) should still be
    selectable in the country filter."""
    countries = ordered_countries()
    curated_count = 21  # total entries currently in country_profile.json
    extras = countries[curated_count:]

    for extra_country in ("Canada", "Cyprus", "France", "United States"):
        assert extra_country in countries
        assert extra_country in extras  # appended after the curated groups

    # Extras should be sorted alphabetically.
    assert extras == sorted(extras)


def test_extra_country_appears_without_modifying_profile_json(monkeypatch):
    """A brand-new country added only via CSV data becomes available
    without any change to country_profile.json."""
    import sponsorscout.services.country_config as cc

    fake_companies = [{"country": "Norway"}, {"country": "Ireland"}, {"country": ""}]
    monkeypatch.setattr(
        "sponsorscout.services.registry_loader.load_seed_registry",
        lambda: fake_companies,
    )

    countries = cc.ordered_countries()
    assert "Norway" in countries
    # Ireland is already curated, so it shouldn't be duplicated.
    assert countries.count("Ireland") == 1
