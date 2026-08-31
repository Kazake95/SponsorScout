from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sponsorscout.services.country_config import load_country_profile


@dataclass(frozen=True)
class SearchObjective:
    key: str
    label: str
    description: str
    min_match_score: int = 0
    min_sponsorship_score: int = 0
    allowed_countries: tuple[str, ...] = ()
    allowed_remote_types: tuple[str, ...] = ()
    require_blue_card: bool = False
    require_relocation: bool = False

    @property
    def is_strict(self) -> bool:
        return any(
            (
                self.min_match_score,
                self.min_sponsorship_score,
                self.allowed_countries,
                self.allowed_remote_types,
                self.require_blue_card,
                self.require_relocation,
            )
        )


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        item = (item or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered)


def _eu_countries() -> tuple[str, ...]:
    profile = load_country_profile()
    countries: list[str] = []
    for group in ("EU_PRIORITY", "EU_SECONDARY", "EU_EXPANDING"):
        countries.extend(profile.get(group, []))
    return _dedupe(countries)


EU_COUNTRIES = _eu_countries()


SEARCH_OBJECTIVES: dict[str, SearchObjective] = {
    "balanced": SearchObjective(
        key="balanced",
        label="Balanced",
        description="Show the full dataset and rank by trust, freshness and fit.",
    ),
    "strict_quality": SearchObjective(
        key="strict_quality",
        label="Strict quality",
        description="Prioritise strong EU fit, sponsorship signals and match score.",
        min_match_score=35,
        min_sponsorship_score=40,
        allowed_countries=EU_COUNTRIES,
        allowed_remote_types=("remote_eu", "remote_emea"),
    ),
    "visa_sponsor": SearchObjective(
        key="visa_sponsor",
        label="Visa sponsor",
        description="Bias towards stronger sponsorship / relocation likelihood.",
        min_match_score=25,
        min_sponsorship_score=60,
        allowed_countries=EU_COUNTRIES,
        allowed_remote_types=("remote_eu", "remote_emea"),
    ),
    "local_eu": SearchObjective(
        key="local_eu",
        label="Local EU",
        description="Keep roles in EU countries or EU/EMEA remote roles.",
        min_match_score=25,
        allowed_countries=EU_COUNTRIES,
        allowed_remote_types=("remote_eu", "remote_emea", "hybrid"),
    ),
    "remote_emea": SearchObjective(
        key="remote_emea",
        label="Remote EMEA",
        description="Focus on EU/EMEA remote roles only.",
        min_match_score=30,
        allowed_remote_types=("remote_eu", "remote_emea"),
    ),
    "blue_card_focus": SearchObjective(
        key="blue_card_focus",
        label="Blue Card focus",
        description="Prioritise roles with explicit EU Blue Card support.",
        min_match_score=25,
        min_sponsorship_score=30,
        allowed_countries=EU_COUNTRIES,
        allowed_remote_types=("remote_eu", "remote_emea"),
        require_blue_card=True,
    ),
}

OBJECTIVE_ORDER = (
    "balanced",
    "strict_quality",
    "visa_sponsor",
    "local_eu",
    "remote_emea",
    "blue_card_focus",
)


def normalize_objective(value: str | None) -> str:
    """Map a label or key to a canonical objective key."""
    raw = (value or "").strip().lower()
    if not raw:
        return "balanced"

    normalized = raw.replace(" ", "_").replace("-", "_")
    for key, obj in SEARCH_OBJECTIVES.items():
        if normalized in {key.lower(), obj.label.lower().replace(" ", "_")}:
            return key
    # tolerate translated / user-entered labels by exact label comparison
    for key, obj in SEARCH_OBJECTIVES.items():
        if raw == obj.label.lower():
            return key
    return "balanced"


def get_search_objective(value: str | None) -> SearchObjective:
    """Return the SearchObjective for a label/key; falls back to Balanced."""
    return SEARCH_OBJECTIVES.get(normalize_objective(value), SEARCH_OBJECTIVES["balanced"])


def available_search_objective_labels() -> list[str]:
    return [SEARCH_OBJECTIVES[key].label for key in OBJECTIVE_ORDER]


def available_search_objectives() -> list[SearchObjective]:
    return [SEARCH_OBJECTIVES[key] for key in OBJECTIVE_ORDER]
