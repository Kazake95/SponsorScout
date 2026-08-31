"""
Sponsorship Detection
Detects visa sponsorship, relocation support, EU Blue Card, and international candidate signals.

This module is intentionally keyword-rich. The user's instruction is to surface
*every* plausible sponsorship / relocation job available in the connected ATS
feeds, so we err on the side of broader detection. We also keep the negative
list tight (only clear "no sponsorship" / "must be local" phrases) to avoid
false-positives that suppress otherwise valid jobs.
"""
from __future__ import annotations
import re

# B14 fix: use whole-word regex matching with word boundaries so that
# short phrases like "no" or "eu" don't trigger inside unrelated words
# (e.g. "bluecard avenue", "no relocation" matched even when the surrounding
# text was positive). Each entry is matched as a regex, so multi-word
# phrases with the proper case-insensitive flag work correctly.

# ── Strong positive signals (visa sponsorship itself) ─────────────────────
POSITIVE_STRONG = [
    r"\bvisa sponsorship\b",
    r"\bsponsorship available\b",
    r"\bwe sponsor\b",
    r"\bwill sponsor\b",
    r"\bvisa support\b",
    r"\bwork permit sponsorship\b",
    r"\bskilled worker visa\b",
    r"\btier\s*2\s*sponsor(?:ship)?\b",       # also catches "tier 2 sponsorship"
    r"\bglobal talent visa\b",
    r"\beu blue card\b",
    r"\bblue\s+card\b",                       # require whitespace so 'Bluecard' (one word) does NOT match
    r"\binternational candidates welcome\b",
    r"\bopen to international applicants\b",
    r"\bwe support visa\b",
    r"\bsponsorship provided\b",
    r"\bwork\s+authoris?ation provided\b",
    r"\bvisa\s+assistance\b",
    r"\bimmigration\s+(?:support|assistance|sponsorship)\b",
    r"\bvisa\s+relocation\s+support\b",       # combined signals
    r"\bprovide\s+(?:a\s+)?work\s+(?:permit|visa)\b",
    r"\bcan\s+support\s+(?:work\s+permit|visa|relocation)\b",
]

