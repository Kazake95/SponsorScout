"""
Derive a job's actual country from the raw location string returned by ATS APIs.

ATS APIs return strings like "São Paulo", "Berlin, DE", "New York, NY",
"Amsterdam, North Holland, Netherlands", "Remote - EU", etc.
This module maps all such strings to a canonical country name for filtering.
"""
from __future__ import annotations
import re

# ── ISO 3166-1 alpha-2 → Country ─────────────────────────────────────────────
ISO2_TO_COUNTRY: dict[str, str] = {
    "af": "Afghanistan", "al": "Albania", "dz": "Algeria", "ar": "Argentina",
    "au": "Australia", "at": "Austria", "be": "Belgium", "br": "Brazil",
    "bg": "Bulgaria", "ca": "Canada", "cl": "Chile", "cn": "China",
    "co": "Colombia", "hr": "Croatia", "cy": "Cyprus", "cz": "Czech Republic",
    "dk": "Denmark", "ee": "Estonia", "fi": "Finland", "fr": "France",
    "de": "Germany", "gr": "Greece", "hu": "Hungary", "in": "India",
    "id": "Indonesia", "ie": "Ireland", "il": "Israel", "it": "Italy",
    "jp": "Japan", "kr": "South Korea", "lv": "Latvia", "lt": "Lithuania",
    "lu": "Luxembourg", "mt": "Malta", "mx": "Mexico", "nl": "Netherlands",
    "nz": "New Zealand", "no": "Norway", "pl": "Poland", "pt": "Portugal",
    "ro": "Romania", "ru": "Russia", "rs": "Serbia", "sg": "Singapore",
    "sk": "Slovakia", "si": "Slovenia", "za": "South Africa", "es": "Spain",
    "se": "Sweden", "ch": "Switzerland", "tw": "Taiwan", "th": "Thailand",
    "tr": "Turkey", "ua": "Ukraine", "ae": "United Arab Emirates",
    "gb": "United Kingdom", "uk": "United Kingdom",
    "us": "United States", "vn": "Vietnam",
}

# ── US states (both abbreviation and full name) ───────────────────────────────
US_STATES_ABBR: set[str] = {
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in",
    "ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
    "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn",
    "tx","ut","vt","va","wa","wv","wi","wy","dc",
}
US_STATES_FULL: set[str] = {
    "alabama","alaska","arizona","arkansas","california","colorado","connecticut",
    "delaware","florida","georgia","hawaii","idaho","illinois","indiana","iowa",
    "kansas","kentucky","louisiana","maine","maryland","massachusetts","michigan",
    "minnesota","mississippi","missouri","montana","nebraska","nevada",
    "new hampshire","new jersey","new mexico","new york","north carolina",
    "north dakota","ohio","oklahoma","oregon","pennsylvania","rhode island",
    "south carolina","south dakota","tennessee","texas","utah","vermont",
    "virginia","washington","west virginia","wisconsin","wyoming",
    "district of columbia",
}

# ── Canadian provinces (full name only — abbrevs conflict with ISO2) ──────────
CA_PROVINCES_FULL: set[str] = {
    "ontario","quebec","british columbia","alberta","manitoba","saskatchewan",
    "nova scotia","new brunswick","newfoundland","prince edward island",
    "northwest territories","nunavut","yukon",
}

