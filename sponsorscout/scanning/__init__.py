"""SponsorScout scanning engine.

Lifted from the two reference algorithm scripts:
  - ats_portal_scannerv5.py            -> Sponsorscout.scanning.ats
  - career_portal_scanner_v7.py        -> sponsorscout.scanning.career

Shared JD-evidence classification lives in :mod:`jd_support`, and the common
output/schema contract in :mod:`common`.  The high-level orchestrator that
both the desktop app and the CLI use is :mod:`pipeline`.
"""