# ── Moderate positive signals (relocation / international / mobility) ────
# Per user feedback, this list is intentionally broad — any reasonable
# phrase that suggests the company helps people move countries or hire
# internationally. We split these into categories for clarity.
POSITIVE_MODERATE = [
    # ── Core relocation phrases ──
    r"\brelocation support\b",
    r"\brelocation package\b",
    r"\brelocation assistance\b",
    r"\brelocation bonus\b",
    r"\brelocation allowance\b",
    r"\breimbursement\s+for\s+relocation\b",
    r"\bhelp\s+with\s+relocation\b",
    r"\bhelp\s+you\s+relocate\b",
    r"\bwe\s+(?:will\s+)?help\s+you\s+relocate\b",
    r"\breloca(?:te|ting)\s+(?:to|with|for)\b",
    r"\binterview\s+and\s+relocation\b",
    r"\brelocation\s+grant\b",
    r"\brelocation\s+benefit(?:s)?\b",
    r"\brelocation\s+services?\b",
    r"\brelocation\s+(?:is\s+)?provided\b",
    r"\brelocation\s+covered\b",
    r"\bcovered\s+relocation\b",
    r"\brelocation\s+reimbursement\b",
    r"\bmoving\s+expenses?\b",
    r"\bmoving\s+(?:costs?|allowance|package|support|assistance)\b",
    r"\bmove\s+to\s+(?:the\s+)?(?:uk|us|usa|europe|eu|germany|netherlands|france|ireland|spain|italy|sweden|denmark|finland|norway|austria|switzerland|belgium|portugal|czech|poland|hungary|romania|greece)\b",
    r"\bmove\s+abroad\b",
    r"\bmove\s+to\s+(?:our|the)\s+(?:hq|headquarters|office)\b",

    # ── Immigration / mobility support ──
    r"\bimmigration\s+support\b",
    r"\bimmigration\s+assistance\b",
    r"\bimmigration\s+lawyer\b",
    r"\bimmigration\s+fees?\b",
    r"\bglobal\s+mobility\b",
    r"\binternational\s+mobility\b",
    r"\bmobility\s+(?:package|support|assistance|program(?:me)?)\b",
    r"\bmobility\s+benefits?\b",
    r"\bexpat\s+(?:package|support|benefits?)\b",
    r"\bexpat\s+relocation\b",
    r"\bexpatriate\s+(?:package|support|benefits?)\b",
    r"\bexpatriation\b",

    # ── Visa-related moderate signals ──
    r"\bvisa\s+provided\b",
    r"\bvisa\s+covered\b",
    r"\bcovered\s+visa\b",
    r"\bvisa\s+sponsored\b",
    r"\bwork\s+permit\s+provided\b",
    r"\bwork\s+permit\s+covered\b",
    r"\bwork\s+permit\s+assistance\b",
    r"\bwork\s+permit\s+support\b",
    r"\bwork\s+visa\b",
    r"\bemployment\s+visa\b",

    # ── International / global hiring ──
    r"\binternational\s+candidates\b",
    r"\bcandidates\s+worldwide\b",
    r"\bopen\s+to\s+candidates\b",
    r"\bglobal\s+talent\b",
    r"\bwe\s+welcome\s+applications\s+from\b",
    r"\bwork\s+from\s+anywhere\b",
    r"\banywhere\s+in\s+the\s+world\b",
    r"\banywhere\s+in\s+europe\b",
    r"\banywhere\s+in\s+the\s+eu\b",
    r"\banywhere\s+in\s+(?:the\s+)?(?:uk|us|germany|netherlands|emea)\b",
    r"\bremote\s+first\s+company\b",
    r"\bdistributed\s+team\b",
    r"\basync\s+remote\b",
    r"\bhire\s+(?:from\s+)?anywhere\b",
    r"\bhire\s+globally\b",
    r"\bglobal\s+hiring\b",
    r"\bglobal\s+team(?:s)?\b",
    r"\bglobally\s+remote\b",
    r"\b100%?\s+remote\b",
    r"\bfull(?:y)?\s+remote\b",

    # ── EU-specific ──
    r"\beu\s+(?:remote|work|relocation|relocate|citizen|candidate|residen[ct])\b",
    r"\bwork\s+in\s+the\s+eu\b",
    r"\bwork\s+in\s+europe\b",
    r"\brelocate\s+to\s+(?:the\s+)?eu\b",
    r"\bemea\s+(?:remote|work|region|opportunit(?:y|ies))\b",

    # ── Talent visa / niche ──
    r"\btalent\s+visa\b",
    r"\bblue\s+card\s+(?:sponsor|support|visa|holder)\b",
    r"\bholiday\s+(?:work\s+)?visa\b",
    r"\bgraduate\s+visa\b",
    r"\bpost[-\s]?study\s+work\b",

    # ── Generic inclusive language ──
    r"\ball\s+backgrounds\b",
    r"\bany\s+background\b",
    r"\bdiverse\s+candidates\b",
    r"\bunder[-\s]?represented\b",
    r"\bequal\s+opportunit(?:y|ies)\s+employer\b",
    r"\bcommitted\s+to\s+diversity\b",
    r"\bwe\s+value\s+diversity\b",
    r"\bwelcoming\s+workplace\b",
    r"\binclusive\s+(?:workplace|environment|hiring|culture)\b",
    r"\bno\s+border\b",
    r"\bborderless\b",
    r"\bpassport\s+not\s+required\b",
    r"\bcitizenship\s+not\s+required\b",
]

