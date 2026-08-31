"""Shared constants and tiny helpers for the scanning package.

Extracted from ats_portal_scannerv5.py / career_portal_scanner_v7.py.
The 35-column output schema and 15-column scan-log schema are the contract
both scanners emit; keeping them in one place avoids drift.
"""

import re
from html import unescape
from urllib.parse import urlparse

OUTPUT_FIELDS = [
    "Company Name", "Seed Name", "Source Type", "Hiring Company",
    "Target Country", "Scope Policy", "Industry Type",
    "Sponsorship History Score", "English Friendly Score", "Remote Score",
    "Job Title", "Raw Job Title", "Job Location", "Raw Location", "Job Type",
    "Job URL", "Canonical Job ID", "Provider", "Extraction Method",
    "EU Blue Card", "Blue Card Evidence", "Relocation/Visa Support",
    "Location Source", "URL Type", "Visa Sponsorship", "Relocation Support",
    "Relocation Required", "Support Confidence", "Support Evidence",
    "Support Evidence URL", "Support Evidence Type", "Record Status",
    "Quarantine Reason", "Run ID", "Scanned At",
]

LOG_FIELDS = [
    "Run ID", "Seed Name", "Company", "Source Type", "Target Country", "Status",
    "Provider", "Jobs Found", "Quarantined", "Duplicates", "Rejected Scope",
    "Error", "Diagnostics", "Duration Sec", "Seed URL",
]


def clean(value):
    """Unescape, fix mojibake, unwrap markdown links, and collapse whitespace."""
    value = unescape(str(value or ""))
    value = value.replace("\ufeff", "")
    match = re.fullmatch(
        r"\[[^\]]*\]\((https?://[^)]+)\)",
        value.strip(),
    )
    if match:
        value = match.group(1)
    if any(x in value for x in ("\ufffd",)):
        try:
            value = value.encode("latin1").decode("utf-8")
        except (UnicodeError, UnicodeEncodeError):
            pass
    return re.sub(r"\s+", " ", value).strip()


def host_of(url):
    return urlparse(url).netloc.lower().split(":")[0]