# ── Full country names (lower) → canonical ───────────────────────────────────
COUNTRY_NAMES: dict[str, str] = {
    "afghanistan": "Afghanistan", "albania": "Albania", "algeria": "Algeria",
    "argentina": "Argentina", "australia": "Australia", "austria": "Austria",
    "belgium": "Belgium", "brazil": "Brazil", "bulgaria": "Bulgaria",
    "canada": "Canada", "chile": "Chile", "china": "China",
    "colombia": "Colombia", "croatia": "Croatia", "cyprus": "Cyprus",
    "czech republic": "Czech Republic", "czechia": "Czech Republic",
    "denmark": "Denmark", "estonia": "Estonia", "finland": "Finland",
    "france": "France", "germany": "Germany", "deutschland": "Germany",
    "greece": "Greece", "hungary": "Hungary", "india": "India",
    "indonesia": "Indonesia", "ireland": "Ireland", "israel": "Israel",
    "italy": "Italy", "japan": "Japan", "south korea": "South Korea",
    "latvia": "Latvia", "lithuania": "Lithuania", "luxembourg": "Luxembourg",
    "malta": "Malta", "mexico": "Mexico", "méxico": "Mexico",
    "netherlands": "Netherlands", "the netherlands": "Netherlands",
    "new zealand": "New Zealand", "norway": "Norway", "poland": "Poland",
    "portugal": "Portugal", "romania": "Romania", "russia": "Russia",
    "serbia": "Serbia", "singapore": "Singapore", "slovakia": "Slovakia",
    "slovenia": "Slovenia", "south africa": "South Africa", "spain": "Spain",
    "españa": "Spain", "sweden": "Sweden", "switzerland": "Switzerland",
    "taiwan": "Taiwan", "thailand": "Thailand", "turkey": "Turkey",
    "ukraine": "Ukraine", "united arab emirates": "United Arab Emirates",
    "uae": "United Arab Emirates",
    "united kingdom": "United Kingdom", "uk": "United Kingdom",
    "great britain": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom",
    "united states": "United States", "usa": "United States",
    "u.s.a.": "United States", "u.s.": "United States",
    "america": "United States",
    "vietnam": "Vietnam",
}