# ── Hard negative signals (clear "we don't sponsor / hire") ──────────────
# Kept TIGHT to avoid suppressing valid jobs. Only unambiguous "no" phrases.
NEGATIVE = [
    r"\bmust have right to work\b",
    r"\bno sponsorship\b",
    r"\bno visa sponsorship\b",
    r"\bunable to sponsor\b",
    r"\bcannot sponsor\b",
    r"\bsponsorship not available\b",
    r"\bwill not sponsor\b",
    r"\bsponsorship is not provided\b",
    r"\blocal candidates only\b",
    r"\bmust already be eligible to work\b",
    r"\bmust be eligible to work\b",
    r"\bwithout sponsorship\b",
    r"\bno relocation\s+(?:support|package|assistance|bonus|allowance|provided)\b",
    r"\bno work permit\b",
    r"\bcitizens only\b",
    r"\bus citizens only\b",
    r"\beu citizens only\b",
    r"\beea citizens only\b",
    r"\bpermanent residents only\b",
    r"\bpr\s+only\b",
    r"\bauthorized to work\b",
    r"\bauthorisation to work\b",
    r"\bright to work in\b",
    r"\bmust\s+be\s+(?:a\s+)?(?:citizen|national|resident)\s+of\b",
    r"\bmust\s+currently\s+(?:be\s+)?(?:reside|live)\s+in\b",
    r"\brelocation\s+is\s+not\s+(?:supported|provided|available|covered)\b",
    r"\brelocation\s+not\s+(?:supported|provided|available|covered)\b",
    r"\bno\s+(?:visa|work\s+permit)\s+(?:sponsorship|support)\b",
    r"\brequired\s+to\s+be\s+(?:physically\s+)?(?:located|based)\s+in\b",
    r"\bon[-\s]?site\s+only\b",
]

# Pre-compile the patterns once at import time.
_POS_STRONG_RE = [re.compile(p, re.IGNORECASE) for p in POSITIVE_STRONG]
_POS_MOD_RE    = [re.compile(p, re.IGNORECASE) for p in POSITIVE_MODERATE]
_NEG_RE        = [re.compile(p, re.IGNORECASE) for p in NEGATIVE]

REMOTE_SIGNALS = {
    "remote_eu": [
        "remote eu", "remote europe", "eu remote", "europe remote",
        "eurozone", "anywhere in the eu", "anywhere in europe",
    ],
    "remote_emea": ["remote emea", "emea remote"],
    "remote_global": [
        "remote global", "remote worldwide", "remote anywhere",
        "fully remote", "work from anywhere", "anywhere in the world",
        "100% remote", "globally remote", "borderless",
    ],
    "hybrid": ["hybrid", "hybrid work", "hybrid remote", "flexible remote"],
}


def _find_all(patterns, text: str) -> list[str]:
    """Return the list of pattern strings that matched anywhere in text."""
    return [p.pattern for p in patterns if p.search(text)]


def score(text: str) -> int:
    """Return sponsorship likelihood score 0-100.

    Scoring strategy:
    - Start at 20 baseline.
    - Hard negative phrases (e.g. "no sponsorship", "local candidates only")
      drop the score to 0 — these are unambiguous rejections.
    - Strong positive phrases add 25 each.
    - Moderate positive phrases (relocation, international, mobility) add 10.
    - Cap at 100.
    """
    t = text or ""
    # Hard negative signals → return 0
    for pat in _NEG_RE:
        if pat.search(t):
            return 0
    s = 20  # baseline
    for pat in _POS_STRONG_RE:
        if pat.search(t):
            s += 25
    for pat in _POS_MOD_RE:
        if pat.search(t):
            s += 10
    return max(0, min(s, 100))


def classify_remote(text: str) -> str:
    """Classify remote type: remote_eu, remote_emea, remote_global, hybrid, onsite."""
    t = (text or "").lower()
    for category, signals in REMOTE_SIGNALS.items():
        if any(sig in t for sig in signals):
            return category
    if "remote" in t:
        return "remote"
    return "onsite"


