from sponsorscout.core.sponsorship import score

def test_positive_phrase():
    assert score("visa sponsorship available") > 20

def test_negative_phrase():
    assert score("must have right to work") == 0