# ── City → Country ────────────────────────────────────────────────────────────
CITY_TO_COUNTRY: dict[str, str] = {
    # Netherlands
    "amsterdam": "Netherlands", "rotterdam": "Netherlands",
    "the hague": "Netherlands", "den haag": "Netherlands",
    "utrecht": "Netherlands", "eindhoven": "Netherlands",
    "haarlem": "Netherlands", "delft": "Netherlands",
    "groningen": "Netherlands", "nijmegen": "Netherlands",
    "tilburg": "Netherlands", "breda": "Netherlands",

    # Germany
    "berlin": "Germany", "munich": "Germany", "münchen": "Germany",
    "hamburg": "Germany", "frankfurt": "Germany", "frankfurt am main": "Germany",
    "cologne": "Germany", "köln": "Germany", "koln": "Germany",
    "düsseldorf": "Germany", "dusseldorf": "Germany", "stuttgart": "Germany",
    "dortmund": "Germany", "nuremberg": "Germany", "nürnberg": "Germany",
    "nurnberg": "Germany", "dresden": "Germany", "leipzig": "Germany",
    "hannover": "Germany", "hanover": "Germany", "bonn": "Germany",
    "mannheim": "Germany", "karlsruhe": "Germany", "augsburg": "Germany",
    "wiesbaden": "Germany", "münster": "Germany", "munster": "Germany",
    "freiburg": "Germany", "kiel": "Germany", "mainz": "Germany",
    "heidelberg": "Germany", "essen": "Germany",

    # United Kingdom
    "london": "United Kingdom", "manchester": "United Kingdom",
    "birmingham": "United Kingdom", "edinburgh": "United Kingdom",
    "glasgow": "United Kingdom", "bristol": "United Kingdom",
    "leeds": "United Kingdom", "liverpool": "United Kingdom",
    "cambridge": "United Kingdom", "oxford": "United Kingdom",
    "sheffield": "United Kingdom", "newcastle": "United Kingdom",
    "nottingham": "United Kingdom", "cardiff": "United Kingdom",
    "belfast": "United Kingdom", "coventry": "United Kingdom",
    "brighton": "United Kingdom", "reading": "United Kingdom",

    # Sweden
    "stockholm": "Sweden", "gothenburg": "Sweden", "göteborg": "Sweden",
    "goteborg": "Sweden", "malmö": "Sweden", "malmo": "Sweden",
    "uppsala": "Sweden", "linköping": "Sweden", "linkoping": "Sweden",
    "örebro": "Sweden", "orebro": "Sweden", "lund": "Sweden",

    # Denmark
    "copenhagen": "Denmark", "københavn": "Denmark", "kobenhavn": "Denmark",
    "aarhus": "Denmark", "odense": "Denmark", "aalborg": "Denmark",

    # Finland
    "helsinki": "Finland", "espoo": "Finland", "tampere": "Finland",
    "oulu": "Finland", "turku": "Finland", "vantaa": "Finland",

    # Norway
    "oslo": "Norway", "bergen": "Norway", "trondheim": "Norway",
    "stavanger": "Norway", "kristiansand": "Norway",

    # France
    "paris": "France", "lyon": "France", "marseille": "France",
    "toulouse": "France", "bordeaux": "France", "nantes": "France",
    "lille": "France", "strasbourg": "France", "nice": "France",
    "rennes": "France", "grenoble": "France", "montpellier": "France",

    # Spain
    "madrid": "Spain", "barcelona": "Spain", "valencia": "Spain",
    "seville": "Spain", "sevilla": "Spain", "bilbao": "Spain",
    "málaga": "Spain", "malaga": "Spain", "zaragoza": "Spain",
    "palma": "Spain", "las palmas": "Spain",

    # Portugal
    "lisbon": "Portugal", "lisboa": "Portugal", "porto": "Portugal",
    "braga": "Portugal", "coimbra": "Portugal", "faro": "Portugal",
    "funchal": "Portugal",

    # Ireland
    "dublin": "Ireland", "cork": "Ireland", "galway": "Ireland",
    "limerick": "Ireland", "waterford": "Ireland",

    # Poland
    "warsaw": "Poland", "wrocław": "Poland", "wroclaw": "Poland",
    "kraków": "Poland", "krakow": "Poland", "gdańsk": "Poland",
    "gdansk": "Poland", "poznan": "Poland", "poznań": "Poland",
    "łódź": "Poland", "lodz": "Poland", "katowice": "Poland",
    "szczecin": "Poland", "lublin": "Poland",

    # Czech Republic
    "prague": "Czech Republic", "brno": "Czech Republic",
    "ostrava": "Czech Republic", "plzeň": "Czech Republic",
    "plzen": "Czech Republic", "liberec": "Czech Republic",

    # Romania
    "bucharest": "Romania", "cluj": "Romania", "cluj-napoca": "Romania",
    "timisoara": "Romania", "timișoara": "Romania", "iasi": "Romania",
    "brașov": "Romania", "brasov": "Romania",

    # Hungary
    "budapest": "Hungary", "debrecen": "Hungary", "pécs": "Hungary",

    # Austria
    "vienna": "Austria", "wien": "Austria", "graz": "Austria",
    "linz": "Austria", "salzburg": "Austria", "innsbruck": "Austria",

    # Switzerland
    "zurich": "Switzerland", "zürich": "Switzerland", "zurich": "Switzerland",
    "geneva": "Switzerland", "genève": "Switzerland", "geneve": "Switzerland",
    "bern": "Switzerland", "basel": "Switzerland", "lausanne": "Switzerland",

    # Belgium
    "brussels": "Belgium", "bruxelles": "Belgium", "brussel": "Belgium",
    "ghent": "Belgium", "gent": "Belgium", "antwerp": "Belgium",
    "antwerpen": "Belgium", "liège": "Belgium", "liege": "Belgium",
    "leuven": "Belgium",

    # Italy
    "rome": "Italy", "roma": "Italy", "milan": "Italy", "milano": "Italy",
    "turin": "Italy", "torino": "Italy", "florence": "Italy",
    "firenze": "Italy", "naples": "Italy", "napoli": "Italy",
    "bologna": "Italy", "venice": "Italy", "venezia": "Italy",
    "genoa": "Italy", "genova": "Italy", "palermo": "Italy",

    # Greece
    "athens": "Greece", "athen": "Greece", "thessaloniki": "Greece",

    # Baltic states
    "tallinn": "Estonia", "riga": "Latvia", "vilnius": "Lithuania",

    # Balkans
    "zagreb": "Croatia", "ljubljana": "Slovenia", "sarajevo": "Bosnia and Herzegovina",
    "belgrade": "Serbia", "beograd": "Serbia", "sofia": "Bulgaria",
    "skopje": "North Macedonia", "tirana": "Albania",

    # Nordics / small EU
    "luxembourg city": "Luxembourg", "valletta": "Malta",
    "nicosia": "Cyprus", "reykjavik": "Iceland",

    # Eastern Europe
    "kiev": "Ukraine", "kyiv": "Ukraine", "kharkiv": "Ukraine",
    "moscow": "Russia", "moskva": "Russia", "st. petersburg": "Russia",
    "saint petersburg": "Russia",
    "minsk": "Belarus", "chisinau": "Moldova",

    # Middle East
    "tel aviv": "Israel", "tel-aviv": "Israel", "tel aviv-yafo": "Israel",
    "jerusalem": "Israel", "haifa": "Israel", "herzliya": "Israel",
    "ramat gan": "Israel", "petah tikva": "Israel",
    "dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates",
    "sharjah": "United Arab Emirates",
    "riyadh": "Saudi Arabia", "jeddah": "Saudi Arabia",
    "doha": "Qatar", "kuwait city": "Kuwait", "manama": "Bahrain",
    "amman": "Jordan", "beirut": "Lebanon", "cairo": "Egypt",
    "istanbul": "Turkey", "ankara": "Turkey",

    # India
    "bangalore": "India", "bengaluru": "India", "mumbai": "India",
    "delhi": "India", "new delhi": "India", "hyderabad": "India",
    "pune": "India", "chennai": "India", "kolkata": "India",
    "gurgaon": "India", "gurugram": "India", "noida": "India",
    "ahmedabad": "India", "jaipur": "India",

    # Asia Pacific
    "singapore": "Singapore",
    "tokyo": "Japan", "osaka": "Japan", "kyoto": "Japan",
    "yokohama": "Japan", "nagoya": "Japan",
    "seoul": "South Korea", "busan": "South Korea",
    "beijing": "China", "shanghai": "China", "shenzhen": "China",
    "guangzhou": "China", "chengdu": "China", "hangzhou": "China",
    "hong kong": "Hong Kong",
    "taipei": "Taiwan",
    "sydney": "Australia", "melbourne": "Australia", "brisbane": "Australia",
    "perth": "Australia", "adelaide": "Australia", "canberra": "Australia",
    "auckland": "New Zealand", "wellington": "New Zealand",
    "kuala lumpur": "Malaysia", "kl": "Malaysia",
    "jakarta": "Indonesia", "bangkok": "Thailand",
    "ho chi minh": "Vietnam", "hanoi": "Vietnam",
    "manila": "Philippines",

    # Africa
    "johannesburg": "South Africa", "cape town": "South Africa",
    "durban": "South Africa", "pretoria": "South Africa",
    "nairobi": "Kenya", "lagos": "Nigeria", "accra": "Ghana",
    "casablanca": "Morocco", "cairo": "Egypt", "tunis": "Tunisia",

    # Canada
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada",
    "montréal": "Canada", "calgary": "Canada", "ottawa": "Canada",
    "edmonton": "Canada", "winnipeg": "Canada", "quebec city": "Canada",

    # United States — additional cities for state-abbrev conflict resolution
    "dover": "United States", "wilmington": "United States",
    "indianapolis": "United States", "fort wayne": "United States",
    "savannah": "United States", "augusta": "United States",
    "colorado springs": "United States", "boulder": "United States",
    "aurora": "United States", "fort collins": "United States",
    "montgomery": "United States", "huntsville": "United States",
    "little rock": "United States", "fayetteville": "United States",
    "billings": "United States", "missoula": "United States",
    "springfield": "United States", "rockford": "United States",
    "peoria": "United States", "anchorage": "United States",
    "honolulu": "United States", "boise": "United States",
    "des moines": "United States", "sioux falls": "United States",
    "bismarck": "United States", "cheyenne": "United States",
    "helena": "United States", "concord": "United States",
    "providence": "United States", "charleston": "United States",
    "jackson": "United States", "columbia": "United States",
    "richmond": "United States", "spokane": "United States",
    "san francisco": "United States", "sf": "United States",
    "los angeles": "United States", "la": "United States",
    "seattle": "United States", "chicago": "United States",
    "boston": "United States", "austin": "United States",
    "denver": "United States", "atlanta": "United States",
    "miami": "United States", "dallas": "United States",
    "houston": "United States", "washington": "United States",
    "washington dc": "United States", "washington d.c.": "United States",
    "portland": "United States", "san jose": "United States",
    "san diego": "United States", "phoenix": "United States",
    "minneapolis": "United States", "pittsburgh": "United States",
    "raleigh": "United States", "salt lake city": "United States",
    "nashville": "United States", "charlotte": "United States",
    "detroit": "United States", "philadelphia": "United States",
    "las vegas": "United States", "baltimore": "United States",
    "orlando": "United States", "tampa": "United States",
    "san antonio": "United States", "columbus": "United States",
    "indianapolis": "United States", "jacksonville": "United States",
    "memphis": "United States", "louisville": "United States",
    "richmond": "United States", "new orleans": "United States",
    "st. louis": "United States", "saint louis": "United States",
    "kansas city": "United States", "oklahoma city": "United States",
    "albuquerque": "United States", "tucson": "United States",
    "omaha": "United States", "sacramento": "United States",

    # Latin America
    "são paulo": "Brazil", "sao paulo": "Brazil",
    "rio de janeiro": "Brazil", "brasília": "Brazil", "brasilia": "Brazil",
    "belo horizonte": "Brazil", "curitiba": "Brazil",
    "recife": "Brazil", "porto alegre": "Brazil",
    "mexico city": "Mexico", "guadalajara": "Mexico", "monterrey": "Mexico",
    "buenos aires": "Argentina", "córdoba": "Argentina", "rosario": "Argentina",
    "bogotá": "Colombia", "bogota": "Colombia", "medellín": "Colombia",
    "medellin": "Colombia", "cali": "Colombia",
    "santiago": "Chile", "lima": "Peru", "quito": "Ecuador",
    "caracas": "Venezuela", "montevideo": "Uruguay",
}