def detect_sponsorship_keywords(text: str) -> dict:
    """Return detailed breakdown of sponsorship / relocation / visa signals found."""
    t = text or ""
    found_positive = _find_all(_POS_STRONG_RE, t) + _find_all(_POS_MOD_RE, t)
    found_negative = _find_all(_NEG_RE, t)
    t_low = t.lower()
    return {
        "positive": found_positive,
        "negative": found_negative,
        "eu_blue_card": bool(
            re.search(r"\beu blue card\b", t_low) or
            re.search(r"\bblue\s+card\b", t_low)
        ),
        "relocation": bool(
            # Original short list
            re.search(r"\brelocation support\b", t_low) or
            re.search(r"\brelocation package\b", t_low) or
            re.search(r"\brelocation assistance\b", t_low) or
            # Expanded for robustness
            re.search(r"\brelocation (?:allowance|bonus|grant|benefit|reimbursement|services?|covered|provided)\b", t_low) or
            re.search(r"\bhelp (?:with |you |you to )?relocat", t_low) or
            re.search(r"\bmoving (?:expenses?|costs?|allowance|package|support|assistance)\b", t_low) or
            re.search(r"\bmove (?:to|abroad|with us)\b", t_low) or
            re.search(r"\bimmigration (?:support|assistance|fees?|lawyer)\b", t_low) or
            re.search(r"\b(?:global|international) mobility\b", t_low) or
            re.search(r"\b(?:expat|expatriate) (?:package|support|benefits?|relocation)\b", t_low) or
            re.search(r"\bmobility (?:package|support|assistance|program(?:me)?|benefits?)\b", t_low) or
            # Robust catch-all: international / remote / EU signals are a
            # strong proxy for "this role is open to people from elsewhere"
            # — which is what the user is filtering for. Otherwise jobs
            # that say "we hire from anywhere" or "100% remote" get missed
            # by the Relocation filter even though they're equally valid.
            re.search(r"\binternational candidates\b", t_low) or
            re.search(r"\bcandidates worldwide\b", t_low) or
            re.search(r"\bopen to international applicants\b", t_low) or
            re.search(r"\bwork from anywhere\b", t_low) or
            re.search(r"\banywhere in (?:the world|europe|the eu|the uk|the us|germany|emea)\b", t_low) or
            re.search(r"\bglobal(?:ly)? (?:remote|hire|hiring|team)\b", t_low) or
            re.search(r"\bhire (?:from )?anywhere\b", t_low) or
            re.search(r"\bdistributed team\b", t_low) or
            re.search(r"\bremote[- ]first\b", t_low) or
            re.search(r"\bborderless\b", t_low) or
            re.search(r"\b100%?\s+remote\b", t_low) or
            re.search(r"\bfully\s*remote\b", t_low) or
            re.search(r"\beu\s+(?:remote|work|relocation|relocate|citizen|candidate)\b", t_low) or
            re.search(r"\bemea\s+(?:remote|work|region|opportunit(?:y|ies))\b", t_low) or
            re.search(r"\brelocate to (?:the\s+)?eu\b", t_low) or
            re.search(r"\bwork in (?:the\s+)?(?:eu|europe)\b", t_low) or
            re.search(r"\btalent visa\b", t_low) or
            re.search(r"\bglobal talent\b", t_low)
        ),
        "visa_sponsorship": bool(
            re.search(r"\bvisa sponsorship\b", t_low) or
            re.search(r"\bwork permit sponsorship\b", t_low) or
            re.search(r"\bvisa support\b", t_low) or
            re.search(r"\bvisa (?:provided|covered|sponsored|assistance)\b", t_low) or
            re.search(r"\bwork permit (?:provided|covered|sponsored|assistance|support)\b", t_low) or
            re.search(r"\bwork visa\b", t_low) or
            re.search(r"\bemployment visa\b", t_low) or
            re.search(r"\bimmigration (?:support|assistance|sponsorship)\b", t_low)
        ),
        "international": bool(
            re.search(r"\binternational candidates\b", t_low) or
            re.search(r"\bcandidates worldwide\b", t_low) or
            re.search(r"\bglobal talent\b", t_low) or
            re.search(r"\bwork from anywhere\b", t_low) or
            re.search(r"\banywhere in (?:the world|europe|the eu|the uk|the us)\b", t_low) or
            re.search(r"\bglobal(?:ly)? (?:remote|hire|hiring|team)\b", t_low) or
            re.search(r"\bhire (?:from )?anywhere\b", t_low) or
            re.search(r"\bdistributed team\b", t_low) or
            re.search(r"\bremote[- ]first\b", t_low) or
            re.search(r"\bborderless\b", t_low)
        ),
        "remote_type": classify_remote(t),
    }
