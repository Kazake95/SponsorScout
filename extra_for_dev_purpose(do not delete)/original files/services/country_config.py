import json
from pathlib import Path


def load_country_profile():
    return json.loads(
        (Path(__file__).resolve().parent.parent / "data" / "country_profile.json").read_text(encoding="utf-8")
    )


def _dedupe(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def country_group(name: str):
    profile = load_country_profile()
    return list(profile.get(name, []))


def eu_countries(include_expanding: bool = True):
    profile = load_country_profile()
    groups = ["EU_PRIORITY", "EU_SECONDARY"]
    if include_expanding:
        groups.append("EU_EXPANDING")
    ordered = []
    for group in groups:
        ordered.extend(profile.get(group, []))
    return _dedupe(ordered)


def ordered_countries():
    """Return the curated EU-priority country order, plus any additional
    countries that actually appear in the loaded company registries.

    The curated groups (EU_PRIORITY / EU_SECONDARY / EU_EXPANDING /
    GLOBAL_OPTIONAL) keep their hand-tuned order at the front. Any country
    found in the CSV registry data that isn't already covered by those
    groups is appended afterwards (alphabetically), so new countries added
    via CSV automatically become available as a search filter without
    needing to edit ``country_profile.json``.
    """
    profile = load_country_profile()
    ordered = []
    for group in ("EU_PRIORITY", "EU_SECONDARY", "EU_EXPANDING", "GLOBAL_OPTIONAL"):
        ordered.extend(profile.get(group, []))

    seen = {c.lower() for c in ordered}

    try:
        from sponsorscout.services.registry_loader import load_seed_registry
        registry_countries = {
            (c.get("country") or "").strip()
            for c in load_seed_registry()
        }
    except Exception:
        registry_countries = set()

    extras = sorted(
        c for c in registry_countries
        if c and c.lower() not in seen
    )
    ordered.extend(extras)

    return ordered