# Phrases that mean truly remote — no single country
_GLOBAL_REMOTE = re.compile(
    r"^(remote|worldwide|global|anywhere|distributed|"
    r"work from anywhere|fully remote|100%\s*remote|"
    r"remote\s*[-–]\s*(global|worldwide|anywhere|eu|europe|emea|apac|latam|"
    r"us|usa|uk|north america|south america|us\s*(and|&|/)\s*canada|"
    r"europe\s*(and|&|/)?\s*middle east|international)|"
    r"multiple locations?|various locations?|"
    r"flexible\s*/\s*remote|global\s*/\s*remote|"
    r"not specified|tbd|n/a)$",
    re.IGNORECASE,
)

# 2-letter codes that appear as BOTH US state abbrev AND ISO-2 country code.
# When following a city name, treat as US state (city, CA = California not Canada).
_AMBIGUOUS_US_STATES: set[str] = {"al", "ar", "ca", "co", "de", "id", "il", "in", "mt"}


def country_from_location(location: str, fallback: str = "") -> str:
    """
    Derive the job's actual country from its raw ATS location string.

    Priority order:
    1. Pure remote / worldwide → ""  (no country)
    2. Whole string is a known country name
    3. Last comma-segment is a country name or ISO-2 code
    4. Last comma-segment is a US state (full or abbr.) → United States
    5. Last comma-segment is a Canadian province → Canada
    6. City lookup on any comma-segment
    7. City lookup on stripped whole string
    8. fallback (company HQ country)
    """
    if not location:
        return fallback

    raw = location.strip()
    raw_lower = raw.lower()

    # ── 1. Global-remote patterns → no country ───────────────────────────────
    if _GLOBAL_REMOTE.match(raw_lower):
        return ""

    # ── 2. Whole string is a country name ────────────────────────────────────
    if raw_lower in COUNTRY_NAMES:
        return COUNTRY_NAMES[raw_lower]
    # Handle parenthetical remote: "Remote (Netherlands)"
    m = re.match(r"^remote\s*[\(\[](.*?)[\)\]]$", raw_lower)
    if m:
        inner = m.group(1).strip()
        if inner in COUNTRY_NAMES:
            return COUNTRY_NAMES[inner]
        if inner in CITY_TO_COUNTRY:
            return CITY_TO_COUNTRY[inner]

    # ── 3. Split on comma and examine each segment right-to-left ─────────────
    parts = [p.strip() for p in raw.split(",") if p.strip()]

    # Try segments from right to left (rightmost is most likely to be country)
    for i, part in enumerate(reversed(parts)):
        part_lower = part.lower().strip()
        part_idx = len(parts) - 1 - i  # original index

        # Full country name
        if part_lower in COUNTRY_NAMES:
            return COUNTRY_NAMES[part_lower]

        # ISO-2 country code — but only if it's NOT an ambiguous US-state abbrev
        # (e.g. CA after a city = California, not Canada)
        if part_lower in ISO2_TO_COUNTRY and part_lower not in _AMBIGUOUS_US_STATES:
            return ISO2_TO_COUNTRY[part_lower]

        # Ambiguous 2-letter code: check if the preceding segment is a US city
        if part_lower in _AMBIGUOUS_US_STATES and part_idx > 0:
            prev_city = parts[part_idx - 1].lower().strip()
            # B8 fix: previous version returned "United States" whenever
            # the preceding segment was NOT a known US city, even if it was
            # an unambiguous non-US city like "Bangalore" or "Berlin" (which
            # is not in CITY_TO_COUNTRY, but should win by being non-US).
            # New rule: trust a known city. If the preceding segment is not
            # a known city, fall through to the ISO2 lookup below.
            if prev_city in CITY_TO_COUNTRY:
                return CITY_TO_COUNTRY[prev_city]
            # Otherwise treat as ISO2 country
            if part_lower in ISO2_TO_COUNTRY:
                return ISO2_TO_COUNTRY[part_lower]
            return "United States"

        # US state full name
        if part_lower in US_STATES_FULL:
            return "United States"

        # US state abbreviation (non-ambiguous ones only)
        if len(part_lower) == 2 and part_lower in US_STATES_ABBR and part_lower not in ISO2_TO_COUNTRY:
            return "United States"

        # Canadian province full name
        if part_lower in CA_PROVINCES_FULL:
            return "Canada"

    # ── 4. City lookup on each segment ───────────────────────────────────────
    for part in parts:
        part_lower = part.lower().strip()
        # Strip "Hybrid -" prefix etc.
        cleaned = re.sub(r"^(hybrid|remote|onsite)\s*[-–]\s*", "", part_lower).strip()
        if cleaned in CITY_TO_COUNTRY:
            return CITY_TO_COUNTRY[cleaned]
        if part_lower in CITY_TO_COUNTRY:
            return CITY_TO_COUNTRY[part_lower]

    # ── 5. City lookup on the whole stripped string ───────────────────────────
    stripped = re.sub(r"^(hybrid|remote|onsite|flexible)\s*[-–/]\s*", "", raw_lower).strip()
    if stripped in CITY_TO_COUNTRY:
        return CITY_TO_COUNTRY[stripped]

    # ── 6. Nothing matched → use HQ country as fallback ──────────────────────
    return fallback
