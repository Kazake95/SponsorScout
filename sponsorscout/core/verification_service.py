"""
Freshness verification service.
Checks whether job URLs still resolve to active job pages.
Uses lightweight HTTP (no browser required).
"""
from __future__ import annotations
from sponsorscout.services.browser_fetcher import fetch_rendered_html
from sponsorscout.core.verification import mark_expired, mark_verified

# Phrases that reliably indicate a job is no longer active
DEAD_PHRASES = [
    "this job is no longer available",
    "job no longer available",
    "position has been filled",
    "this position is no longer",
    "vacancy has been filled",
    "application period has ended",
    "listing has expired",
    "job listing expired",
    "no longer accepting",
    "page not found",
    "404 not found",
    "sorry, this job",
    "job has been removed",
    "this role has been filled",
]


def verify_url_active(url: str) -> bool:
    """Return True if job URL appears to still be live."""
    if not url:
        return False
    result = fetch_rendered_html(url)
    status = result.get("status", 0)

    # Hard 404/410/gone
    if status in (404, 410, 403, 0):
        return False

    html_lower = (result.get("html") or "").lower()
    title_lower = (result.get("title") or "").lower()
    combined = html_lower[:5000] + " " + title_lower

    for phrase in DEAD_PHRASES:
        if phrase in combined:
            return False

    return True


def verify_job(job: dict) -> dict:
    """Verify a job dict and return it with updated verified_active / is_expired."""
    if verify_url_active(job.get("url", "")):
        return mark_verified(job)
    return mark_expired(job)
