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


def host_workers_limits() -> tuple[int, int]:
    """Return ``(cpu_count, total_ram_bytes)`` for this machine.

    RAM is read via ``GlobalMemoryStatusEx`` on Windows and ``sysconf`` on
    POSIX; when neither works (exotic platform / sandbox) a conservative
    8 GiB is assumed so the pool sizing stays *small* rather than optimistic.
    """
    import os

    cpu = os.cpu_count() or 2

    ram = 0
    try:
        if os.name == "nt":
            import ctypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                ram = int(stat.ullTotalPhys)
        else:
            ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except Exception:
        ram = 0

    if ram <= 0:
        ram = 8 * 1024 ** 3
    return cpu, ram


def recommended_workers(kind: str = "browser") -> int:
    """Concurrency level suited to *this* machine, not to a dev workstation.

    Each Playwright Chromium instance costs roughly 150-400 MB resident, so the
    previously hard-coded pools (3 concurrent browsers, 6 concurrent detail
    fetches) can exhaust the RAM of an 8 GB laptop and stall the whole OS —
    exactly the "scanning freezes my system" failure mode.

    ``kind``:
      * ``"browser"`` — concurrent browser contexts for the career crawl.
      * ``"http"``    — concurrent lightweight HTTP detail fetches.

    Returned values are always >= 1 and deliberately conservative; the scans
    stay correct at any concurrency, they are merely slower.
    """
    cpu, ram = host_workers_limits()
    if kind == "http":
        if ram < 6 * 1024 ** 3:
            return 3 if cpu >= 2 else 2
        return max(2, min(cpu * 2, 8))
    # browser contexts: the heavy case
    if ram < 6 * 1024 ** 3 or cpu <= 2:
        return 1
    if cpu <= 4:
        return 2
    return max(2, min(cpu // 2, 4))


# Lean Chromium flags.  ``--blink-settings=imagesEnabled=false`` alone removes
# the bulk of the download/render work on image-heavy career pages, and the
# remaining flags stop background networking that costs CPU and bandwidth
# without contributing a single job row.
BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-http2",
    "--ignore-certificate-errors",
    "--blink-settings=imagesEnabled=false",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-client-side-phishing-detection",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-gpu",
    "--disable-sync",
    "--disable-translate",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-first-run",
]


def host_of(url):
    return urlparse(url).netloc.lower().split(":")[0]