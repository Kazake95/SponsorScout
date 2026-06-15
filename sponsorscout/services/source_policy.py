VERIFIED_SOURCE_TRUST = {
    "greenhouse": 100,
    "lever": 100,
    "workable": 100,
    "ashby": 100,
    "workday": 100,
    "personio": 95,
    "recruitee": 95,
    "smartrecruiters": 95,
    "teamtailor": 90,
    "bamboohr": 90,
    "jobvite": 90,
    "icims": 85,
    "homerun": 90,
    "freshteam": 90,
    "breezy": 90,
    "welcometothejungle": 90,
    "manatal": 85,
    "official_careers": 80,
}
DISCOVERY_SOURCE_TRUST = {"indeed": 60, "linkedin": 60, "google_jobs": 55}

def classify_source(source_name: str):
    s = (source_name or "").lower()
    if s in VERIFIED_SOURCE_TRUST:
        return "verified", VERIFIED_SOURCE_TRUST[s], False
    if s in DISCOVERY_SOURCE_TRUST:
        return "discovery", DISCOVERY_SOURCE_TRUST[s], True
    return "unknown", 20, True
