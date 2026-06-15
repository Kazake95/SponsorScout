import re
from typing import Tuple

def detect_ats_from_links(links: list[str]) -> Tuple[str, str]:
    """
    Analyzes a list of URLs (typically extracted from a career page)
    to detect the underlying Applicant Tracking System (ATS) and extract its company token.

    Returns:
        Tuple[str, str]: (ats_type, ats_board_token). 
        Returns ("", "") if no known ATS is detected.
    """
    for url in links:
        # Greenhouse
        m = re.search(r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)", url)
        if m:
            return "greenhouse", m.group(1)

        # Lever
        m = re.search(r"(?:jobs|careers|api)\.lever\.co/(?:v0/postings/)?([^/?#]+)", url)
        if m:
            return "lever", m.group(1)

        # Ashby
        m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)", url)
        if m:
            return "ashby", m.group(1)

        # Workable
        m = re.search(r"apply\.workable\.com/([^/?#]+)", url)
        if m:
            return "workable", m.group(1)

        # Personio
        m = re.search(r"([a-zA-Z0-9_-]+)\.(?:jobs\.)?personio\.(?:com|de)", url)
        if m:
            return "personio", m.group(1)

        # Workday (returns tenant as token, we rely on the connector to figure out the site)
        m = re.search(r"([a-zA-Z0-9_-]+)(?:\.wd\d+)?\.myworkdayjobs\.com", url)
        if m:
            return "workday", m.group(1)

        # Teamtailor
        m = re.search(r"([a-zA-Z0-9_-]+)\.teamtailor\.com", url)
        if m:
            return "teamtailor", m.group(1)

        # SmartRecruiters
        m = re.search(r"jobs\.smartrecruiters\.com/([^/?#]+)", url)
        if m:
            return "smartrecruiters", m.group(1)

        # BambooHR
        m = re.search(r"([a-zA-Z0-9_-]+)\.bamboohr\.com", url)
        if m:
            return "bamboohr", m.group(1)

        # Recruitee
        m = re.search(r"([a-zA-Z0-9_-]+)\.recruitee\.com", url)
        if m:
            return "recruitee", m.group(1)

        # Jobvite
        m = re.search(r"jobs\.jobvite\.com/([^/?#]+)", url)
        if m:
            return "jobvite", m.group(1)

        # iCIMS
        m = re.search(r"([a-zA-Z0-9_-]+)\.icims\.com", url)
        if m:
            return "icims", m.group(1)

        # Breezy
        m = re.search(r"([a-zA-Z0-9_-]+)\.breezy\.hr", url)
        if m:
            return "breezy", m.group(1)

        # Freshteam
        m = re.search(r"([a-zA-Z0-9_-]+)\.freshteam\.com", url)
        if m:
            return "freshteam", m.group(1)

        # Homerun
        m = re.search(r"run\.homerun\.co/([^/?#]+)", url)
        if m:
            return "homerun", m.group(1)

        # Welcome to the jungle
        m = re.search(r"welcometothejungle\.com/companies/([^/?#]+)", url)
        if m:
            return "welcometothejungle", m.group(1)

        # Manatal
        m = re.search(r"([a-zA-Z0-9_-]+)\.manatal\.com", url)
        if m:
            return "manatal", m.group(1)

    return "", ""
