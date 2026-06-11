import json
from pathlib import Path

def load_country_profile():
    return json.loads((Path(__file__).resolve().parent.parent / "data" / "country_profile.json").read_text(encoding="utf-8"))


def ordered_countries():
    profile = load_country_profile()
    ordered = []
    for group in ("EU_PRIORITY", "EU_SECONDARY", "EU_EXPANDING", "GLOBAL_OPTIONAL"):
        ordered.extend(profile.get(group, []))
    return ordered
