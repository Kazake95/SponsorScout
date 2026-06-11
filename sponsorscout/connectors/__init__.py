"""Lazy-loaded connector registry.

Each connector class is imported and instantiated only when first requested,
keeping module import time fast and avoiding eager HTTP-client creation
across all 18 ATS backends.
"""
from __future__ import annotations

from typing import Optional

# Maps ATS type name → (module path, class name).  The first access triggers
# the import + instantiation; subsequent accesses return the cached instance.
_CONNECTOR_REGISTRY: dict[str, tuple[str, str]] = {
    "greenhouse":       ("sponsorscout.connectors.greenhouse",         "GreenhouseConnector"),
    "lever":            ("sponsorscout.connectors.lever",              "LeverConnector"),
    "workable":         ("sponsorscout.connectors.workable",           "WorkableConnector"),
    "official_careers": ("sponsorscout.connectors.official_careers",   "OfficialCareersConnector"),
    "teamtailor":       ("sponsorscout.connectors.teamtailor",         "TeamtailorConnector"),
    "personio":         ("sponsorscout.connectors.personio",           "PersonioConnector"),
    "smartrecruiters":  ("sponsorscout.connectors.smartrecruiters",    "SmartRecruitersConnector"),
    "workday":          ("sponsorscout.connectors.workday",            "WorkdayConnector"),
    "bamboohr":         ("sponsorscout.connectors.bamboohr",           "BambooHRConnector"),
    "recruitee":        ("sponsorscout.connectors.recruitee",          "RecruiteeConnector"),
    "ashby":            ("sponsorscout.connectors.ashby",              "AshbyConnector"),
    "jobvite":          ("sponsorscout.connectors.jobvite",            "JobviteConnector"),
    "icims":            ("sponsorscout.connectors.icims",              "ICIMSConnector"),
    "homerun":          ("sponsorscout.connectors.homerun",            "HomerunConnector"),
    "freshteam":        ("sponsorscout.connectors.freshteam",          "FreshteamConnector"),
    "breezy":           ("sponsorscout.connectors.breezy",             "BreezyConnector"),
    "welcometothejungle": ("sponsorscout.connectors.welcometothejungle", "WTTJConnector"),
    "manatal":          ("sponsorscout.connectors.manatal",            "ManatalConnector"),
}

# Cached instances: ATS type name → instantiated connector object.
_instances: dict[str, object] = {}


def get_connector(ats_type: str):
    """Return the singleton connector for *ats_type*, or ``None``."""
    key = (ats_type or "").lower()
    if key in _instances:
        return _instances[key]
    entry = _CONNECTOR_REGISTRY.get(key)
    if entry is None:
        return None
    module_path, class_name = entry
    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    instance = cls()
    _instances[key] = instance
    return instance


def get_connector_names() -> list[str]:
    """Return the list of registered ATS type names."""
    return list(_CONNECTOR_REGISTRY)
