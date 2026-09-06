import os
import re
import csv
import time
import socket
import collections
import unicodedata
import urllib.parse
import urllib.request
import json
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ModuleNotFoundError:  # Provider-API-only runs can still work without a browser.
    sync_playwright = None
    class PlaywrightTimeoutError(Exception):
        pass

# Real-time logging. When a progress callback is installed (desktop app) all
# output lines are routed to it; otherwise they print to stdout as before.
import builtins as _builtins

progress_cb = None


def _notify(msg):
    if progress_cb:
        progress_cb(msg)
    else:
        _builtins.print(msg, flush=True)


def print(*args, **kwargs):
    _notify(" ".join(str(a) for a in args))
# ───────────────────────── JS HELPERS ──────────────────────────
# Upgraded with high-precision regex matching and robust card scoping to prevent 
# matching large layout containers and extracting generic page texts.
JS_HELPERS = r"""
const querySelectorAllDeep = (selector, root = document) => {
    const out = [];
    const walk = (node) => {
        if (!node) return;
        if (node.nodeType === 1) {
            try {
                if (node.matches && node.matches(selector)) out.push(node);
            } catch(e) {}
            if (node.shadowRoot) {
                walk(node.shadowRoot);
            }
        }
        if (node.childNodes) {
            for (const child of node.childNodes) walk(child);
        }
    };
    walk(root);
    return out;
};
const cleanText = (s) => String(s || '').replace(/\s+/g, ' ').trim();
const getClassName = (el) => {
    if (!el) return '';
    const cls = el.className;
    if (typeof cls === 'string') return cls;
    if (cls && typeof cls === 'object' && 'baseVal' in cls) return cls.baseVal || '';
    return String(cls || '');
};
const isVisible = (el) => {
    if (!el) return false;
    try {
        const r = el.getBoundingClientRect();
        const st = window.getComputedStyle(el);
        return r.width > 0 && r.height > 0 &&
               st.display !== 'none' &&
               st.visibility !== 'hidden' &&
               st.opacity !== '0';
    } catch(e) {
        return false;
    }
};
const badScopeSelector = [
    'header', 'nav', 'footer',
    '[role="banner"]', '[role="contentinfo"]',
    '.site-header', '.site-footer',
    '.navbar', '.navigation', '.main-nav', '.primary-nav',
    '.cookie-banner', '.cookie-consent', '.cookie-notice',
    '[class*="CookieBanner"]', '[class*="cookie-bar"]',
    '[id*="cookie-notice"]'
].join(',');
const isBadScope = (el) => {
    try {
        return !!el.closest(badScopeSelector);
    } catch(e) {
        return false;
    }
};
// Expanded to match custom-hosted ATS directories like Catawiki's /o/ and Deliveroo's /role/
const jobUrlRe = /(\/job(s)?\/[^\/?#]+|\/career(s)?\/[^/?#]+\/[^\/?#]+|\/o\/[a-zA-Z0-9-]+|\/role\/[a-zA-Z0-9-]+|\/position|\/vacancy|\/vacancies|\/opening|\/role|\/requisition|\/posting|\/apply|\/stellenangebot|\/stelle|\/lavoro|\/posizioni|\/annuncio|\/offerta|\/opportunit|detail|jobid|job_id|gh_jid|reqid|requisition|posting|lever\.co|greenhouse\.io|personio|workable|smartrecruiters|teamtailor|ashby|workdayjobs|successfactors|phenompeople|eightfold|deel\.com\/job-boards)/i;
// FIXED: Uses leading slashes and word boundaries for path keywords (like /about, /press)
// to prevent matching entire domain names like aboutyou.de or americanexpress.com!
const badUrlRe = /(\/(privacy|cookie|terms|legal|about|contact|history|press|investor|culture|benefit|login|signup|help|blog|pricing|faq|values|diversity|inclusion|mission|story|leadership|impact|journey|how-we-hire|talent-community|talent-network|job-alert|subscribe|download|upload|notify)\b|facebook|linkedin|twitter|instagram|youtube|support\.google|play\.google|apps\.apple|mailto:|tel:)/i;
const genericTextRe = /^(apply|apply now|view|view job|view role|view position|read more|details|click here|learn more|more info|more information|maggiori informazioni|mehr informationen|meer informatie|load more|show more|see more|next|previous|back|home|jobs|careers|search|filter|sort|select|choose|open|close|\+|-|>|<|\d+|job listing|job listings|job vacancy|job vacancies|vacancy|vacancies|current opening|current openings|open position|open positions|opening|openings|role|roles|position|positions|job|jobs|career|careers|learn more|read more|apply here|apply online|view details|job details|role details|position details|vacancy details|read job description|job description|description|full description|full details|link|apply for this job|apply for this role)$/i;
const uiTextRe = /(checkbox|items per page|page \d+|open jobs|posting date|clear all filters|filter results|privacy statement|terms of use|cookie|stay connected|job alert|manage preferences|recruitment fraud|business code of conduct|human rights|whistleblowing|code of ethics)/i;
const roleWordRe = /\b(engineer|developer|manager|analyst|scientist|specialist|consultant|architect|designer|director|lead|head|principal|senior|junior|intern|trainee|associate|advisor|officer|administrator|recruiter|counsel|lawyer|accountant|controller|planner|coordinator|assistant|representative|agent|technician|mechanic|operator|driver|picker|cashier|crew|barista|rider|expert|owner|scrum master|product owner|sales|marketing|finance|security|devops|frontend|backend|full stack|fullstack|software|data|qa|quality|stagiair|stage|werkstudent|apprentice|graduate|nurse|doctor|pharmacist|planner|scheduler|receptionist|waiter|warehouse|legal counsel|business partner)\b/i;
const locationRe = /(remote|hybrid|onsite|on-site|amsterdam|berlin|hamburg|munich|münchen|frankfurt|cologne|köln|london|manchester|paris|lyon|madrid|barcelona|lisbon|porto|milano|milan|roma|rome|torino|turin|bologna|dublin|stockholm|copenhagen|oslo|helsinki|vienna|wien|zurich|zürich|warsaw|krakow|kraków|prague|praha|budapest|bucharest|sofia|tallinn|riga|vilnius|bengaluru|bangalore|mumbai|delhi|hyderabad|tokyo|singapore|sydney|new york|san francisco|chicago|boston|austin|seattle|toronto|netherlands|germany|italy|france|spain|portugal|united kingdom|uk|united states|usa|india|poland|sweden|denmark|norway|finland|austria|switzerland|belgium|ireland|estonia|latvia|lithuania|romania|greece|hungary|czech|japan|china|australia|canada)/i;
// FIXED: rejects UI link text, departments, brands, abbreviations and contract words
// from ever being treated as a location (kills "Internal Services Share Learn more",
// "LensCrafters", "CDI", "Nightshift", "JobDetail", "DACH", ...)
const badLocationRe = /(share|learn more|read more|view more|show more|load more|more results|apply now|details|public sector|financial services|internal services|customer services|customer service|information technology|field operations|supply chain|business development|people team|talent team|marketing & communications|sunglass hut|target optical|for eyes|vogue eyewear|ikea store|living rooms|human resources|job alerts?|career areas|open positions|privacy policy|terms of use|cookie policy|stay connected|talent community|marketing|sales|operations|engineering|finance|legal|insurance|hr|people|talent|product|design|security|audit|tax|support|communications|facilities|business|infrastructure|systems|procurement|logistics|warehouse|strategy|recruitment|compliance|commerce|retail|corporate|administration|accounting|analytics|data|cloud|platform|solutions|services|internal|customer|manufacturing|public|sector|financial|technology|information|dach|emea|latam|apac|mena|ind|flex|gtm|csm|rxo|gqe|cdi|cdd|nightshift|shift|store|stores|markthalle|lenscrafters|oakley|opsm|ray-ban|persol|eyemed|glasses|jobdetail|externaljobs|jobsuche|praxissoftware|career|careers|vacancy|vacancies|position|positions|opening|openings|requisition|posting|trainee|internship|intern|praktikum|werkstudent|scholarship|location|locations|department|departments|workplace)\b/i;
const currentClean = window.location.href
    .split('#')[0]
    .split('?')[0]
    .toLowerCase()
    .replace(/\/$/, '');
const hasJobQuery = (href) => /[?&](job|jobid|job_id|jid|gh_jid|req|reqid|requisition|requisitionid|posting|postingid|id)=/i.test(href);
const isSelfListingUrl = (href) => {
    const clean = href.split('#')[0].split('?')[0].toLowerCase().replace(/\/$/, '');
    if (/#job=/i.test(href)) return false;
    if (hasJobQuery(href)) return false;
    return clean === currentClean;
};
const looksJobUrl = (href) => {
    if (!href || !String(href).startsWith('http')) return false;
    if (badUrlRe.test(href)) return false;
    if (isSelfListingUrl(href)) return false;
    return jobUrlRe.test(href);
};
// FIXED: Upgraded with a two-pass system that prefers line matches for roleWordRe.
// This prevents picking up location headers or boilerplate as job titles from multiline cards (e.g. Deliveroo's 'Emilia-Romagna').
const firstGoodLine = (text) => {
    const lines = String(text || '')
        .split(/\n|\\n/)
        .map(x => cleanText(x))
        .filter(Boolean);
    
    // Pass 1: Try to match a line that has a strong role keyword
    for (const line of lines) {
        if (line.length < 4 || line.length > 150) continue;
        if (!/[A-Za-zÀ-ÿ]/.test(line)) continue;
        if (genericTextRe.test(line)) continue;
        if (uiTextRe.test(line)) continue;
        if (/^[^A-Za-zÀ-ÿ0-9]+$/.test(line)) continue;
        if (roleWordRe.test(line)) return line;
    }
    // Pass 2: Fallback to the first available line
    for (const line of lines) {
        if (line.length < 4 || line.length > 150) continue;
        if (!/[A-Za-zÀ-ÿ]/.test(line)) continue;
        if (genericTextRe.test(line)) continue;
        if (uiTextRe.test(line)) continue;
        if (/^[^A-Za-zÀ-ÿ0-9]+$/.test(line)) continue;
        // FIXED: skip lines that are pure locations (e.g. "Emilia-Romagna", "Berlin")
        if (locationRe.test(line) && !roleWordRe.test(line)) continue;
        if (badLocationRe.test(line)) continue;
        return line;
    }
    return '';
};
const titleFromScope = (scope) => {
    if (!scope) return '';
    const titleSelectors = [
        'a[data-automation-id="jobTitle"]',
        '[data-automation-id="jobTitle"]',
        '[data-ph-at-id="job-title"]',
        '[data-testid*="job-title" i]',
        '[data-testid*="title" i]',
        '[data-qa*="job-title" i]',
        '[class*="job-title" i]',
        '[class*="jobTitle" i]',
        '[class*="position-title" i]',
        '[class*="posting-title" i]',
        '[class*="vacancy-title" i]',
        '[class*="role-title" i]',
        '[class*="title" i]',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'strong', 'b'
    ];
    for (const sel of titleSelectors) {
        const nodes = querySelectorAllDeep(sel, scope);
        for (const n of nodes) {
            if (!isVisible(n)) continue;
            const t = firstGoodLine(n.innerText || n.textContent || '');
            if (!t) continue;
            // FIXED: never use a pure location or boilerplate/department text as a title
            if ((locationRe.test(t) && !roleWordRe.test(t))) continue;
            if (badLocationRe.test(t) && !roleWordRe.test(t)) continue;
            if (/^(sales & commercial|corporate banking|private banking|financial services|internal services|customer services|information technology|public sector|risk management|marketing & communications|data & analytics|operations|manufacturing|engineering|finance|marketing|sales|legal|human resources|product|design|insurance|retail|store operations|communications|logistics|supply chain|customer service|customer success|field operations)$/i.test(t)) continue;
            return t;
        }
    }
    return firstGoodLine(scope.innerText || scope.textContent || '');
};
// FIXED: Checked data-attributes on the scope element itself!
// Prevents missing locations when the container element holds metadata as attributes instead of raw text.
const locationFromScope = (scope) => {
    if (!scope) return '';
    
    // Check attributes on the scope element itself first
    const attrLoc = 
        scope.getAttribute?.('data-location') ||
        scope.getAttribute?.('data-office') ||
        scope.getAttribute?.('data-city') ||
        scope.getAttribute?.('data-country') ||
        scope.getAttribute?.('data-place');
    if (attrLoc) {
        const cleaned = cleanText(attrLoc);
        if (cleaned && !badLocationRe.test(cleaned)) return cleaned;
    }
    
    const locSelectors = [
        '[data-automation-id*="location" i]',
        '[data-testid*="location" i]',
        '[data-qa*="location" i]',
        '[class*="location" i]',
        '[class*="city" i]',
        '[class*="office" i]',
        '[class*="place" i]',
        '[aria-label*="location" i]'
    ];
    for (const sel of locSelectors) {
        const nodes = querySelectorAllDeep(sel, scope);
        for (const n of nodes) {
            if (!isVisible(n)) continue;
            const txt = cleanText(n.innerText || n.textContent || '');
            if (!txt || txt.length > 200 || !locationRe.test(txt)) continue;
            if (badLocationRe.test(txt)) continue;
            // prefer the LAST segment for "City - Country" / "Brand - City" layouts
            const segs = txt.split(/\s*-\s*|\s*\|\s*|\s{2,}/).map(x => cleanText(x)).filter(Boolean);
            return txt;
        }
    }
    const lines = String(scope.innerText || '')
        .split(/\n|\\n/)
        .map(x => cleanText(x))
        .filter(Boolean);
    for (const line of lines) {
        if (line.length <= 120 && locationRe.test(line) && !badLocationRe.test(line)) {
            const segs = line.split(/\s*-\s*|\s*\|\s*/).map(x => cleanText(x)).filter(Boolean);
            return line;
        }
    }
    return '';
};
// FIXED: Upgraded with accordion/card/row-class selectors and layout filters.
// Also starts searching from parentElement to avoid returning the 'a' anchor itself!
const scopeForAnchor = (a) => {
    if (!a) return null;
    const selectors = [
        '[data-job-id]', '[data-jobid]', '[data-job]',
        '[data-position-id]', '[data-posting-id]', '[data-requisition-id]',
        '[data-automation*="job" i]', '[data-testid*="job" i]',
        '[data-testid*="accordion" i]', '[data-testid*="card" i]', '[data-testid*="item" i]',
        '[class*="job-card" i]', '[class*="job-item" i]', '[class*="job-listing" i]',
        '[class*="position-card" i]', '[class*="position-item" i]',
        '[class*="posting" i]', '[class*="opening" i]', '[class*="vacancy" i]',
        '[class*="accordion-item" i]', '[class*="accordionItem" i]', '[class*="accordion" i]',
        '[class*="card" i]', '[class*="row" i]', '[class*="item" i]',
        'li', 'article', 'tr', '[role="listitem"]'
    ];
    for (const sel of selectors) {
        try {
            const s = a.parentElement ? a.parentElement.closest(sel) : null;
            if (s) {
                if (s.tagName === 'BODY' || s.tagName === 'MAIN') continue;
                const txt = cleanText(s.innerText || '');
                const linksCount = querySelectorAllDeep('a[href]', s).length;
                if (txt.length > 3000 || linksCount > 15) {
                    continue; // Skip layout containers
                }
                return s;
            }
        } catch(e) {}
    }
    let p = a.parentElement;
    for (let i = 0; i < 4 && p; i++, p = p.parentElement) {
        if (p.tagName === 'BODY' || p.tagName === 'MAIN') break;
        const txt = cleanText(p.innerText || '');
        const linksCount = querySelectorAllDeep('a[href]', p).length;
        if (txt.length >= 10 && txt.length <= 2500 && linksCount <= 15) return p;
    }
    return a; // Fallback to anchor itself if parent layout wraps too much content
};
const pickJobUrl = (scope) => {
    if (!scope) return '';
    if (scope.tagName === 'A' && looksJobUrl(scope.href)) {
        return scope.href;
    }
    const links = querySelectorAllDeep('a[href]', scope);
    for (const a of links) {
        if (!isVisible(a)) continue;
        if (looksJobUrl(a.href)) return a.href;
    }
    const dataHref =
        scope.getAttribute?.('data-href') ||
        scope.getAttribute?.('data-url') ||
        scope.getAttribute?.('data-link') ||
        scope.getAttribute?.('data-permalink');
    if (dataHref) {
        try {
            const full = new URL(dataHref, window.location.href).href;
            if (looksJobUrl(full)) return full;
        } catch(e) {}
    }
    const dataInfo =
        scope.getAttribute?.('data-info') ||
        scope.getAttribute?.('data-slug') ||
        scope.getAttribute?.('data-id') ||
        scope.getAttribute?.('data-job-id') ||
        scope.getAttribute?.('data-posting-id');
    if (dataInfo && dataInfo.length > 3) {
        try {
            const base = window.location.href.split('?')[0].split('#')[0].replace(/\/$/, '');
            if (base.endsWith('/jobs')) {
                return base + '/' + dataInfo;
            }
            if (base.includes('/jobs/')) {
                return base + '/' + dataInfo;
            }
            return base + '/jobs/' + dataInfo;
        } catch(e) {}
    }
    const clickable = scope.querySelector?.('[onclick]') || (scope.hasAttribute?.('onclick') ? scope : null);
    if (clickable) {
        const oc = clickable.getAttribute('onclick') || '';
        const m = oc.match(/['"]([^'"]*(?:job|career|position|vacancy|role|opening|posting|requisition)[^'"]*)['"]/i);
        if (m) {
            try {
                const full = new URL(m[1], window.location.href).href;
                if (!badUrlRe.test(full)) return full;
            } catch(e) {}
        }
    }
    return '';
};
const synthJobUrl = (title, loc) => {
    const titleSlug = cleanText(title).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').substring(0, 70);
    const locSlug = cleanText(loc || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').substring(0, 40);
    return window.location.href.split('?')[0].split('#')[0] + '#job=' + titleSlug + '--' + locSlug;
};
"""
# ───────────────────────── CONFIG ──────────────────────────────
class ProductionScannerConfig:
    ACTION_TIMEOUT_MS = 35000
    STABILIZATION_DELAY_SEC = 6
    MAX_PAGINATION_PAGES = 250  # hard cap; loop also self-terminates earlier (see below)
    MAX_COMPANY_TIME_SEC = 900    # per-company wall-clock budget (15 min) — giant boards release worker slots
    LOW_YIELD_PAGES = 5           # stop when N consecutive pages each add <= 2 new jobs
    # ── Network resilience (v7.1) ────────────────────────────────────────────
    # A single DNS/connection blip must not zero out a 3-hour crawl. These knobs
    # gate the run up-front and add exponential backoff to every navigation/fetch.
    PREFLIGHT_ENABLED = True          # probe connectivity before crawling
    PREFLIGHT_PROBE_HOSTS = (         # representative hosts; must resolve + connect
        "www.google.com",
        "boards-api.greenhouse.io",
        "www.amazon.jobs",
        "jobs.sap.com",
        "www.asml.com",
    )
    PREFLIGHT_PORT = 443
    PREFLIGHT_TIMEOUT_SEC = 5
    PREFLIGHT_MAX_FAILURES = 2        # abort if this many (or more) probes fail
    GOTO_RETRIES = 3                  # navigation attempts per URL
    GOTO_BACKOFF_BASE_SEC = 2.0       # exponential: 2s, 4s, 8s...
    HTTP_RETRIES = 3                  # provider-API fetch attempts
    HTTP_BACKOFF_BASE_SEC = 1.5
    HTTP_TIMEOUT_SEC = 20
    PAGINATION_WAIT_MS = 2500     # wait after clicking next
    DOM_QUIET_MS = 3000           # shorter dom-quiet for pagination
    MAX_INFINITE_SCROLL = 35
    MAX_LOAD_MORE_CLICKS = 30
    HARD_TITLE_BLACKLIST = {
        "jobs", "job", "careers", "career", "all jobs", "all openings",
        "open positions", "open roles", "current openings", "vacancies",
        "vacancy", "our jobs", "our openings", "our roles", "search jobs",
        "browse jobs", "view all jobs", "see all jobs", "job search",
        "search", "job openings", "job listings", "openings",
        "home", "homepage", "main", "skip to content", "skip to main content",
        "back", "back to top", "close", "menu", "toggle menu", "open menu",
        "learn more", "read more", "view more", "see more", "show more",
        "load more", "click here", "details", "view details", "view role",
        "view job", "view position", "apply", "apply now",
        "privacy", "privacy statement", "privacy policy", "terms",
        "terms of use", "terms & conditions", "legal", "cookie policy",
        "cookie settings", "manage cookies", "consent", "settings",
        "notice", "notifications", "accept", "this website uses cookies",
        "we use cookies", "cookie notice", "recruitment fraud warning",
        "business code of conduct", "code of ethics",
        "human rights & environmental policy", "whistleblowing",
        "complaints procedure", "sustainable sourcing policies",
        "accessibility", "disclaimer",
        "title", "job title", "position title", "loading", "please wait",
        "no results", "items per page:", "items per page", "filter results",
        "clear all filters", "posting dates", "posting date", "career area",
        "workplace", "location", "locations", "country", "region",
        "department", "departments", "teams", "select language",
        "choose language", "language", "english", "deutsch", "italiano",
        "français", "español", "nederlands", "português", "polski",
        "open jobs", "page", "ellipsis",
        "job description", "description", "job details", "position details",
        "full time", "part time", "internship", "contract", "remote",
        "hybrid", "on-site", "onsite", "upload your cv", "upload cv",
        "submit cv", "submit resume", "download", "share this job",
        "print", "email this job", "save this job", "save for later", "show job",
        "job alerts",
        "culture", "our culture", "our values", "values", "mission",
        "how we hire", "hiring process", "hiring", "our people",
        "our team", "the team", "our impact", "diversity", "inclusion",
        "benefits", "perks", "life at", "why us", "why work here",
        "about us", "about", "our story", "who we are", "what we do",
        "history", "leadership", "our leadership", "meet the team",
        "join us", "connect with us", "talent community",
        "join our talent community",
        "engineering", "marketing", "sales", "finance", "operations",
        "product", "design", "hr", "human resources", "legal",
        "customer success", "data", "analytics", "logistics",
        "compliance", "it", "technology", "field operations",
        "data & analytics", "data and analytics", "corporate banking",
        "private banking", "risk management", "finance & risk management",
        "digital & innovation", "marketing & communications",
        "customer & products", "expertise areas",
        "students & young professionals", "interns and trainees",
        "early careers", "experienced", "students", "graduates",
        "internships", "marketplace", "retail media", "campaign material",
        "operational risk management and control", "analytics & risk",
        "customer service and", "corporate", "sales & relationship",
        "applications engineering", "business performance improvement",
        "customer support", "design engineering and architecture",
        "learning and knowledge management", "legal, compliance, risk and assurance",
        "management support", "manufacturing", "projects, programs and change",
        "real estate and facilities management",
        "research and technology development",
        "sales & customer management", "sourcing and supply chain management",
        "d&e architects", "d&e planner / integrator",
        "electrical engineering", "management design engineering",
        "mechanical engineering", "mechatronics", "system industrialization",
        "system integration and testing", "chemical engineering",
        "computer science", "data science", "materials science",
        "mathematics", "other non-technical backgrounds",
        "other technical backgrounds",
        "working at abn amro", "why abn amro?", "testimonials",
        "fringe benefits", "learning and development", "challenging work",
        "making an impact", "hybrid working", "working level",
        "number of hours", "workexperience", "the reboot program",
        "all vacancies", "work with us", "find the job that matches you.",
        "service & contacts", "play store", "go to home page",
        "career areas", "ai usage", "stay connected.",
        "colleagues", "about american express", "people care",
        "people development", "daily life", "vision, mission & values",
        "#ourcareers", "manage your preferences", "be open",
        "sorry! no openings!", "for brands", "for publishers",
        "for creators", "product update", "announcement", "case study",
        "ir information", "financial highlights", "ir library",
        "stock information", "ir calendar", "suppliernet", "customernet",
        "high school", "vocational", "10-15 years",
    }
    COUNTRIES_AND_REGIONS = {
        "india", "united states", "usa", "united", "germany", "japan",
        "china", "netherlands", "france", "italy", "spain", "uk",
        "united kingdom", "europe", "asia", "north america",
        "south america", "global", "worldwide", "remote",
        "barcelona", "amsterdam", "london", "berlin", "paris",
        "madrid", "milan", "milano", "rome", "roma", "hamburg",
        "munich", "frankfurt", "dublin", "lisbon", "stockholm",
        "copenhagen", "oslo", "helsinki", "vienna", "zurich",
        "warsaw", "krakow", "kraków", "prague", "praha", "budapest",
        "bucharest", "sofia", "tallinn", "riga", "vilnius", "bengaluru",
        "bangalore", "mumbai", "delhi", "hyderabad", "tokyo", "singapore",
        "sydney", "toronto", "new york", "boston", "chicago", "austin",
        "seattle", "san francisco",
        # Italian regions
        "lombardia", "lombardy", "piemonte", "piedmont", "veneto", 
        "emilia-romagna", "lazio", "campania", "puglia", "apulia", 
        "sicilia", "sicily", "toscana", "tuscany", "friuli-venezia giulia", 
        "abruzzo", "umbria", "marche", "liguria"
    }
    ROLE_WORD_PATTERN = re.compile(
        r"\b("
        r"engineer|developer|manager|analyst|scientist|specialist|consultant|"
        r"president|vice|chief|cfo|ceo|cto|cmo|coo|chro|chairman|chef|"
        r"architect|designer|director|lead|head|principal|senior|junior|"
        r"intern|trainee|associate|advisor|officer|administrator|recruiter|"
        r"counsel|lawyer|accountant|controller|planner|coordinator|assistant|"
        r"representative|agent|technician|mechanic|operator|driver|picker|"
        r"cashier|crew|barista|rider|expert|owner|scrum master|product owner|"
        r"sales|marketing|finance|security|devops|frontend|backend|full stack|"
        r"fullstack|software|data|qa|quality|stagiair|stage|werkstudent|"
        r"apprentice|graduate|nurse|doctor|pharmacist|planner|scheduler|"
        r"receptionist|waiter|warehouse|legal counsel|business partner"
        r")\b",
        re.IGNORECASE,
    )
    SUSPICIOUS_TITLE_PATTERNS = [
        re.compile(r"^\s*vacancies?\s*\(?\d*\)?\s*$", re.IGNORECASE),
        re.compile(r"^\s*jobs?\s*\(?\d*\)?\s*$", re.IGNORECASE),
        re.compile(r"^\s*\d+\s*(jobs?|openings?|positions?|vacancies?|roles?)\s*$", re.IGNORECASE),
        re.compile(r"^\s*skip\s+to\s+", re.IGNORECASE),
        re.compile(r"^\s*(view|see|browse|explore|find|search)\s+(all\s+)?(jobs?|roles?|positions?|openings?|vacancies?)\s*$", re.IGNORECASE),
        re.compile(r"^\s*\d+\s*$"),
        re.compile(r"^[^a-zA-Z0-9À-ÿ]+$"),
        re.compile(r"^\s*to\s+apply\s+for\s+this\s+job", re.IGNORECASE),
        re.compile(r"^\s*(explore|see|view)\s+\d+\s+open\s+roles?", re.IGNORECASE),
        re.compile(r"^\s*homepage?\s*$", re.IGNORECASE),
        re.compile(r"^\s*this\s+website\s+uses", re.IGNORECASE),
        re.compile(r"^\s*(upload|submit|download)\s+", re.IGNORECASE),
        re.compile(r"^\s*(office|home|main|back)\s*$", re.IGNORECASE),
        re.compile(r"^\s*page\s+\d+.*$", re.IGNORECASE),
        re.compile(r".*checkbox.*label.*", re.IGNORECASE),
        re.compile(r"^\s*\d+\s+open\s+jobs\s*$", re.IGNORECASE),
        re.compile(r".*click this button to view.*", re.IGNORECASE),
        re.compile(r"^\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", re.IGNORECASE),
    ]
    URL_EXCLUSION_PATTERN = re.compile(
        r"(/("
        r"privacy|cookie|terms|legal|about|contact|history|press|investor|culture|"
        r"benefit|login|signup|help|blog|pricing|faq|values|diversity|inclusion|"
        r"mission|story|leadership|impact|journey|how-we-hire|hiring-process|"
        r"life-at|talent-community|talent-network|download|upload|job-alert|"
        r"job-alerts|notify|subscribe"
        r")\b|facebook|linkedin|twitter|instagram|youtube|support\.google|"
        r"play\.google|apps\.apple|mailto:|tel:)",
        re.IGNORECASE,
    )
    CATEGORY_PATH_INDICATORS = re.compile(
        r"/(all-jobs|all-openings|browse|search|filter|category|categories|"
        r"department|departments|team|teams|location|locations|"
        r"talent-community|talent-network|newsletter|privacy|terms|cookie)/?$",
        re.IGNORECASE,
    )
    JOB_URL_PATTERN = re.compile(
        r"(/job(s)?/[^/?#]+|/career(s)?/.*(job|position|opening|vacanc|role)|"
        r"/career(s)?/[^/]+/[^/]+|/o/[^/?#]+|/role/[^/?#]+|/position|/vacancy|"
        r"/vacancies|/opening|/role|/requisition|/posting|/apply|/stellenangebot|"
        r"/stelle|/lavoro|/posizioni|/annuncio|/offerta|/opportunit|detail|"
        r"jobid|job_id|gh_jid|reqid|requisition|posting|lever\.co|greenhouse\.io|"
        r"personio|workable|smartrecruiters|teamtailor|ashby|workdayjobs|"
        r"successfactors|phenompeople|eightfold|deel\.com/job-boards)",
        re.IGNORECASE,
    )
    LANDING_PAGE_CTAS = [
        "see open roles", "view all openings", "explore open roles",
        "check openings", "browse openings", "view open roles",
        "check our openings", "open positions", "see all jobs",
        "view all jobs", "browse jobs", "explore jobs",
        "see job openings", "find your role", "all openings",
        "find open roles", "see roles", "view roles",
        "scopri le posizioni aperte", "lavora con noi",
        "posizioni aperte", "vedi tutti gli annunci",
        "offene stellen", "alle jobs", "stellenangebote",
        "bekijk vacatures", "alle vacatures",
        "voir les offres", "nos offres",
    ]
    # FIXED: Added fallback seed-company headquarters map to guarantee no location
    # remains generic Onsite/Hybrid or "Not Specified"!
    COMPANY_HEADQUARTERS = {
        "ABN AMRO": "Amsterdam, Netherlands",
        "About You": "Hamburg, Germany",
        "adjoe": "Hamburg, Germany",
        "Airbyte": "Remote",
        "Amazon Italia": "Milan, Italy",
        "American Express": "New York, USA",
        "Angelini Pharma": "Rome, Italy",
        "Anymind Group": "Singapore",
        "Appodeal": "Barcelona, Spain",
        "ASML": "Veldhoven, Netherlands",
        "Audible": "Newark, USA",
        "Babbel": "Berlin, Germany",
        "Barilla Group": "Parma, Italy",
        "Bolt": "Tallinn, Estonia",
        "Booking.com": "Amsterdam, Netherlands",
        "Buena": "Berlin, Germany",
        "Bunq": "Amsterdam, Netherlands",
        "Bynder": "Amsterdam, Netherlands",
        "Caeli Wind": "Berlin, Germany",
        "Cal.com": "Remote",
        "Catawiki": "Amsterdam, Netherlands",
        "Celonis": "Munich, Germany",
        "Choco": "Berlin, Germany",
        "ClearVue": "Remote",
        "Conad": "Bologna, Italy",
        "Coop Italia": "Bologna, Italy",
        "Databricks": "San Francisco, USA",
        "Decathlon Italia Retail": "Milan, Italy",
        "Deliveroo": "London, UK",
        "Detectify": "Stockholm, Sweden",
        "DevsData": "Warsaw, Poland",
        "Doctolib": "Paris, France",
        "Doist": "Remote",
        "Elastic Sales": "Mountain View, USA",
        "Elastic Finance": "Mountain View, USA",
        "Elastic Marketing": "Mountain View, USA",
        "Enel": "Rome, Italy",
        "Eni": "Rome, Italy",
        "Esselunga": "Milan, Italy",
        "Eurospin": "San Martino Buon Albergo, Italy",
        "Exact": "Delft, Netherlands",
        "Exness": "Limassol, Cyprus",
        "Factorial": "Barcelona, Spain",
        "Ferrero": "Alba, Italy",
        "Flix": "Munich, Germany",
        "Forto": "Berlin, Germany",
        "Freeletics": "Munich, Germany",
        "FS Italiane / Trenitalia": "Rome, Italy",
        "Generali": "Trieste, Italy",
        "Glovo": "Barcelona, Spain",
        "Harnham Germany": "London, UK",
        "Hays Germany": "Mannheim, Germany",
        "HelloFresh": "Berlin, Germany",
        "Highsnobiety": "Berlin, Germany",
        "HubSpot": "Cambridge, USA",
        "Huxley Netherlands": "Amsterdam, Netherlands",
        "Ikea Italia": "Milan, Italy",
        "ING": "Amsterdam, Netherlands",
        "Intesa Sanpaolo": "Turin, Italy",
        "Kaufland e-com": "Cologne, Germany",
        "Kelly Services Germany": "Troy, USA",
        "King": "London, UK",
        "Klarna": "Stockholm, Sweden",
        "KONUX": "Munich, Germany",
        "KPN": "Rotterdam, Netherlands",
        "La Fosse": "London, UK",
        "Lavazza": "Turin, Italy",
        "Lidl Italia": "Arcole, Italy",
        "Lightspeed": "Montreal, Canada",
        "limehome": "Munich, Germany",
        "Luxottica": "Milan, Italy",
        "McDonald's Italia": "Milan, Italy",
        "MetaQuotes": "Limassol, Cyprus",
        "Michael Page Germany": "Düsseldorf, Germany",
        "Michael Page Netherlands": "Amsterdam, Netherlands",
        "Michael Page UK": "London, UK",
        "Miro": "Amsterdam, Netherlands",
        "Mollie": "Amsterdam, Netherlands",
        "Morgan McKinley": "Dublin, Ireland",
        "MSD Netherlands": "Haarlem, Netherlands",
        "NavVis": "Munich, Germany",
        "Nexthink (Germany)": "Lausanne, Switzerland",
        "Nigel Frank": "Newcastle, UK",
        "Notion": "San Francisco, USA",
        "Ocado Technology": "Hatfield, UK",
        "Optiver": "Amsterdam, Netherlands",
        "Organon": "Jersey City, USA",
        "Pam Panorama": "Venice, Italy",
        "Personio": "Munich, Germany",
        "Picnic": "Amsterdam, Netherlands",
        "Pipedrive": "Tallinn, Estonia",
        "Pitch": "Berlin, Germany",
        "Planhat": "Stockholm, Sweden",
        "Poste Italiane": "Rome, Italy",
        "Prada Group": "Milan, Italy",
        "Quinyx": "Stockholm, Sweden",
        "reisetopia": "Berlin, Germany",
        "Reperio Human Capital": "Belfast, UK",
        "Retool": "San Francisco, USA",
        "Revolut": "London, UK",
        "Robert Walters Germany": "Frankfurt, Germany",
        "Robert Walters Ireland": "Dublin, Ireland",
        "Robert Walters Netherlands": "Amsterdam, Netherlands",
        "Rows": "Porto, Portugal",
        "SAP": "Walldorf, Germany",
        "Scorewarrior": "Limassol, Cyprus",
        "Shopify": "Remote",
        "Siemens": "Munich, Germany",
        "Sigmar Recruitment": "Dublin, Ireland",
        "Skyscanner": "Edinburgh, UK",
        "SNAM": "San Donato Milanese, Italy",
        "Spendesk": "Paris, France",
        "Spotify": "Stockholm, Sweden",
        "Stellantis": "Amsterdam, Netherlands",
        "Stripe": "San Francisco, USA",
        "SumUp": "London, UK",
        "Talentor Germany": "Vienna, Austria",
        "Teamtailor": "Stockholm, Sweden",
        "TIM": "Rome, Italy",
        "Understanding Recruitment": "St Albans, UK",
        "Undutchables": "Amsterdam, Netherlands",
        "UniCredit": "Milan, Italy",
        "Veriff": "Tallinn, Estonia",
        "Voi Technology": "Stockholm, Sweden",
        "Wise": "London, UK"
    }

    # ── NEW: location-quality fixes ──────────────────────────────
    # Multi-word cities (prefix-completion + known-place validation)
    MULTI_WORD_CITIES = {
        "palo alto", "las vegas", "sao paulo", "são paulo", "rio de janeiro",
        "round rock", "fort worth", "fort lauderdale", "fort collins", "fort wayne",
        "san francisco", "san jose", "san diego", "san antonio", "san mateo",
        "san ramon", "san carlos", "san leandro", "san rafael", "san pedro",
        "santa clara", "santa monica", "santa cruz", "santa barbara", "santa rosa",
        "santa fe", "st louis", "st. louis", "st gallen", "st. gallen",
        "st petersburg", "new york", "new jersey", "new delhi", "new haven",
        "newport beach", "newport news", "new brunswick", "new castle",
        "los angeles", "los alamitos", "king of prussia", "mountain view",
        "walnut creek", "redwood city", "menlo park", "south lake tahoe",
        "el segundo", "el dorado hills", "salt lake city", "kansas city",
        "oklahoma city", "charlotte", "charlottesville", "myrtle beach",
        "white plains", "herndon", "reston", "tysons", "tysons corner",
        "frankfurt am main", "bad homburg", "neu-isenburg", "bad nauheim",
        "mörfelden-walldorf", "seeheim-jugenheim", "alsbach-hähnlein",
        "garching bei münchen", "unterschleißheim", "st. leon-rot",
        "wiesbaden", "düsseldorf", "köln", "münchen", "zürich", "nürnberg",
        "hannover", "mönchengladbach", "mülheim", "saarbrücken", "koblenz",
        "ludwigshafen", "kaiserslautern", "bad kreuznach", "rüsselsheim",
        "groß-gerau", "rödermark", "dietzenbach", "maintal", "langen",
        "egelsbach", "weiterstadt", "pfungstadt", "bensheim", "heppenheim",
        "lampertheim", "bürstadt", "toenisvorst", "willich", "kaarst",
        "meerbusch", "erkelenz", "hückelhoven", "wegberg", "wassenberg",
        "schwäbisch hall", "göppingen", "esslingen", "tübingen", "sindelfingen",
        "böblingen", "leonberg", "herrenberg", "nürtingen", "kirchheim",
        "filderstadt", "ostfildern", "waiblingen", "fellbach", "backnang",
        "ludwigsburg", "kornwestheim", "bietigheim-bissingen", "vaihingen",
        "bad rappenau", "sinsheim", "waibstadt", "meckesheim", "neckargemünd",
        "schönau", "wiesloch", "walldorf", "sandhausen", "nußloch", "leimen",
        "dossenheim", "schriesheim", "weinheim", "hoppenheim", "ladenburg",
        "edingen-neckarhausen", "ilvesheim", "heddesheim", "hockenheim",
        "altlußheim", "neulußheim", "brühl", "ketsch", "plankstadt",
        "schwetzingen", "offenau", "gundelsheim", "haßmersheim", "mosbach",
        "neunkirchen", "waldbrunn", "zwingenberg", "hirschhorn",
        "neckarsteinach", "schönbrunn", "bammental", "mauer", "wiesenbach",
        "spechbach", "epfenbach", "reichartshausen", "baden-baden", "bühl",
        "achern", "oberkirch", "offenburg", "lahr", "freiburg", "müllheim",
        "weil am rhein", "lörrach", "rheinfelden", "schopfheim",
        "zell im wiesental", "todtnau", "schönau im schwarzwald",
        "titisee-neustadt", "hinterzarten", "feldberg", "schluchsee",
        "bonndorf", "waldshut-tiengen", "bad säckingen", "laufenburg",
        "stein am rhein", "schaffhausen", "konstanz", "kreuzlingen",
        "radolfzell", "überlingen", "friedrichshafen", "lindau", "kempten",
        "memmingen", "kaufbeuren", "füssen", "garmisch-partenkirchen",
        "murnau", "weilheim", "starnberg", "herrsching", "germering",
        "garching", "neufahrn", "eching", "freising", "erding",
        "markt schwaben", "poing", "grafing", "zorneding", "kirchseeon",
        "ebersberg", "wasserburg", "rosenheim", "bad aibling", "kolbermoor",
        "raubling", "brannenburg", "kufstein", "wörgl", "kitzbühel",
        "st. johann in tirol", "saalfelden", "zell am see", "mittersill",
        "mayrhofen", "jenbach", "schwaz", "hall in tirol", "wattens",
        "fügen", "zillertal", "ramsau", "schladming", "liezen", "admont",
        "eisenerz", "leoben", "bruck an der mur", "kapfenberg",
        "mürzzuschlag", "krippenstein", "obertraun", "bad ischl", "gmunden",
        "traunsee", "vöcklabruck", "wels", "linz", "steyr", "enns",
        "amstetten", "sankt pölten", "tulln", "klosterneuburg", "korneuburg",
        "stockerau", "mistelbach", "hollabrunn", "retz", "znojmo",
        "břeclav", "hodonín", "kroměříž", "olomouc", "přerov", "prostějov",
        "šumperk", "jeseník", "krnov", "bruntál", "opava", "ostrava",
        "havířov", "karviná", "český těšín", "trinec", "frýdek-místek",
        "nový jičín", "valašské meziříčí", "vsetín", "zlín", "kroměříž",
        "uherské hradiště", "hodonín", "břeclav", "mikulov", "znojmo",
        "jihlava", "havlíčkův brod", "chotěboř", "žďár nad sázavou",
        "velké meziříčí", "třebíč", "telč", "slavonice", "jindřichův hradec",
        "tábor", "písek", "strakonice", "prachatice", "vimperk",
        "český krumlov", "kaplice", "vyšší brod", "lippstadt", "gütersloh",
        "bielefeld", "herford", "bad salzuflen", "lemgo", "detmold",
        "höxter", "warburg", "marsberg", "brilon", "meschede", "arnsberg",
        "sundern", "neheim-hüsten", "menden", "balve", "iserlohn",
        "lüdenscheid", "meinerzhagen", "kierspe", "halver", "schalksmühle",
        "plettenberg", "attendorn", "olpe", "lennestadt", "kirchhundem",
        "finnentrop", "schmallenberg", "winterberg", "medebach", "hallenberg",
        "wenden", "freudenberg", "siegen", "kreuztal", "netphen",
        "hilchenbach", "bad berleburg", "bad laasphe", "burbach",
        "wilkensdorf", "haiger", "dillenburg", "herborn", "wetzlar",
        "giessen", "butzbach", "friedberg", "oberursel", "kronberg",
        "königstein", "kelkheim", "hofheim", "flörsheim", "hochheim",
        "raunheim", "kelsterbach", "nauheim", "büttelborn", "griesheim",
        "bickenbach", "seeheim-jugenheim", "zwingenberg", "lorsch", "biblis",
        "gernsheim", "biebesheim", "stockstadt", "aschaffenburg", "goldbach",
        "hösbach", "lindenberg", "alzenau", "kahl am main", "seligenstadt",
        "babenhausen", "dieburg", "groß-umstadt", "höchst im odenwald",
        "bad könig", "michelstadt", "erbach", "beerfelden", "kirchheim",
        "rohrbach", "handschuhsheim", "wieblingen", "angelbachtal",
        "zuzenhausen", "eschelbronn", "neidenstein", "siegelsbach",
        "itilingen", "bad wimpfen", "binau", "felsenberg", "lindelbach",
        "billigheim", "schefflenz", "adelsheim", "seckach", "buchen",
        "walldürn", "hardheim", "külsheim", "wertheim", "marktheidenfeld",
        "lohr am main", "gemünden", "karlstadt", "arnstein", "hammelburg",
        "bad kissingen", "bad brückenau", "wildflecken", "fulda", "hünfeld",
        "bad hersfeld", "bebra", "rottenburg an der fulda",
        "bad soden-salmünster", "schlüchtern", "steinau an der straße",
        "gelnhausen", "wächtersbach", "bad orb", "birstein", "gedern",
        "schotten", "laubach", "grünberg", "hungen", "nidda", "büdingen",
        "hanau", "bruchköbel", "langenselbold", "erlensee", "schöneck",
        "niederdorfelden", "karben", "bad vilbel", "rosbach", "ober-mörlen",
        "münzenberg", "linden", "pohlheim", "braunfels", "leun", "solms",
        "aßlar", "ehringshausen", "braunfels", "wuppertal", "remscheid",
        "solingen", "hilden", "haan", "erkrath", "mettmann", "wülfrath",
        "velbert", "heiligenhaus", "ratingen", "grevenbroich",
        "rommerskirchen", "dormagen", "zons", "neuss", "korschenbroich",
        "jüchen", "pulheim", "frechen", "hürth", "wesseling", "bornheim",
        "swisttal", "weilerswist", "euskirchen", "zülpich",
        "bad münstereifel", "mechernich", "schleiden", "kall", "hellenthal",
        "nideggen", "heimbach", "monschau", "simmerath", "roetgen",
        "aachen", "würselen", "herzogenrath", "übach-palenberg",
        "geilenkirchen", "heinsberg", "nettetal", "grefrath", "kempen",
        "business bay", "east london", "north carolina", "south carolina",
        "north dakota", "south dakota", "north hollywood", "west hollywood",
        "south beach", "new south wales", "north rhine-westphalia",
        "newcastle upon tyne", "stratford-upon-avon", "sutton coldfield",
        "west midlands", "east midlands", "north yorkshire", "west yorkshire",
        "south yorkshire", "east sussex", "west sussex", "northamptonshire",
        "wellington", "stockholm", "new delhi", "são leopoldo",
        "greater london", "greater manchester", "greater china",
        "greater tokyo", "greater toronto", "greater boston",
    }

    # Single-word known cities (broad global + EU coverage)
    KNOWN_CITIES = {
        "amsterdam", "berlin", "hamburg", "munich", "cologne", "frankfurt",
        "stuttgart", "dusseldorf", "dortmund", "essen", "leipzig", "dresden",
        "nuremberg", "bremen", "mannheim", "heidelberg", "karlsruhe",
        "freiburg", "bonn", "mainz", "wiesbaden", "kiel", "rostock",
        "magdeburg", "erfurt", "potsdam", "walldorf", "veldhoven", "eindhoven",
        "utrecht", "groningen", "tilburg", "almere", "breda", "nijmegen",
        "haarlem", "arnhem", "delft", "leiden", "rotterdam", "den haag",
        "london", "manchester", "birmingham", "leeds", "liverpool",
        "newcastle", "sheffield", "bristol", "nottingham", "leicester",
        "southampton", "portsmouth", "brighton", "edinburgh", "glasgow",
        "cardiff", "belfast", "oxford", "cambridge", "york", "bath",
        "aberdeen", "dundee", "reading", "coventry", "plymouth", "derby",
        "swansea", "luton", "milton keynes", "northampton", "watford",
        "bournemouth", "norwich", "exeter", "cheltenham", "salzburg", "graz",
        "linz", "innsbruck", "vienna", "zurich", "geneva", "basel",
        "lausanne", "bern", "lugano", "milan", "milano", "rome", "roma",
        "naples", "napoli", "turin", "torino", "palermo", "genoa", "bologna",
        "florence", "venice", "verona", "bari", "trieste", "brescia",
        "parma", "modena", "alba", "cagliari", "catania", "livorno",
        "ravenna", "rimini", "ancona", "udine", "vicenza", "bergamo",
        "bolzano", "trento", "pisa", "siena", "lucca", "prato", "ferrara",
        "pescara", "lecce", "monza", "como", "asti", "novara", "la spezia",
        "treviso", "rovigo", "mantova", "cremona", "pavia", "varese",
        "biella", "vercelli", "cuneo", "savona", "agordo", "charenton",
        "warsaw", "krakow", "lodz", "wroclaw", "poznan", "gdansk", "szczecin",
        "bydgoszcz", "lublin", "katowice", "bialystok", "gdynia",
        "czestochowa", "radom", "torun", "rzeszow", "kielce", "olsztyn",
        "prague", "brno", "ostrava", "plzen", "liberec", "olomouc",
        "pardubice", "budapest", "debrecen", "szeged", "miskolc", "pecs",
        "gyor", "bucharest", "cluj", "timisoara", "iasi", "constanta",
        "craiova", "brasov", "galati", "ploiesti", "oradea", "braila",
        "arad", "sibiu", "bacau", "satu mare", "sophia", "sofia", "plovdiv",
        "varna", "burgas", "ruse", "stara zagora", "pleven", "sliven",
        "dobrich", "shumen", "pernik", "athens", "thessaloniki", "patras",
        "larissa", "heraklion", "volos", "chania", "rhodes", "stockholm",
        "gothenburg", "malmo", "uppsala", "vasteras", "orebro", "linkoping",
        "helsingborg", "jonkoping", "norrkoping", "lund", "umea", "gavle",
        "boras", "oslo", "bergen", "trondheim", "stavanger", "drammen",
        "fredrikstad", "kristiansand", "tromso", "copenhagen", "aarhus",
        "odense", "aalborg", "esbjerg", "randers", "kolding", "horsens",
        "vejle", "roskilde", "herning", "silkeborg", "helsinki", "espoo",
        "tampere", "vantaa", "oulu", "turku", "jyvaskyla", "lahti",
        "kuopio", "tallinn", "tartu", "narva", "riga", "daugavpils",
        "liepaja", "vilnius", "kaunas", "klaipeda", "siauliai", "dublin",
        "cork", "limerick", "galway", "waterford", "kilkenny", "brussels",
        "antwerp", "ghent", "charleroi", "liege", "bruges", "namur",
        "leuven", "luxembourg", "singapore", "tokyo", "osaka", "kyoto",
        "yokohama", "nagoya", "sapporo", "fukuoka", "kobe", "hiroshima",
        "seoul", "busan", "incheon", "daegu", "daejeon", "gwangju",
        "suwon", "shanghai", "beijing", "shenzhen", "guangzhou", "chengdu",
        "hangzhou", "wuhan", "xian", "nanjing", "chongqing", "suzhou",
        "tianjin", "qingdao", "dalian", "ningbo", "xiamen", "hong kong",
        "taipei", "kaohsiung", "taichung", "tainan", "hsinchu", "linkou",
        "bangkok", "kuala lumpur", "penang", "jakarta", "surabaya",
        "bandung", "manila", "cebu", "davao", "makati", "ho chi minh",
        "hanoi", "da nang", "mumbai", "delhi", "new delhi", "bengaluru",
        "hyderabad", "chennai", "kolkata", "pune", "ahmedabad", "jaipur",
        "surat", "lucknow", "kanpur", "nagpur", "indore", "bhopal",
        "visakhapatnam", "patna", "vadodara", "agra", "nashik", "meerut",
        "rajkot", "varanasi", "srinagar", "amritsar", "guwahati",
        "chandigarh", "gurgaon", "gurugram", "noida", "kochi",
        "coimbatore", "madurai", "mangalore", "mysore", "sydney",
        "melbourne", "brisbane", "perth", "adelaide", "canberra", "hobart",
        "geelong", "townsville", "cairns", "auckland", "wellington",
        "christchurch", "hamilton", "dunedin", "victoria", "saskatoon",
        "regina", "johannesburg", "cape town", "durban", "pretoria",
        "lagos", "abuja", "accra", "nairobi", "cairo", "alexandria",
        "casablanca", "rabat", "marrakech", "doha", "dubai", "abu dhabi",
        "sharjah", "riyadh", "jeddah", "dammam", "kuwait city", "manama",
        "muscat", "tel aviv", "jerusalem", "haifa", "beirut", "amman",
        "istanbul", "ankara", "izmir", "bursa", "antalya", "tehran",
        "tbilisi", "yerevan", "baku", "almaty", "astana", "tashkent",
        "islamabad", "karachi", "lahore", "dhaka", "colombo", "nicosia",
        "limassol", "valletta", "reykjavik", "new york", "los angeles",
        "chicago", "houston", "phoenix", "philadelphia", "san antonio",
        "san diego", "dallas", "san jose", "austin", "jacksonville",
        "columbus", "charlotte", "indianapolis", "seattle", "denver",
        "washington", "boston", "nashville", "detroit", "portland",
        "las vegas", "memphis", "louisville", "baltimore", "milwaukee",
        "albuquerque", "tucson", "fresno", "sacramento", "kansas city",
        "atlanta", "miami", "omaha", "raleigh", "cincinnati", "cleveland",
        "pittsburgh", "minneapolis", "tampa", "orlando", "newark",
        "cambridge", "auburn hills", "dearborn", "palo alto", "mountain view",
        "sunnyvale", "santa clara", "redwood city", "menlo park", "emeryville",
        "oakland", "berkeley", "irvine", "santa monica", "culver city",
        "burbank", "glendale", "pasadena", "long beach", "toronto",
        "montreal", "vancouver", "calgary", "ottawa", "edmonton", "winnipeg",
        "halifax", "mississauga", "brampton", "markham", "waterloo",
        "kitchener", "mexico city", "guadalajara", "monterrey", "sao paulo",
        "sao leopoldo", "rio de janeiro", "buenos aires", "santiago",
        "bogota", "lima", "montevideo", "lisbon", "porto", "braga",
        "coimbra", "faro", "aveiro", "guimaraes", "madrid", "barcelona",
        "valencia", "seville", "bilbao", "zaragoza", "malaga", "granada",
        "palma", "alicante", "paris", "lyon", "marseille", "toulouse",
        "nice", "nantes", "strasbourg", "bordeaux", "lille", "rennes",
        "grenoble", "montpellier", "hannover", "aachen", "kiel", "lubeck",
        "wiesbaden", "erlangen", "würzburg", "ingolstadt", "regensburg",
        "garching", "herndon", "kokomo", "newtown", "sterling heights",
        "tempe", "toledo", "chelsea", "middlesex", "aurora", "appleton",
        "hsinchu", "linkou", "agordo", "charenton", "kv", "kyiv", "lviv",
        "odessa", "kharkiv", "dnipro", "zaporizhzhia", "minsk", "chișinău",
        "batumi", "yerevan", "tbilisi", "bishkek", "dushanbe", "ashgabat",
    }

    # Words/phrases that must NEVER be accepted as a location
    LOCATION_REJECT_PHRASES = [
        "learn more", "read more", "view more", "show more", "load more",
        "more results", "share", "apply now", "apply", "details",
        "public sector", "financial services", "internal services",
        "customer services", "customer service", "information technology",
        "field operations", "supply chain", "business development",
        "people team", "talent team", "marketing & communications",
        "sunglass hut", "target optical", "for eyes", "vogue eyewear",
        "ikea store", "living rooms", "human resources", "life at",
        "about us", "career areas", "open positions", "job alerts",
        "job alert", "privacy policy", "terms of use", "cookie policy",
        "stay connected", "talent community", "join our", "work with us",
        "find the job", "all vacancies", "play store", "app store",
        "manage preferences", "recruitment fraud", "code of ethics",
        "code of conduct", "call us", "contact us", "join us", "more",
        "next page", "previous page", "back to top", "all jobs",
        "job search", "search", "browse", "filter", "sort", "view all",
        "vice president", "wholesale banking", "enterprise architecture",
        "power distribution", "transformation value management",
        "revenue growth management", "asset management", "cost management",
        "contact centre", "contact center", "intelligent automation",
        "workforce planning", "network planning", "database engine internals",
        "candy crush saga", "orbit program", "pearle vision",
        "orlen eye care", "walmart confections", "hazelnut company",
        "valley fair mall", "gurnee mills", "warranty kokomo engine plant",
        "warranty dundee engine plant", "wise buisness", "wise account",
        "china outbound", "belgium market", "protected categories",
        "women's health", "wind turbines", "front line", "cust svc",
        "western region", "eastern region", "northern region",
        "southern region", "greater china region", "orbit program",
    ]

    LOCATION_REJECT_WORDS = [
        "share", "more", "apply", "details", "linkedin", "facebook",
        "twitter", "instagram", "youtube", "pinterest", "tiktok",
        "marketing", "sales", "operations", "engineering", "finance",
        "legal", "insurance", "hr", "people", "talent", "product",
        "design", "security", "audit", "tax", "support", "communications",
        "facilities", "business", "infrastructure", "systems", "procurement",
        "logistics", "warehouse", "strategy", "recruitment", "compliance",
        "commerce", "retail", "corporate", "administration", "accounting",
        "analytics", "data", "cloud", "platform", "solutions", "services",
        "internal", "customer", "manufacturing", "public", "sector",
        "financial", "technology", "information", "central", "north",
        "south", "east", "west", "dach", "emea", "latam", "apac", "mena",
        "ind", "flex", "gtm", "csm", "rxo", "gqe", "cdi", "cdd",
        "nightshift", "shift", "store", "stores", "markthalle",
        "verkäufer", "verkaeufer", "mitarbeiter", "mitarbeiterin",
        "berater", "kaufmann", "kauffrau", "techniker", "ingenieur",
        "assistent", "leiter", "sachbearbeiter", "vendeur", "vendeuse",
        "collaborateur", "collaboratrice", "employé", "employe", "hôte",
        "hôtesse", "commesso", "commessa", "addetto", "addetta",
        "impiegato", "stagista", "tirocinante", "operaio", "operatore",
        "jobdetail", "externaljobs", "jobsuche", "praxissoftware",
        "lenscrafters", "lenscrafter", "oakley", "opsm", "ray-ban",
        "persol", "eyemed", "glasses", "career", "careers", "job", "jobs",
        "vacancy", "vacancies", "position", "positions", "opening",
        "openings", "role", "roles", "requisition", "posting", "hiring",
        "recruiting", "graduate", "students", "interns", "trainee",
        "trainees", "scholarship", "stipend", "internship", "stage",
        "praktikum", "apprenticeship", "apprentice", "freelance",
        "commission", "location", "locations", "workplace", "department",
        "departments", "team", "teams", "division", "unit", "area",
        "sector", "office", "headquarters", "campus", "hub", "site",
        "onboarding", "welcome", "register", "signup", "login", "logout",
        # languages / descriptors that are never locations
        "french", "german", "italian", "spanish", "portuguese", "dutch",
        "polish", "swedish", "danish", "norwegian", "finnish", "greek",
        "czech", "hungarian", "romanian", "bulgarian", "croatian", "serbian",
        "ukrainian", "russian", "turkish", "arabic", "chinese", "japanese",
        "korean", "hindi", "bengali", "thai", "vietnamese", "indonesian",
        "malay", "flemish", "swiss", "british", "american", "canadian",
        "australian", "irish", "scottish", "welsh", "english", "speaking",
        "speaker", "fluent", "native", "bilingual", "multilingual",
        "language", "international", "federal", "civilian", "regional",
        "national", "global", "worldwide", "hq", "headquarter",
        "greater", "metropolitan", "downtown", "uptown", "midtown",
        # workload / schedule words (German/Italian included)
        "vollzeit", "teilzeit", "seasonal", "virtual", "minijob", "aushilfe",
        "schicht", "nacht", "turno", "fulltime", "parttime",
        # tech stacks / skills — never locations
        "java", "javascript", "python", "azure", "aws", "gcp", "sql",
        "kubernetes", "docker", "terraform", "react", "angular", "node",
        "networking", "database", "sap", "salesforce", "oracle", "linux",
        "windows", "machine learning", "artificial intelligence",
        # departments / business units / generic nouns
        "hotels", "banking", "wholesale", "credit", "cards", "payments",
        "fincrime", "sanctions", "deactivations", "assets", "consumer",
        "development", "programs", "programme", "specialisation",
        "specialization", "growth", "upsell", "experimentation", "technical",
        "electrical", "construction", "mechanical", "treasury", "trade",
        "market", "outbound", "inbound", "account", "buisness", "business",
        "manag", "cust", "svc", "network", "payroll", "transformation",
        "revenue", "cost management", "contact", "intelligent", "workforce",
        "warranty", "plant", "engine", "region", "area", "division",
        "program", "project", "portfolio", "governance", "risk", "fraud",
        "collections", "billing", "invoicing", "vendor", "supplier",
        "merchandising", "planning", "scheduling", "inventory", "fleet",
        "dispatch", "staffing", "compensation", "channel", "alliance",
        "east", "west", "north", "south", "northeast", "northwest",
        "southeast", "southwest", "eastern", "western", "northern",
        "southern", "central", "midwest", "anywhere", "worldwide", "global",
        "international", "federal", "civilian", "national", "regional",
        "local", "virtual", "digital", "center", "centre",
        # store brands / product / program names
        "mack", "ram", "jeep", "dodge", "chrysler", "fiat", "lancia",
        "abarth", "alfa", "maserati", "opel", "vauxhall", "peugeot",
        "citroen", "cymer", "candy crush", "macys", "macy's", "cabela's",
        "walmart", "eyebuydirect", "pearle vision", "orlen eye care",
        "gurnee mills", "valley fair", "hazelnut", "engawa",
        "wise account", "wise buisness", "protected categories",
        "women's health", "wind turbines", "mall", "mills", "company",
        "corp", "inc", "ltd", "gmbh", "ag", "spa", "llc", "plc",
    ]

    # Phrases that are NEVER job titles even on their own (dropped by title cleaning)
    PURE_CONTRACT_PHRASES = {
        "fixed term", "fixed-term", "fixed term contract", "permanent",
        "temporary", "temporaire", "contract", "full time", "full-time",
        "part time", "part-time", "internship", "trainee", "apprenticeship",
        "secondment", "stage", "cdi", "cdd", "temporary contract",
        "permanent contract", "open position", "open positions",
        "apply now", "apply", "more", "learn more", "read more",
        "view more", "show more", "load more", "job description",
        "job details", "all genders", "m/f/d", "m/w/d", "w/m/d",
        "d/f/m", "f/m/d", "m/f/x", "w/m/x", "m/w/x",
    }

    # Exact department/boilerplate titles that must never be kept as a job title
    DEPT_AS_TITLE = {
        "sales & commercial", "sales and commercial", "retail banking sales",
        "corporate banking", "private banking", "financial services",
        "internal services", "customer services", "information technology",
        "public sector", "risk management", "marketing & communications",
        "data & analytics", "data and analytics", "operations", "manufacturing",
        "engineering", "finance", "marketing", "sales", "legal", "human resources",
        "product", "design", "insurance", "retail", "store operations",
        "communications", "logistics", "supply chain", "customer service",
        "customer success", "field operations", "expertise areas", "commercial",
        "retail operations", "store", "stores", "nightshift", "cdi", "cdd",
        "sales & commercial assistant", "store management", "merchandising",
        "quality & lean", "quality and lean", "food & beverage", "food and beverage",
        "night shift", "nightshift", "recovery", "customer relations",
        "visual merchandising", "food service", "bakery", "deli", "produce",
        "cashier", "checkout", "front end", "back end", "fresh food",
        "customer experience", "ecommerce", "e-commerce", "fulfillment",
    }

    # Companies where the HQ fallback must NOT be stamped (multi-location / global)
    HQ_FALLBACK_EXCEPTIONS = {
        "ASML", "Hays Germany", "Ferrero", "Anymind Group", "Luxottica",
        "Ikea Italia", "Siemens", "SAP", "Stripe", "Databricks",
        "American Express", "Amazon Italia", "Nigel Frank", "Harnham Germany",
        "Michael Page Germany", "Michael Page UK", "Michael Page Netherlands",
        "ING", "Revolut", "Wise", "SumUp", "Optiver", "Stellantis", "Enel",
        "Poste Italiane", "Generali", "Intesa Sanpaolo", "UniCredit",
        "Morgan McKinley", "Robert Walters Germany", "Robert Walters Ireland",
        "Robert Walters Netherlands", "Kelly Services Germany",
        "Sigmar Recruitment", "Understanding Recruitment",
        "Reperio Human Capital", "Klarna", "Spotify", "Booking.com",
        "Deliveroo", "Glovo", "Bolt", "HelloFresh", "Ocado Technology",
        "King", "Skyscanner", "Eni", "TIM", "SNAM", "McDonald's Italia",
        "Decathlon Italia Retail", "Conad", "Coop Italia", "Esselunga",
        "Eurospin", "Lidl Italia", "Pam Panorama", "FS Italiane / Trenitalia",
        "Barilla Group", "Lavazza", "Angelini Pharma", "Organon",
        "MSD Netherlands", "Huxley Netherlands", "Undutchables", "La Fosse",
        "Talentor Germany", "DevsData", "MetaQuotes", "Exness",
        "Scorewarrior", "Morgan McKinley", "Hays Germany", "Siemens",
        "Luxottica", "Stellantis", "American Express",
    }

    # Extended country/region list — the original set was missing many countries
    # (ukraine, romania, greece, sweden, brazil, ...). Merged into
    # COUNTRIES_AND_REGIONS at runtime.
    REGIONS_EXTRA = {
        # Europe
        "ukraine", "belarus", "moldova", "romania", "bulgaria", "greece",
        "hungary", "czechia", "czech republic", "slovakia", "slovenia",
        "croatia", "serbia", "bosnia", "bosnia and herzegovina",
        "north macedonia", "montenegro", "albania", "kosovo", "georgia",
        "armenia", "azerbaijan", "turkey", "cyprus", "malta", "iceland",
        "luxembourg", "monaco", "andorra", "san marino", "liechtenstein",
        "scandinavia", "baltics", "baltic states", "benelux", "nordics",
        "balkans", "sweden", "denmark", "norway", "finland", "austria",
        "switzerland", "belgium", "ireland", "estonia", "latvia", "lithuania",
        "poland", "czech", "czechia", "portugal", "canada", "australia",
        "netherlands", "germany", "italy", "france", "spain", "japan",
        "china", "india", "singapore", "usa", "uk", "united kingdom",
        "united states",
        # Americas
        "brazil", "argentina", "chile", "colombia", "peru", "uruguay",
        "paraguay", "bolivia", "ecuador", "venezuela", "guyana", "suriname",
        "mexico", "cuba", "dominican republic", "jamaica", "puerto rico",
        "panama", "costa rica", "guatemala", "honduras", "el salvador",
        "nicaragua", "belize", "trinidad", "central america",
        "latin america",
        # Middle East / Africa
        "israel", "palestine", "uae", "united arab emirates", "qatar",
        "saudi arabia", "kuwait", "bahrain", "oman", "jordan", "lebanon",
        "syria", "iraq", "iran", "yemen", "egypt", "morocco", "algeria",
        "tunisia", "libya", "sudan", "ethiopia", "nigeria", "ghana",
        "kenya", "tanzania", "uganda", "senegal", "ivory coast",
        "cote d'ivoire", "cameroon", "zimbabwe", "zambia", "botswana",
        "namibia", "mozambique", "angola", "rwanda", "south africa",
        "north africa", "west africa", "east africa",
        "sub-saharan africa",
        # Asia / Oceania
        "south korea", "taiwan", "thailand", "vietnam", "indonesia",
        "malaysia", "philippines", "myanmar", "cambodia", "laos",
        "mongolia", "nepal", "sri lanka", "bangladesh", "pakistan",
        "afghanistan", "kazakhstan", "uzbekistan", "kyrgyzstan",
        "tajikistan", "turkmenistan", "new zealand", "fiji",
        "papua new guinea", "new caledonia", "french polynesia",
        # Generic regions
        "europe", "asia", "africa", "oceania", "global", "worldwide",
    }

    # Known typos/OCR artifacts in job-board location strings
    TYPO_MAP = {
        "fort laurderdale": "fort lauderdale",
        "fort lauderale": "fort lauderdale",
        "garching bei munchen": "garching bei münchen",
    }

    # Public ATS job-board API fallbacks for companies whose career pages are
    # JS-heavy or blocked. Verified working 2026-08-06:
    #   Ashby: Lightspeed, Forto, Rows (Rowspace), Planhat
    #   Greenhouse: HelloFresh, Skyscanner, Catawiki
    ATS_FALLBACK = {
        "HelloFresh": {"greenhouse": ["hellofresh"]},
        "Skyscanner": {"greenhouse": ["skyscanner"]},
        "Catawiki": {"greenhouse": ["catawiki"]},
        "Rows": {"ashby": ["Rowspace", "rows"]},
        "Planhat": {"ashby": ["Planhat", "planhat"]},
        "Lightspeed": {"ashby": ["Lightspeed", "lightspeed"]},
        "Forto": {"ashby": ["Forto", "forto"]},
        "Retool": {"ashby": ["Retool", "retool"]},
        "Doist": {"ashby": ["Doist", "doist"], "lever": ["doist"]},
        "Pitch": {"ashby": ["Pitch", "pitch"], "lever": ["pitch"]},
        "Spendesk": {"personio": ["spendesk"]},
        "Freeletics": {"personio": ["freeletics"]},
        "Generali": {"greenhouse": ["generali"]},
        "Bynder": {"ashby": ["Bynder", "bynder"]},
        "Buena": {"ashby": ["Buena", "buena"]},
    }

    # Casing overrides (uk -> UK etc.)
    CASING_MAP = {
        "uk": "UK", "usa": "USA", "us": "US", "uae": "UAE", "eu": "EU",
        "apac": "APAC", "emea": "EMEA", "latam": "LATAM", "dach": "DACH",
        "mena": "MENA", "sa": "SA", "in": "IN", "de": "DE", "it": "IT",
        "fr": "FR", "es": "ES", "nl": "NL", "pl": "PL", "pt": "PT",
        "se": "SE", "no": "NO", "dk": "DK", "fi": "FI", "at": "AT",
        "ch": "CH", "be": "BE", "ie": "IE", "cn": "CN", "jp": "JP",
        "kr": "KR", "sg": "SG", "au": "AU", "ca": "CA", "mx": "MX",
        "br": "BR", "ar": "AR", "cl": "CL", "co": "CO", "pe": "PE",
        "za": "ZA", "ng": "NG", "ke": "KE", "eg": "EG", "ma": "MA",
        "il": "IL", "tr": "TR", "ae": "AE", "qa": "QA",
    }

    # Seed URL corrections for broken entries
    SEED_URL_OVERRIDES = {
        "SNAM": "https://carriere.snam.it/",
        "Pam Panorama": "https://lavoraconnoi.gruppopam.it/hr-jobsite/",
        "Eni": "https://www.eni.com/en-IT/careers.html",
    }

    # URL path segments that are UI routes, never locations
    URL_PATH_SEGMENT_BLACKLIST = {
        "jobdetail", "externaljobs", "jobsuche", "search", "search-results",
        "searchjobs", "careers", "career", "jobs", "job", "vacancies",
        "vacancy", "openings", "positions", "position", "results", "list",
        "page", "department", "departments", "locations", "location",
        "detail", "show", "index", "home", "apply", "form", "new",
        "requisition", "posting", "role", "o", "all", "browse", "filter",
        "category", "categories", "jobsearch", "jobsuche", "talent",
        "people", "about", "contact", "faq", "help", "privacy", "terms",
    }

    URL_JOB_MARKERS = {
        "job", "jobs", "o", "role", "vacancy", "vacancies", "position",
        "positions", "posting", "requisition", "career", "careers",
        "opening", "openings", "apply", "stellenangebot", "stelle",
        "lavoro", "posizioni", "annuncio", "offerta", "opportunity",
        "opportunities",
    }

    # Optional detail-page scan (off by default; enable with --detail)
    ENABLE_DETAIL_SCAN = False
    DETAIL_SCAN_TIMEOUT_MS = 12000
    DETAIL_SCAN_TIME_BUDGET_SEC = 480   # max seconds one company's detail scan may run (8 min)
    MAIN_HEARTBEAT_SEC = 30             # main thread prints how many companies are still running
    MAX_STALL_SEC = 600             # abort ONLY when NO page-level ACTIVITY anywhere for 10 min
                                    # (queued companies waiting for a worker slot are NOT a hang)
    MAX_DETAIL_SCAN_PER_COMPANY = 120
    MAX_DETAIL_SCAN_TOTAL = 3000

# ───────────── JD SUPPORT DETECTOR (shared) ─────────────
# Single source of truth moved to sponsorscout.scanning.jd_support.
from sponsorscout.scanning.jd_support import (
    JDSupportDetector,
    VERDICT_YES,
    VERDICT_NO,
    VERDICT_UNKNOWN,
    detect_blue_card,
)

# ───── legacy comment block retained below for historical context ─────
# Context-aware detection of Visa Sponsorship / Relocation Support in JD text.
# Never matches keywords alone: every mention is judged within its sentence/
# clause, with negation / requirement / conditional / scope qualifiers.
#   "We do NOT support relocation"              -> No      (negated)
#   "We support if you are READY to relocate"   -> No      (candidate must move)
#   "may be provided case-by-case"              -> Unknown (conditional)
# ───────────────────────── SCANNER ─────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# SEED UPGRADE TABLE (v7 final)
#
# The v7 scanner reads either schema:
#   • v7  (seed_name, canonical_name, source_type, target_country, scope_policy,
#          provider, board_slug, careers_url, ...)
#   • v6  (name, ats_type, careers_url, industry, sponsorship_history,
#          english_friendly, remote_score)
#
# A v6 seed carries none of the v7 metadata (recruiter tagging, country scope,
# provider/board slugs) and several rows carry wrong or placeholder URLs. Rather
# than fail or silently degrade, the scanner upgrades known v6 rows in-memory
# using this table. Every applied correction is logged to stdout and recorded in
# the per-run scan log so nothing is hidden.
#
# Keyed by seed `name` (case-insensitive). Omit a key and the row keeps v6
# defaults (direct_employer / Global / global / auto).
# ─────────────────────────────────────────────────────────────────────────────
SEED_UPGRADE = {
    # ── Recruiters: separate file + country scope ────────────────────────────
    "DevsData":                     {"source_type": "recruiter"},
    "Harnham Germany":              {"source_type": "recruiter", "target_country": "Germany", "scope_policy": "job_location"},
    "Hays Germany":                 {"source_type": "recruiter", "target_country": "Germany", "scope_policy": "seed_url"},
    "Huxley Netherlands":           {"source_type": "recruiter", "target_country": "Netherlands", "scope_policy": "seed_url"},
    "Kelly Services Germany":       {"source_type": "recruiter", "target_country": "Germany", "scope_policy": "job_location"},
    "La Fosse":                     {"source_type": "recruiter"},
    "Michael Page Germany":         {"source_type": "recruiter", "target_country": "Germany", "scope_policy": "seed_url"},
    "Michael Page Netherlands":     {"source_type": "recruiter", "target_country": "Netherlands", "scope_policy": "seed_url"},
    "Michael Page UK":              {"source_type": "recruiter", "target_country": "United Kingdom", "scope_policy": "seed_url"},
    "Morgan McKinley":              {"source_type": "recruiter"},
    "Nigel Frank":                  {"source_type": "recruiter"},
    "Reperio Human Capital":        {"source_type": "recruiter"},
    "Robert Walters Germany":       {"source_type": "recruiter", "scope_policy": "seed_url"},
    "Robert Walters Ireland":       {"source_type": "recruiter", "target_country": "Ireland", "scope_policy": "seed_url"},
    "Robert Walters Netherlands":   {"source_type": "recruiter", "target_country": "Netherlands", "scope_policy": "seed_url"},
    "Sigmar Recruitment":           {"source_type": "recruiter"},
    "Talentor Germany":             {"source_type": "recruiter", "target_country": "Germany", "scope_policy": "job_location"},
    "Understanding Recruitment":    {"source_type": "recruiter"},
    "Undutchables":                 {"source_type": "recruiter"},
    # ── Direct employers: country scope ──────────────────────────────────────
    "Amazon Italia":                {"target_country": "Italy", "scope_policy": "seed_url"},
    "Coop Italia":                  {"target_country": "Italy", "scope_policy": "seed_url",
                                     "careers_url": "https://lavoro.coopalleanza3-0.it/jobs.php"},
    "Decathlon Italia Retail":      {"target_country": "Italy", "scope_policy": "seed_url"},
    "Enel":                         {"target_country": "Italy", "scope_policy": "seed_url"},
    "Ikea Italia":                  {"target_country": "Italy", "scope_policy": "job_location"},
    "McDonald's Italia":            {"target_country": "Italy", "scope_policy": "seed_url"},
    "MSD Netherlands":              {"target_country": "Netherlands", "scope_policy": "job_location"},
    "Nexthink (Germany)":           {"target_country": "Germany", "scope_policy": "job_location"},
    "Pam Panorama":                 {"target_country": "Italy", "scope_policy": "seed_url"},
    # ── NEW: Italian hotels/retail added 2026-09-05 ───────────────────────────
    "Eataly Italia":                {"target_country": "Italy", "scope_policy": "seed_url"},
    "Gruppo UNA":                   {"target_country": "Italy", "scope_policy": "seed_url"},
    "NH Hotel Group Italy":         {"target_country": "Italy", "scope_policy": "job_location",
                                     "notes": "URL is generic minorhotels.com/search; job_location scope "
                                              "ensures only Italy-scoped jobs pass"},
    "Oniverse":                     {"target_country": "Italy", "scope_policy": "seed_url"},
    "OVS":                          {"target_country": "Italy", "scope_policy": "seed_url"},
    "Starhotels":                   {"target_country": "Italy", "scope_policy": "seed_url"},
    # ── Provider API (avoids fragile DOM scraping) ───────────────────────────
    "Airbyte":                      {"provider": "ashby", "board_slug": "airbyte"},
    "American Express":             {"provider": "oracle"},
    "Appodeal":                     {"provider": "greenhouse", "board_slug": "appodeal"},
    "Babbel":                       {"provider": "ashby", "board_slug": "Babbel"},
    "Buena":                        {"provider": "ashby", "board_slug": "Buena"},
    "Bynder":                       {"provider": "ashby", "board_slug": "Bynder"},
    "Catawiki":                     {"provider": "greenhouse", "board_slug": "catawiki",
                                     "careers_url": "https://job-boards.greenhouse.io/catawiki"},
    "Choco":                        {"provider": "ashby", "board_slug": "Choco"},
    "Doist":                        {"provider": "ashby", "board_slug": "Doist"},
    "Forto":                        {"provider": "ashby", "board_slug": "Forto"},
    "HelloFresh":                   {"provider": "greenhouse", "board_slug": "hellofresh"},
    "Klarna":                       {"provider": "deel"},
    "KONUX":                        {"provider": "greenhouse", "board_slug": "KONUX"},
    "Lightspeed":                   {"provider": "ashby", "board_slug": "Lightspeed"},
    "Notion":                       {"provider": "ashby", "board_slug": "notion"},
    "Personio":                     {"provider": "custom",
                                     "careers_url": "https://www.personio.com/about-personio/careers/"},
    "Pitch":                        {"provider": "ashby", "board_slug": "Pitch"},
    "Planhat":                      {"provider": "ashby", "board_slug": "Planhat"},
    "Poste Italiane":               {"provider": "oracle"},
    "Retool":                       {"provider": "ashby", "board_slug": "Retool"},
    "Rows":                         {"provider": "ashby", "board_slug": "Rowspace"},
    "Scorewarrior":                 {"provider": "ashby", "board_slug": "scorewarrior"},
    "Skyscanner":                   {"provider": "greenhouse", "board_slug": "skyscanner"},
    "Spendesk":                     {"provider": "personio"},
    "Teamtailor":                   {"provider": "teamtailor"},
    # ── Disabled: broken/unrelated host, do not scrape ───────────────────────
    "SNAM":                         {"enabled": False,
                                     "notes": "Disabled: official careers host (carriere.snam.it) is unreachable; "
                                              "v6 URL pointed at unrelated snamanalytics.in"},
}


class CareerPortalScanner:
    def __init__(self, input_csv="company_Career_seed.csv", output_csv="scraped_jobs_v7.csv",
                 max_workers=3, detail_scan=False, resume=False,
                 allow_synthetic=False, skip_preflight=False, cancel_event=None,
                 only_companies=None):
        self.input_csv = input_csv
        self.output_csv = output_csv
        self.max_workers = max_workers
        self.detail_scan = detail_scan or ProductionScannerConfig.ENABLE_DETAIL_SCAN
        self.resume = bool(resume)
        self.allow_synthetic = bool(allow_synthetic)
        # Cooperative cancellation for the desktop UI Stop button: checked
        # before submitting each crawl target; in-flight targets finish.
        self.cancel_event = cancel_event
        # Optional whitelist of company names (CLI --company): when set, only
        # these targets are scanned.
        self.only_companies = only_companies
        self.run_id = time.strftime("%Y%m%dT%H%M%S")
        self.config = ProductionScannerConfig()
        self.config.PREFLIGHT_ENABLED = not bool(skip_preflight)
        self.detector = JDSupportDetector()

        # Merge the extended country/region list into the base set (the seed config
        # set was missing many countries: ukraine, romania, greece, sweden, brazil...)
        self.config.COUNTRIES_AND_REGIONS = (
            set(self.config.COUNTRIES_AND_REGIONS) | ProductionScannerConfig.REGIONS_EXTRA
        )
        self.ALL_REGIONS = set(self.config.COUNTRIES_AND_REGIONS)

        # Build the known-places index (countries + regions + single/multi-word cities)
        self.KNOWN_CITIES = set(self.config.KNOWN_CITIES) | {"wuxi", "hefei", "kunshan",
            "dongguan", "foshan", "zhengzhou", "changsha", "nanchang", "fuzhou",
            "ningbo", "xiamen", "suzhou", "odense", "aarhus", "esbjerg", "kolding",
            "horsens", "vejle", "roskilde", "herning", "silkeborg", "randers",
            # common US cities (seen in scraped store/retail data)
            "rochester", "sanford", "katy", "waco", "coconut creek", "pembroke pines",
            "lone tree", "centennial", "westminster", "arvada", "thornton",
            "youngstown", "weston", "welland", "thousand oaks", "saugus",
            "saratoga springs", "pleasant prairie", "parsippany", "medford",
            "casselberry", "bentonville", "beavercreek", "aventura", "arlington",
            "hillsboro", "wetzlar", "chillicothe", "athens",
            "manhasset", "garden city", "great neck", "huntington", "levittown",
            # German cities + ASCII transliterations (Hays URL slugs)
            "ulm", "boeblingen", "böblingen", "duesseldorf", "düsseldorf",
            "koeln", "köln", "muenchen", "münchen", "nuernberg", "nürnberg",
            "zuerich", "zürich", "wuerzburg", "würzburg", "fuerth", "fürth",
            "gelsenkirchen", "bochum", "kassel", "kiel", "luebeck", "lübeck",
            "flensburg", "osnabrueck", "osnabrück", "münster", "munster",
            "aachen", "leverkusen", "solingen", "rüsselsheim", "ruesselsheim",
            "darmstadt", "offenbach", "hanau", "marburg", "giessen", "gießen",
            "koblenz", "trier", "saarbruecken", "saarbrücken", "mainz",
            "wiesbaden", "karlsruhe", "mannheim", "heidelberg", "freiburg",
            "reutlingen", "tuebingen", "tübingen", "stuttgart", "ulm",
            "augsburg", "regensburg", "ingolstadt", "passau", "wolfsburg",
            "braunschweig", "hannover", "bremen", "hamburg", "kiel", "rostock",
            "schwerin", "potsdam", "magdeburg", "erfurt", "jena", "leipzig",
            "dresden", "chemnitz", "cottbus", "halle", "bielefeld", "paderborn",
            "guetersloh", "gütersloh", "minden", "detmold", "siegen",
            "wuppertal", "rheinberg", "krefeld", "moenchengladbach",
            "mönchengladbach", "neuss", "duisburg", "oberhausen", "essen",
            "dortmund", "herne", "bochum", "hagen", "witten", "hamm",
            "boynton beach", "jupiter", "palm beach gardens",
            "deltona", "sanford", "coral gables", "kendall", "homestead",
            "wake forest", "buffalo", "kissimmee", "st augustine", "destin", "lecanto",
            "springfield", "tallahassee", "fort myers", "naples", "gainesville",
            "ocala", "daytona beach", "delray beach", "boca raton", "west palm beach",
            "melbourne", "vero beach", "hollywood", "doral", "hialeah",
            "coral springs", "plantation", "sunrise", "davie", "miramar",
            "clermont", "oviedo", "winter park", "lakeland", "port orange",
            "new smyrna beach", "flagler beach", "palm coast",
            "plano", "irving", "garland", "frisco", "mckinney", "denton",
            "nashville", "memphis", "knoxville", "chattanooga",
            "raleigh", "charlotte", "greensboro", "winston-salem", "durham",
            "fayetteville", "cary", "wilmington", "asheville", "greenville",
            "columbia", "charleston", "aiken", "anderson", "savannah",
            "augusta", "macon", "albany", "athens",
            "birmingham", "montgomery", "tuscaloosa",
            "new orleans", "baton rouge", "shreveport", "lafayette",
            "oklahoma city", "tulsa", "lawton", "norman", "wichita", "topeka",
            "omaha", "lincoln", "des moines", "cedar rapids", "davenport",
            "kansas city", "st louis", "jefferson city",
            "little rock", "fort smith"}
        self.MULTI_WORD_CITIES = set(self.config.MULTI_WORD_CITIES)
        # more global cities (Ferrero/SAP/ASML detail pages)
        self.KNOWN_CITIES |= {
            "suqian", "kunshan", "changzhou", "nantong", "xuzhou", "yancheng",
            "yangzhou", "zhenjiang", "taizhou", "huai'an", "lianyungang",
            "wuhu", "bengbu", "ma'anshan", "fuyang", "jiaxing", "shaoxing",
            "jinhua", "wenzhou", "quanzhou", "zhangzhou", "putian",
            "jiujiang", "jingdezhen", "zhuzhou", "xiangtan", "hengyang",
            "yueyang", "guiyang", "kunming", "nanning", "liuzhou", "guilin",
            "haikou", "sanya", "shijiazhuang", "tangshan", "qinhuangdao",
            "handan", "baoding", "zhangjiakou", "taiyuan", "datong", "changzhi",
            "hohhot", "baotou", "harbin", "qiqihar", "mudanjiang", "jiamusi",
            "changchun", "anshan", "fushun", "lanzhou", "xining", "yinchuan",
            "urumqi", "kashgar", "mianyang", "leshan", "yibin", "xianyang",
            "baoji", "hancheng", "huangshi", "shiyan", "yichang", "xiangyang",
            "jingzhou", "xiaogan", "xianning", "suizhou", "changde",
            "zhangjiajie", "yiyang", "chenzhou", "yongzhou", "huaihua",
            "loudi", "shaoyang", "luzhou", "neijiang", "nanchong", "meishan",
            "guang'an", "suining", "zigong", "panzhihua", "ya'an", "bazhong",
            "ziyang",
        }
        # German state names (Hays URLs use them: nordrhein-westfalen, ...)
        self.config.COUNTRIES_AND_REGIONS = self.config.COUNTRIES_AND_REGIONS | {
            "bayern", "bavaria", "baden-wuerttemberg", "baden-württemberg",
            "nordrhein-westfalen", "north rhine-westphalia", "hessen", "hesse",
            "niedersachsen", "lower saxony", "rheinland-pfalz", "rhineland-palatinate",
            "sachsen", "saxony", "sachsen-anhalt", "saxony-anhalt",
            "thueringen", "thüringen", "thuringia", "schleswig-holstein",
            "mecklenburg-vorpommern", "saarland", "brandenburg", "rhein-main",
            "rhein-main-gebiet", "north holland", "noord-holland", "south holland",
            "zuid-holland", "north brabant", "noord-brabant", "gelderland",
            "flevoland", "drenthe", "overijssel", "zeeland",
        }
        # v7: refresh after adding regional aliases; v6 built region regexes from a stale copy.
        self.ALL_REGIONS = set(self.config.COUNTRIES_AND_REGIONS)
        self.KNOWN_PLACES = (
            set(self.config.COUNTRIES_AND_REGIONS)
            | self.KNOWN_CITIES
            | self.MULTI_WORD_CITIES
            | {
                "bavaria", "baden-wurttemberg", "north rhine-westphalia",
                "hesse", "saxony", "lower saxony", "rhineland-palatinate",
                "schleswig-holstein", "thuringia", "saarland", "brandenburg",
                "mecklenburg-vorpommern", "saxony-anhalt", "lombardy",
                "piedmont", "veneto", "emilia-romagna", "tuscany", "lazio",
                "campania", "puglia", "sicily", "sardinia", "liguria",
                "friuli-venezia giulia", "trentino-alto adige", "abruzzo",
                "umbria", "marche", "molise", "basilicata", "calabria",
                "england", "scotland", "wales", "northern ireland",
                "flanders", "wallonia", "catalonia", "andalusia", "basque",
                "galicia", "castile", "provence", "brittany", "normandy",
                "occitanie", "bavaria", "business bay", "east london",
                # US states
                "alabama", "alaska", "arizona", "arkansas", "california",
                "colorado", "connecticut", "delaware", "florida", "georgia",
                "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
                "kentucky", "louisiana", "maine", "maryland", "massachusetts",
                "michigan", "minnesota", "mississippi", "missouri", "montana",
                "nebraska", "nevada", "new hampshire", "new jersey",
                "new mexico", "north carolina", "north dakota", "ohio",
                "oklahoma", "oregon", "pennsylvania", "rhode island",
                "south carolina", "south dakota", "tennessee", "texas",
                "utah", "vermont", "virginia", "washington", "west virginia",
                "wisconsin", "wyoming", "district of columbia",
                # Canadian provinces
                "alberta", "british columbia", "manitoba", "new brunswick",
                "newfoundland", "newfoundland and labrador", "nova scotia",
                "ontario", "prince edward island", "quebec", "saskatchewan",
                # extra cities seen in data
                "sarasota", "huntsville", "wimbledon", "wilton", "chantilly",
                "newtown square", "malibu", "vista", "ventura", "warren",
                "waregem", "firenze", "xi'an", "makati",
            }
        )

        # 2-letter country codes -> full names (for "Suqian CN" style LD strings)
        self.COUNTRY_CODES = {
            "cn": "china", "de": "germany", "us": "united states", "usa": "united states",
            "gb": "united kingdom", "uk": "united kingdom", "fr": "france", "it": "italy",
            "es": "spain", "nl": "netherlands", "be": "belgium", "ch": "switzerland",
            "at": "austria", "pl": "poland", "pt": "portugal", "se": "sweden", "no": "norway",
            "dk": "denmark", "fi": "finland", "ie": "ireland", "cz": "czechia",
            "sk": "slovakia", "hu": "hungary", "ro": "romania", "bg": "bulgaria",
            "gr": "greece", "hr": "croatia", "si": "slovenia", "rs": "serbia",
            "ee": "estonia", "lv": "latvia", "lt": "lithuania", "lu": "luxembourg",
            "mt": "malta", "cy": "cyprus", "tr": "turkey", "il": "israel", "ae": "uae",
            "qa": "qatar", "sa": "saudi arabia", "in": "india", "jp": "japan",
            "kr": "south korea", "sg": "singapore", "my": "malaysia", "th": "thailand",
            "vn": "vietnam", "ph": "philippines", "id": "indonesia", "au": "australia",
            "nz": "new zealand", "ca": "canada", "mx": "mexico", "br": "brazil",
            "ar": "argentina", "cl": "chile", "co": "colombia", "pe": "peru",
            "za": "south africa", "eg": "egypt", "ng": "nigeria", "ke": "kenya",
            "ma": "morocco", "tw": "taiwan", "hk": "hong kong", "ua": "ukraine",
            "ru": "russia", "kz": "kazakhstan",
        }
        # Diacritic-insensitive lookup index (Wrocław <-> wroclaw, München <-> munchen)
        self.NORM_KNOWN = {}
        for _p in self.KNOWN_PLACES:
            self.NORM_KNOWN.setdefault(self._norm(_p), _p)

        # US state + Canadian province codes (2-letter location codes we ACCEPT)
        self.STATE_CODES = {
            "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
            "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
            "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
            "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
            "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
            "dc", "ab", "bc", "mb", "nb", "nl", "ns", "nt", "nu", "on",
            "pe", "qc", "sk", "yt",
        }

        # Compiled location-reject regex (word/phrase boundaries)
        phrases = sorted(
            {p for p in self.config.LOCATION_REJECT_PHRASES if len(p) >= 3},
            key=len, reverse=True,
        )
        words = sorted(
            {w for w in self.config.LOCATION_REJECT_WORDS if len(w) >= 2},
            key=len, reverse=True,
        )
        self.LOCATION_REJECT_RE = re.compile(
            r"\b(?:" + "|".join(re.escape(p) for p in phrases) + r"|"
            + "|".join(re.escape(w) for w in words) + r")\b",
            re.IGNORECASE,
        )

        # Region/country detection regexes (end-of-string and end-of-line)
        regions = sorted(
            {r for r in self.ALL_REGIONS
             if r not in ("global", "worldwide", "united", "remote")},
            key=len, reverse=True,
        )
        region_alt = "|".join(re.escape(r) for r in regions)
        self.REGION_END_RE = re.compile(
            r"\b(" + region_alt + r")(?:[.,;!?)\]}\"'%]*)$", re.IGNORECASE)
        self.REGION_LINE_RE = re.compile(
            r"\b(" + region_alt + r")(?:[.,;!?)\]}\"'%]*)(?=$|[\n\r|•])",
            re.IGNORECASE | re.MULTILINE,
        )

        # Company names from the seed file (used to reject company-name-as-location)
        self.seed_company_names_lower = set()
        try:
            if os.path.exists(self.input_csv):
                with open(self.input_csv, newline="", encoding="utf-8-sig") as f:
                    sample = f.read(4096)
                    f.seek(0)
                    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
                    for row in csv.DictReader(f, delimiter=delimiter):
                        n = (row.get("name") or "").strip().lower()
                        if n:
                            self.seed_company_names_lower.add(n)
        except Exception:
            pass

    @staticmethod
    def _is_network_error(exc):
        """True if an exception is a transient network/DNS failure worth retrying."""
        msg = str(exc).lower()
        markers = (
            "net::err_", "err_name_not_resolved", "err_connection_", "err_timed_out",
            "err_ssl_", "err_http_", "dns", "socket", "connection reset", "timed out",
            "timeout", "temporary failure", "getaddrinfo", "connectionrefused",
        )
        return any(m in msg for m in markers)

    def _preflight_connectivity(self):
        """Resolve + connect a handful of representative hosts before crawling.

        Aborts the run with a clear error if the network is down, instead of
        letting 125 companies each burn their time budget on DNS timeouts.
        """
        if not self.config.PREFLIGHT_ENABLED:
            return
        failures = []
        for host in self.config.PREFLIGHT_PROBE_HOSTS:
            try:
                socket.setdefaulttimeout(self.config.PREFLIGHT_TIMEOUT_SEC)
                infos = socket.getaddrinfo(host, self.config.PREFLIGHT_PORT, socket.AF_INET)
                if not infos:
                    raise socket.gaierror("no address")
                ip = infos[0][4][0]
                with socket.create_connection((ip, self.config.PREFLIGHT_PORT),
                                              timeout=self.config.PREFLIGHT_TIMEOUT_SEC):
                    pass
                print(f"[preflight] OK   {host}")
            except Exception as exc:
                failures.append(f"{host}: {type(exc).__name__}: {exc}")
                print(f"[preflight] FAIL {host}: {type(exc).__name__}: {exc}")
        if len(failures) >= self.config.PREFLIGHT_MAX_FAILURES:
            raise RuntimeError(
                "Connectivity pre-flight FAILED: "
                f"{len(failures)}/{len(self.config.PREFLIGHT_PROBE_HOSTS)} probes unreachable. "
                "Aborting before crawling to avoid a wasted run. "
                "Check DNS/VPN/proxy, then re-run. "
                "(Use --skip-preflight to bypass this gate.)\n  "
                + "\n  ".join(failures)
            )
        if failures:
            print(f"[preflight] WARNING {len(failures)} probe(s) failed but proceeding.")

    def _http_fetch_with_retry(self, url, headers, parse_json=True):
        """GET a provider/API URL with transient-error retry + exponential backoff.

        Returns decoded body (str). Raises the last exception if all attempts fail.
        """
        last_exc = None
        for attempt in range(1, self.config.HTTP_RETRIES + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.config.HTTP_TIMEOUT_SEC) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                return raw
            except urllib.error.HTTPError as exc:
                # 404/410 are definitive (wrong slug); 429/5xx are transient.
                if exc.code in (404, 410):
                    raise
                last_exc = exc
            except Exception as exc:
                if not self._is_network_error(exc):
                    raise
                last_exc = exc
            if attempt < self.config.HTTP_RETRIES:
                backoff = self.config.HTTP_BACKOFF_BASE_SEC * (2 ** (attempt - 1))
                time.sleep(backoff)
        raise last_exc

    def read_seed_file(self):
        """Read and validate the v7 seed schema.

        Backward-compatible with v6, but v7 fields are strongly preferred. Disabled
        seeds are logged and skipped rather than silently substituted in code.
        """
        if not os.path.exists(self.input_csv):
            # Actionable failure instead of a bare traceback. Resolve the path the
            # OS actually looked at, list sibling CSV candidates, and tell the user
            # exactly how to point at the right file.
            cwd = os.getcwd()
            resolved = os.path.abspath(self.input_csv)
            here = os.path.dirname(resolved) or cwd
            candidates = []
            for fn in ("company_Career_seed.csv", "company_Career_seed_v7.csv"):
                p = os.path.join(here, fn)
                if os.path.exists(p):
                    candidates.append(f"    found: {p}")
            hint = (
                "\n  The seed CSV was not found at:\n"
                f"    {resolved}\n"
                f"  (working directory: {cwd})\n"
            )
            if candidates:
                hint += "  Sibling seed files detected:\n" + "\n".join(candidates) + "\n"
            hint += (
                "  Fix one of:\n"
                "    1. Put 'company_Career_seed.csv' in your working directory, or\n"
                "    2. Run with: --input <full path to your seed CSV>\n"
                "  Note: the scanner reads either the v7 schema (source_type,\n"
                "  target_country, scope_policy, provider, board_slug) or the original\n"
                "  v6 schema (name, ats_type, careers_url, ...). A v6-format seed will\n"
                "  still run, but without recruiter separation and country-scope\n"
                "  enforcement (those default to Global/global)."
            )
            raise FileNotFoundError(f"Seed file '{self.input_csv}' not found.{hint}")
        records = []
        errors = []
        seen_seed_keys = set()
        with open(self.input_csv, newline="", encoding="utf-8-sig") as f:
            sample = f.read(4096)
            f.seek(0)
            delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
            reader = csv.DictReader(f, delimiter=delimiter)
            headers = set(reader.fieldnames or [])
            if "careers_url" not in headers:
                raise ValueError("Seed CSV must contain careers_url")
            for line_no, row in enumerate(reader, 2):
                seed_name = (row.get("seed_name") or row.get("name") or "").strip()
                name = (row.get("canonical_name") or seed_name).strip()
                url = (row.get("careers_url") or "").strip()
                # ── v6 → v7 in-memory upgrade (auditable, logged) ────────────────
                # Only applied to v6-format rows: when a row has no v7 metadata of
                # its own and a matching SEED_UPGRADE key exists, correct it.
                upg = SEED_UPGRADE.get(name) or SEED_UPGRADE.get(name.casefold()) \
                    or next((v for k, v in SEED_UPGRADE.items() if k.casefold() == name.casefold()), None)
                if upg:
                    changed = []
                    if "careers_url" in upg and upg["careers_url"] != url:
                        changed.append(f"url {url!r} -> {upg['careers_url']!r}")
                        url = upg["careers_url"]
                    if "source_type" in upg and not (row.get("source_type") or "").strip():
                        changed.append(f"source_type -> {upg['source_type']}")
                        row["source_type"] = upg["source_type"]
                    if "target_country" in upg and not (row.get("target_country") or "").strip():
                        changed.append(f"target_country -> {upg['target_country']}")
                        row["target_country"] = upg["target_country"]
                    if "scope_policy" in upg and not (row.get("scope_policy") or "").strip():
                        changed.append(f"scope_policy -> {upg['scope_policy']}")
                        row["scope_policy"] = upg["scope_policy"]
                    if "provider" in upg and not (row.get("provider") or "").strip():
                        changed.append(f"provider -> {upg['provider']}")
                        row["provider"] = upg["provider"]
                    if "board_slug" in upg and not (row.get("board_slug") or "").strip():
                        changed.append(f"board_slug -> {upg['board_slug']}")
                        row["board_slug"] = upg["board_slug"]
                    if changed:
                        print(f"   [upgrade] {seed_name or name}: " + "; ".join(changed))
                if upg and upg.get("enabled") is False:
                    notes = upg.get("notes", "") or row.get("notes", "")
                    print(f"   -> Seed disabled (upgrade): {seed_name or name} ({notes})")
                    continue
                enabled = (row.get("enabled") or "true").strip().lower() not in {
                    "0", "false", "no", "disabled"
                }
                if not enabled:
                    print(f"   -> Seed disabled: {seed_name or name} ({row.get('notes','')})")
                    continue
                if not seed_name or not name:
                    errors.append(f"line {line_no}: missing seed/canonical name")
                    continue
                if not url.startswith(("http://", "https://")) or "..." in url:
                    errors.append(f"line {line_no} {seed_name}: invalid URL {url!r}")
                    continue
                source_type = (row.get("source_type") or "direct_employer").strip().lower()
                if source_type not in {"direct_employer", "recruiter"}:
                    errors.append(f"line {line_no} {seed_name}: invalid source_type {source_type!r}")
                    continue
                target_country = (row.get("target_country") or "Global").strip()
                scope_policy = (row.get("scope_policy") or "global").strip().lower()
                if scope_policy not in {"global", "seed_url", "job_location"}:
                    errors.append(f"line {line_no} {seed_name}: invalid scope_policy {scope_policy!r}")
                    continue
                provider = (row.get("provider") or "auto").strip().lower()
                board_slug = (row.get("board_slug") or "").strip()
                key = (seed_name.casefold(), target_country.casefold(), url.casefold())
                if key in seen_seed_keys:
                    # Same company + same country + same (post-upgrade) URL is a
                    # duplicate seed row (e.g. a placeholder split into two region
                    # URLs that both resolve to one board). Collapse silently rather
                    # than fail the whole run.
                    print(f"   -> Seed deduped (duplicate): {seed_name} line {line_no}")
                    continue
                seen_seed_keys.add(key)
                # Parse scores instead of silently ignoring four seed columns.
                scores = {}
                for col in ("sponsorship_history", "english_friendly", "remote_score"):
                    raw = (row.get(col) or "").strip()
                    try:
                        value = int(raw) if raw else None
                    except ValueError:
                        errors.append(f"line {line_no} {seed_name}: non-numeric {col}={raw!r}")
                        value = None
                    if value is not None and not 0 <= value <= 100:
                        errors.append(f"line {line_no} {seed_name}: {col} outside 0..100")
                    scores[col] = value
                # Safe page-size normalization; query-aware behavior is handled by pagination.
                url = re.sub(r"([?&]size=)n_3_n(?=&|$)", r"\1n_100_n", url)
                records.append({
                    "seed_name": seed_name,
                    "name": name,
                    "careers_url": url,
                    "industry": (row.get("industry") or "Unknown").strip(),
                    "source_type": source_type,
                    "target_country": target_country,
                    "scope_policy": scope_policy,
                    "provider": provider,
                    "board_slug": board_slug,
                    "ats_type": (row.get("ats_type") or provider).strip(),
                    "notes": (row.get("notes") or "").strip(),
                    **scores,
                })
        if errors:
            raise ValueError("Seed validation failed:\n - " + "\n - ".join(errors))
        return records

    def dismiss_initial_blockers(self, page):
        selectors = [
            "button:has-text('Accept all')",
            "button:has-text('Accept All')",
            "button:has-text('Accept')",
            "button:has-text('Agree')",
            "button:has-text('Allow all')",
            "button:has-text('Allow All')",
            "button:has-text('Allow')",
            "button:has-text('Consent')",
            "button:has-text('Accept All Cookies')",
            "button:has-text('Allow Cookies')",
            "button:has-text('Accetta tutti')",
            "button:has-text('Accetta')",
            "button:has-text('Alle akzeptieren')",
            "button:has-text('Akzeptieren')",
            "button:has-text('Accepteer alles')",
            "button:has-text('Accepteer')",
            "button:has-text('Accepter tout')",
            "button:has-text('Aceptar todo')",
            "button:has-text('OK')",
            "button:has-text('Got it')",
            "button:has-text('I agree')",
            "button:has-text('I understand')",
            "button:has-text('Continue')",
            "#onetrust-accept-btn-handler",
            ".cc-accept",
            ".cookie-accept",
            "button[id*='cookie' i]",
            "button[class*='cookie' i]",
            "button[id*='accept' i]",
            "button[class*='accept' i]",
            "button[data-testid*='accept']",
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=400):
                    btn.click(timeout=1000)
                    page.wait_for_timeout(400)
            except Exception:
                continue
    def navigate_to_fragment(self, page, url):
        if "#" not in url:
            return
        fragment = url.split("#", 1)[1].strip()
        if not fragment:
            return
        try:
            page.evaluate(
                """frag => {
                    const el = document.getElementById(frag) ||
                               document.querySelector('[name="' + frag + '"]');
                    if (el) el.scrollIntoView({behavior: "instant", block: "start"});
                }""",
                fragment,
            )
            page.wait_for_timeout(1200)
        except Exception:
            pass
    def handle_landing_page_redirect(self, page, base_url):
        for text in self.config.LANDING_PAGE_CTAS:
            try:
                loc = page.locator(f"a:has-text('{text}'), button:has-text('{text}')").first
                if loc.is_visible(timeout=300):
                    href = loc.get_attribute("href")
                    print(f"   -> Landing CTA: {text}")
                    if href:
                        page.goto(
                            urljoin(base_url, href),
                            wait_until="domcontentloaded",
                            timeout=self.config.ACTION_TIMEOUT_MS,
                        )
                    else:
                        loc.click(timeout=1500)
                    page.wait_for_timeout(3000)
                    return True
            except Exception:
                continue
        return False
    def trigger_search_if_present(self, page):
        selectors = [
            "button:has-text('Search')",
            "button:has-text('Search Jobs')",
            "button:has-text('Find Jobs')",
            "button:has-text('Show all')",
            "button:has-text('View all')",
            "button:has-text('All jobs')",
            "button:has-text('Cerca')",
            "button:has-text('Suchen')",
            "input[type='submit'][value*='Search' i]",
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=300):
                    btn.click(timeout=1500)
                    page.wait_for_timeout(2500)
                    return True
            except Exception:
                continue
        return False
    # FIXED: Re-engineered with:
    # 1. URL parsing to evaluate ONLY the domain + path (netloc/path), completely preventing matching keywords hidden inside tracking/referral parameters!
    # 2. Strict domain/provider exclusions for trackers, cookie consent widgets, chatbots, and layout players to guarantee we never accidentally target them.
    def check_iframes(self, page):
        best_frame = None
        best_score = 0
        
        EXCLUDED_IFRAME_DOMAINS = [
            "doubleclick.net", "demdex.net", "googleads", "googletagmanager", 
            "google-analytics", "analytics", "facebook.com", "linkedin.com", 
            "framer.com", "speakerdeck.com", "driftt.com", "drift.com", 
            "hotjar", "cookiebot", "onetrust", "cookie-consent", "youtube.com", 
            "vimeo.com", "twitter.com", "instagram.com", "hubspot.com", 
            "intercom", "recaptcha", "disqus", "optimizely", "krxd.net",
            "scorecardresearch", "adnxs.com", "ads-twitter", "snapchat.com",
            "adsrvr.org", "casalemedia.com", "rubiconproject.com", "pubmatic.com"
        ]
        
        try:
            for frame in page.frames[1:]:
                low_url = (frame.url or "").lower()
                if not low_url or any(d in low_url for d in EXCLUDED_IFRAME_DOMAINS):
                    continue
                
                parsed = urlparse(low_url)
                check_str = f"{parsed.netloc}{parsed.path}"
                
                score = 0
                if any(k in check_str for k in [
                    "personio", "workable", "greenhouse", "lever", "ashby",
                    "smartrecruiters", "teamtailor", "breezy", "successfactors",
                    "myworkday", "workdayjobs", "jobs", "career", "tellent",
                    "recruitee", "comeet", "jobylon", "rippling"
                ]):
                    score += 8
                try:
                    text_score = frame.evaluate("""() => {
                        const txt = (document.body?.innerText || '').toLowerCase();
                        const links = [...document.querySelectorAll('a[href]')];
                        const jobLinks = links.filter(a => /\\/(job|jobs|o|role|position|vacancy|opening)\\b|jobid|gh_jid|requisition/i.test(a.href || '')).length;
                        let score = Math.min(jobLinks * 3, 20);
                        if (jobLinks >= 2 && /job|career|position|opening|vacancy|role/.test(txt)) score += 5;
                        return score;
                    }""")
                    score += int(text_score or 0)
                except Exception:
                    pass
                if score > best_score:
                    best_score = score
                    best_frame = frame
            if best_frame and best_score >= 8:
                return best_frame
        except Exception:
            pass
        return None
    def fix_encoding(self, text):
        if not text:
            return text
        replacements = {
            "Ã¼": "ü", "Ã¤": "ä", "Ã¶": "ö", "ÃŸ": "ß",
            "Ã©": "é", "Ã¨": "è", "Ã ": "à", "Ã¡": "á",
            "Ã¢": "â", "Ã­": "í", "Ã³": "ó", "Ã²": "ò",
            "Ã´": "ô", "Ã»": "û", "Ã§": "ç", "Ã±": "ñ",
            "Ãœ": "Ü", "Ã„": "Ä", "Ã–": "Ö", "Ã‰": "É", "Ã€": "À",
            "â€™": "'", "â€œ": '"', "â€": '"',
            "â€”" : "—", "â€¢": "•", "Â": "",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text
    def has_job_identifier_query(self, url):
        try:
            parsed = urlparse(url)
            q = parsed.query.lower()
            path = parsed.path.lower()
        except Exception:
            return False
        strong = re.search(
            r"(^|&)(job|jobid|job_id|jid|gh_jid|req|reqid|requisition|"
            r"requisitionid|career_job_req_id|posting|postingid|externaljobid)=",
            q, re.IGNORECASE,
        )
        if strong:
            return True
        # Generic id= is identity only on an explicitly job-shaped path (e.g. Coop view-job.php?id=...).
        return bool(re.search(r"(^|&)id=", q, re.I) and re.search(r"job|vacanc|position", path, re.I))

    def clean_page_identity(self, url):
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/").lower()
    def is_self_listing_url(self, job_url, seed_url):
        if not seed_url:
            return False
        if "#job=" in job_url.lower():
            return False
        if self.has_job_identifier_query(job_url):
            return False
        return self.clean_page_identity(job_url) == self.clean_page_identity(seed_url)
    def clean_and_normalize_url(self, url):
        if not url:
            return ""
        url = self.fix_encoding(url.strip()).replace("&amp;", "&")
        if not url.startswith(("http://", "https://")):
            return ""
        parsed = urlparse(url)
        keep_keys = {
            "job", "jobid", "job_id", "jid", "gh_jid", "req", "reqid",
            "requisition", "requisitionid", "career_job_req_id", "posting",
            "postingid", "externaljobid", "lever-origin", "language", "lang",
        }
        if re.search(r"job|vacanc|position", parsed.path, re.I):
            keep_keys.add("id")
        kept_query = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() in keep_keys
        ]
        query = urlencode(kept_query, doseq=True)
        fragment = ""
        if parsed.fragment and re.search(r"(?:^|/)(?:job|jobs|position|vacancy)[=/]", parsed.fragment, re.I):
            fragment = parsed.fragment
        elif parsed.fragment.lower().startswith("job="):
            fragment = parsed.fragment
        path = re.sub(
            r"/(apply|submission|application|form|new|confirm|thank-you)/?(?=$)",
            "/", parsed.path, flags=re.IGNORECASE,
        )
        return urlunparse((
            parsed.scheme.lower(), parsed.netloc.lower(),
            path.rstrip("/") if not fragment else path,
            "", query, fragment,
        ))

    def _strip_gender_tags(self, title):
        # Removes (m/f/d), (m/w/d), (w/m/d), (d/f/m), (f/m/d), (m/f/x), (all genders),
        # (mwd), (m/f), (divers), standalone trailing m/f/d, etc.
        title = re.sub(
            r"\s*[\(\[]\s*(?:all\s+genders|"
            r"(?:[mwdfχxns]{1,4}[\s/|](?:[mwdfχxns]{1,4})(?:[\s/|](?:[mwdfχxns]{1,4}))?)|"
            r"(?:[mwdfχxns]{1,4}[\s/|](?:[mwdfχxns]{1,4})))\s*[\)\]]\s*",
            "", title, flags=re.IGNORECASE,
        )
        title = re.sub(
            r"\s+(m/f/d|m/w/d|w/m/d|d/f/m|f/m/d|m/f/x|w/m/x|m/w/x)\s*$",
            "", title, flags=re.IGNORECASE,
        )
        return title

    def _normalize_level_prefix(self, title):
        level_map = {
            "senior": "Senior", "junior": "Junior", "staff": "Staff",
            "principal": "Principal", "lead": "Lead", "executive": "Executive",
            "expert": "Expert", "associate": "Associate", "entry": "Entry",
            "mid": "Mid", "sr": "Sr.", "sr.": "Sr.", "jr": "Jr.", "jr.": "Jr.",
        }
        m = re.match(
            r"^\s*\(\s*([A-Za-zÀ-ÿ.'-]{1,12})\s*\)\s*", title)
        if m and m.group(1).lower() in level_map:
            return level_map[m.group(1).lower()] + " " + title[m.end():]
        return title

    def _looks_like_location_fragment(self, frag):
        s = (frag or "").strip()
        if not s:
            return False
        # a fragment that contains a role word is a title, not a location
        # (e.g. "Payments Consultant Germany & Austria")
        if self.config.ROLE_WORD_PATTERN.search(s):
            return False
        low = re.sub(r"^[\(\[]|[\)\]]$", "", s).strip(" .,;").lower()
        if low in ("remote", "hybrid", "onsite", "on-site", "on site",
                   "home office", "anywhere", "worldwide", "global"):
            return True
        # diacritic-aware known-place check (Gda\u0144sk, K\u00f6ln, Wroc\u0142aw)
        if low in self.KNOWN_PLACES or self._norm(low) in self.NORM_KNOWN:
            return True
        # slash-separated city list ("Linkou/Hsinchu/Taichung") is a location fragment
        if "/" in low:
            for part in low.split("/"):
                part = part.strip()
                if part and (part in self.KNOWN_PLACES or self._norm(part) in self.NORM_KNOWN):
                    return True
        # office / work-mode keywords ("In-Office", "Onsite")
        if re.search(r"\b(in[- ]?office|on[- ]?site|remote|hybrid|home office|"
                     r"work from home|flexible)\b", low):
            return True
        # known boilerplate phrases ("Target Optical", "Sunglass Hut")
        if any(ph in low for ph in self.config.LOCATION_REJECT_PHRASES):
            return True
        if low in self.KNOWN_PLACES:
            return True
        if re.fullmatch(r"[a-z]{2}", low):
            return True
        words = low.split()
        if words and words[-1] in self.config.COUNTRIES_AND_REGIONS:
            return True
        if re.search(
            r"\b(ny|ca|tx|ma|il|wa|fl|az|co|ga|nj|pa|mi|oh|mn|nc|va|md|ct|"
            r"or|ut|in|mo|wi|tn|sc|ky|la|al|ok|ks|ia|ar|nv|ne|id|nh|me|ri|"
            r"vt|wv|mt|nd|sd|wy|ak|hi|de|dc|on|bc|ab|qc|ns|mb|sk|nt|yt|nu|"
            r"pe|nl|nb)\b$", low,
        ):
            return True
        return False

    def _looks_like_contract_fragment(self, frag):
        low = (frag or "").strip().lower()
        if not low or len(low) > 80:
            return False
        # short fragments that START with a contract/type term
        # (e.g. "fixed term until June 30th, 2027" — but NOT
        #  "Campus Undergraduate Summer Internship Program")
        if re.search(
            r"^(fixed[- ]?term|permanent|temporary|temporaire|contract|"
            r"full[- ]?time|part[- ]?time|internship|trainee|werkstudent|"
            r"working student|praktikum|ausbildung|duales studium|"
            r"apprenticeship|apprentice|secondment)\b", low,
        ):
            return True
        # year + contract-word combo (e.g. "2027 fixed term")
        if re.search(r"\b20\d\d\b", low) and re.search(
            r"\b(term|until|ending|contract|fixed|year|month)\b", low):
            return True
        return False

    def clean_job_title(self, title):
        """Conservative, multilingual title normalization.

        v7 never removes comma-delimited function text, brand names, or words merely
        because they resemble a department/location. Raw extraction mistakes are
        rejected by validation instead of destructively rewritten into generic titles.
        """
        if not title:
            return ""
        title = self.fix_encoding(str(title))
        lines = [re.sub(r"\s+", " ", x).strip() for x in re.split(r"[\r\n]+", title) if x.strip()]
        if not lines:
            return ""
        title = lines[0]
        title = self._strip_gender_tags(title)
        title = self._normalize_level_prefix(title)
        title = re.sub(r"^(?:new|featured|hot)\s*[!:\-–—|]+\s*", "", title, flags=re.I)
        title = re.sub(r"^[•·→↗›\s|]+", "", title)
        title = re.sub(r"\s*[•·]+\s*$", "", title)
        # Remove an unambiguous trailing work-mode/contract parenthesis only.
        title = re.sub(
            r"\s*\((?:full[- ]?time|part[- ]?time|remote|hybrid|on[- ]?site|"
            r"permanent|temporary|fixed[- ]?term|contract)\)\s*$",
            "", title, flags=re.I,
        )
        # Remove salary tails, but never surrounding title words.
        title = re.sub(
            r"\s*[-–—|]\s*[€$£]\s?[\d,.]+(?:k)?(?:\s*(?:-|to)\s*[€$£]?\s?[\d,.]+(?:k)?)?"
            r"(?:\s*(?:per|/)\s*(?:hour|day|year|annum|hr))?\s*$",
            "", title, flags=re.I,
        )
        title = re.sub(r"\s+", " ", title).strip(" \t-–—|•")
        return title[:200].rstrip()

    def is_valid_job_title(self, title):
        if not title:
            return False
        t = re.sub(r"\s+", " ", title).strip()
        low = t.casefold()
        if len(t) < 3 or len(t) > 200 or not any(ch.isalpha() for ch in t):
            return False
        hard = {x.casefold() for x in self.config.HARD_TITLE_BLACKLIST}
        dept = {x.casefold() for x in self.config.DEPT_AS_TITLE}
        # These can be genuine standalone retail roles, not only departments.
        dept -= {"cashier", "bakery", "deli", "produce", "recovery", "checkout"}
        dept |= {"marketing solutions", "pre-sales", "presales", "business development",
                 "customer service analytics", "field engineering", "professional services"}
        generic_single = {
            "senior", "junior", "associate", "principal", "lead", "manager",
            "director", "expert", "owner", "quality", "officer", "specialist",
            "analyst", "engineer", "intern", "apprentice", "trainee",
        }
        if low in hard or low in dept or low in generic_single:
            return False
        if low in self.KNOWN_PLACES or self._norm(low) in self.NORM_KNOWN:
            return False
        for pattern in self.config.SUSPICIOUS_TITLE_PATTERNS:
            if pattern.match(t):
                return False
        if re.match(
            r"^(load|view|see|show|browse|explore|find|search|open|close|toggle|"
            r"upload|submit|download|share|print|email|save|apply)\b", low
        ) and len(t.split()) <= 6:
            return False
        if any(x in low for x in (
            "privacy statement", "terms of use", "cookie", "items per page",
            "clear all filters", "recruitment fraud", "click this button",
        )):
            return False
        # No English-only role-word gate: preserve Italian/German/French/Dutch,
        # accented and non-Latin titles. Multi-word context is the safer signal.
        if len(t.split()) == 1 and len(t) < 5:
            return False
        return True

    def is_valid_job_url(self, url):
        if not url or not url.startswith("http"):
            return False
        if re.search(r"/(?:applicationmethods|apply|application)(?:/|$)", urlparse(url).path, re.I):
            return False
        if self.config.URL_EXCLUSION_PATTERN.search(url):
            return False
        if "#job=" in url.lower():
            return True
        if self.config.CATEGORY_PATH_INDICATORS.search(url):
            return False
        clean_path = urlparse(url).path.rstrip("/").lower()
        if clean_path.endswith((
            "/jobs", "/careers", "/career", "/vacancies",
            "/openings", "/positions", "/roles", "/search"
        )):
            if not self.has_job_identifier_query(url):
                return False
        if not self.config.JOB_URL_PATTERN.search(url):
            if not self.has_job_identifier_query(url):
                return False
        return True
    def _fmt_place(self, low):
        """Format a lowercased place token with proper casing."""
        low = low.strip()
        if not low:
            return ""
        # restore canonical (diacritic) form: "munchen" -> "München"
        canon = self.NORM_KNOWN.get(self._norm(low))
        if canon:
            low = canon
        if low in self.config.CASING_MAP:
            return self.config.CASING_MAP[low]
        de_regions = {
            "nordrhein-westfalen": "Nordrhein-Westfalen",
            "nordrhein westfalen": "Nordrhein-Westfalen",
            "rhein-main-gebiet": "Rhein-Main-Gebiet",
            "rhein-main": "Rhein-Main",
            "baden-wuerttemberg": "Baden-Württemberg",
            "baden-württemberg": "Baden-Württemberg",
            "sachsen-anhalt": "Sachsen-Anhalt",
            "mecklenburg-vorpommern": "Mecklenburg-Vorpommern",
            "schleswig-holstein": "Schleswig-Holstein",
            "rheinland-pfalz": "Rheinland-Pfalz",
            "thueringen": "Thüringen",
            "thüringen": "Thüringen",
            "niedersachsen": "Niedersachsen",
        }
        if low in de_regions:
            return de_regions[low]
        display_map = {
            "sao paulo": "São Paulo", "sao leopoldo": "São Leopoldo",
            "duesseldorf": "Düsseldorf", "koeln": "Köln", "muenchen": "München",
            "munchen": "München", "zuerich": "Zürich", "zurich": "Zürich",
            "wroclaw": "Wrocław", "lodz": "Łódź", "gdansk": "Gdańsk",
            "krakow": "Kraków", "kyiv": "Kyiv", "lviv": "Lviv",
            "mexico city": "Mexico City", "ho chi minh": "Ho Chi Minh",
            "the hague": "The Hague", "tysons": "Tysons", "tysons corner": "Tysons Corner",
            "nuernberg": "Nürnberg", "nurnberg": "Nürnberg", "wuerzburg": "Würzburg",
            "wuertzburg": "Würzburg", "fuerth": "Fürth", "further": "Fürth",
            "rüsselsheim": "Rüsselsheim", "ruesselsheim": "Rüsselsheim",
            "saarbruecken": "Saarbrücken", "saarbrücken": "Saarbrücken",
            "tuebingen": "Tübingen", "tübingen": "Tübingen",
            "osnabrueck": "Osnabrück", "osnabrück": "Osnabrück",
            "moenchengladbach": "Mönchengladbach", "mönchengladbach": "Mönchengladbach",
            "guetersloh": "Gütersloh", "gütersloh": "Gütersloh",
            "boeblingen": "Böblingen", "böblingen": "Böblingen",
        }
        if low in display_map:
            return display_map[low]
        if "," in low:
            return ", ".join(self._fmt_place(p) for p in low.split(",") if p.strip())
        particles = {"am", "bei", "upon", "de", "la", "le", "du", "di", "del",
                     "der", "den", "und", "van", "von", "sur", "sous", "im", "in"}
        words = low.split()
        out = []
        for w in words:
            if w in self.config.CASING_MAP:
                out.append(self.config.CASING_MAP[w])
            elif w in particles:
                out.append(w)
            elif len(w) == 2 and w.isalpha():
                out.append(w.upper())  # state / country codes: ny -> NY
            elif "-" in w:
                # capitalize after hyphens: emilia-romagna -> Emilia-Romagna
                out.append("-".join(part.capitalize() for part in w.split("-")))
            else:
                out.append(w.capitalize())
        return " ".join(out)

    def _norm(self, s):
        """Normalize a place string: lowercase, strip diacritics
        (Wrocław -> wroclaw, München -> munchen)."""
        try:
            # characters with no NFKD decomposition must be transliterated manually
            s = s.translate(str.maketrans({
                "\u0142": "l", "\u0141": "L", "\u0105": "a", "\u0104": "A",
                "\u0119": "e", "\u0118": "E", "\u0144": "n", "\u0143": "N",
                "\u015b": "s", "\u015a": "S", "\u017a": "z", "\u0179": "Z",
                "\u017c": "z", "\u017b": "Z", "\u0107": "c", "\u0106": "C",
                "\u00f8": "o", "\u00d8": "O", "\u00e5": "a", "\u00c5": "A",
                "\u00e6": "ae", "\u00c6": "AE", "\u0153": "oe", "\u0152": "OE",
                "\u00df": "ss", "\u011f": "g", "\u011e": "G", "\u0131": "i",
                "\u015f": "s", "\u015e": "S", "\u0219": "s", "\u0218": "S",
                "\u021b": "t", "\u021a": "T", "\u0171": "u", "\u0151": "o",
                "\u0103": "a", "\u0102": "A", "\u010d": "c", "\u010c": "C",
                "\u0111": "d", "\u0110": "D", "\u0161": "s", "\u0160": "S",
                "\u017e": "z", "\u017d": "Z", "\u00f0": "d", "\u00d0": "D",
                "\u00fe": "th", "\u00de": "TH",
            }))
            s = unicodedata.normalize("NFKD", s)
            s = s.encode("ascii", "ignore").decode()
        except Exception:
            pass
        return re.sub(r"\s+", " ", s).strip().lower()

    def _fmt_region(self, region_lower):
        if region_lower in self.config.CASING_MAP:
            return self.config.CASING_MAP[region_lower]
        return region_lower.title()

    def _location_from_line(self, line):
        """Evaluate one candidate line/part as a location. Returns formatted location or None."""
        if not line:
            return None
        # strip parenthetical content completely (e.g. "(Part Time)", "(w/m/d)")
        line = re.sub(r"\(.*?\)", "", line)
        line = line.strip(" \t,;•.()[]-*")
        if not line:
            return None
        # strip trailing " office|site|campus|hub" etc., then re-evaluate
        stripped = re.sub(r"\b(office|site|campus|hub|location|headquarters)\b\s*$",
                          "", line.strip(), flags=re.IGNORECASE).strip()
        if stripped and stripped != line:
            return self._location_from_line(stripped)

        low = line.lower()
        if len(low) < 2 or len(low) > 60 or not re.search(r"[a-zA-ZÀ-ÿ]", line):
            return None
        nlow = self._norm(low)
        if low in {"global", "worldwide", "united", "anywhere"}:
            return None

        # 1) exact known place (diacritic-insensitive: Wrocław, München, Garching Bei München)
        if low in self.KNOWN_PLACES or nlow in self.NORM_KNOWN:
            canonical = self.NORM_KNOWN.get(nlow, low)
            return self._fmt_place(canonical)

        # 1b) "City, Country" / "City, State" comma pattern — checked BEFORE the
        #     reject list so office names get salvaged:
        #     "The River Building Hq, London" -> "London"
        if "," in line or "，" in line:
            raw_segs = re.split(r"[,，]", line)
            segs = [s.strip(" \t") for s in raw_segs if s.strip(" \t")]
            if segs:
                def _is_known_seg(sg):
                    sg_low = sg.lower()
                    sg_n = self._norm(sg_low)
                    return (sg_low in self.KNOWN_PLACES or sg_n in self.NORM_KNOWN
                            or sg_low in self.config.COUNTRIES_AND_REGIONS
                            or (re.fullmatch(r"[a-z]{2}", sg_low)
                                and (sg_low in self.STATE_CODES or sg_low in self.COUNTRY_CODES)))
                def _is_junk_seg(sg):
                    # title/dept garbage embedded in the location string
                    # ("Associate Optometrist-Katy, TX", "NL Credit Controller - ...")
                    return (self.config.ROLE_WORD_PATTERN.search(sg)
                            or bool(self.LOCATION_REJECT_RE.search(sg.lower())))
                # walk backward from the last segment:
                #   - keep known places / state codes
                #   - SKIP junk segments (role words, departments) so the real
                #     place at the end still wins:
                #     "Hesse, Germany Lakebase Specialist Hesse, Germany" -> "Hesse, Germany"
                #     "Boston, MA 14457 Recruiter (boston, MA" -> "Boston, MA"
                #   - stop at clean unknown segments (office names):
                #     "The River Building Hq, London" -> "London"
                keep = []
                i = len(segs) - 1
                stopped_at = None
                while i >= 0:
                    if re.fullmatch(r"[a-z]{2}", segs[i].lower()) and not _is_known_seg(segs[i]):
                        i -= 1      # unknown trailing code ("Paris, FR" -> drop FR)
                        continue
                    if _is_known_seg(segs[i]):
                        keep.append(segs[i])
                        i -= 1
                        continue
                    if _is_junk_seg(segs[i]):
                        i -= 1      # drop title/department junk
                        continue
                    stopped_at = segs[i]
                    break
                if keep:
                    keep.reverse()
                    # drop duplicates anywhere ("Madrid, Spain, Madrid" -> "Madrid, Spain")
                    deduped = []
                    seen_seg = set()
                    for seg in keep:
                        sk = seg.lower()
                        if sk not in seen_seg:
                            seen_seg.add(sk)
                            deduped.append(seg)
                    keep = deduped
                    # v7: in "City, XX", US/Canadian state/province codes take
                    # priority over overlapping country codes (CA, IN, IL, MA, ...).
                    # This prevents "Chicago, IL" -> "Chicago, Israel".
                    mapped_keep = []
                    for seg in keep:
                        code = seg.lower()
                        if re.fullmatch(r"[a-z]{2}", code) and code in self.STATE_CODES:
                            mapped_keep.append(code.upper())
                        elif re.fullmatch(r"[a-z]{2}", code) and code in self.COUNTRY_CODES:
                            mapped_keep.append(self.COUNTRY_CODES[code])
                        else:
                            mapped_keep.append(seg)
                    keep = mapped_keep
                    # never emit a BARE state code ("Associate, TX" -> reject)
                    if len(keep) == 1 and re.fullmatch(r"[a-z]{2}", keep[0].lower()):
                        code = keep[0].upper()
                        if stopped_at is not None and not _is_junk_seg(stopped_at):
                            sa = stopped_at.strip()
                            sa_low = sa.lower()
                            # typo / OCR fix
                            for bad, good in self.config.TYPO_MAP.items():
                                if sa_low == bad:
                                    sa = good
                                    sa_low = good
                                    break
                            # full-string known lookup first ("Fort Lauderdale")
                            if sa_low in self.KNOWN_PLACES or self._norm(sa_low) in self.NORM_KNOWN:
                                return f"{self._fmt_place(self._norm(sa_low))}, {code}"
                            # else: trailing known-word run ("Yieldstar Austin" -> "Austin")
                            sa_words = sa_low.split()
                            run = []
                            for w in reversed(sa_words):
                                w_n = self._norm(w)
                                if (w in self.KNOWN_PLACES or w_n in self.NORM_KNOWN
                                        or w in self.config.COUNTRIES_AND_REGIONS):
                                    run.append(w)
                                else:
                                    break
                            run = list(reversed(run))
                            if run:
                                countries = [
                                    w for w in run
                                    if w in self.config.COUNTRIES_AND_REGIONS
                                    and w not in self.KNOWN_CITIES
                                    and w not in self.MULTI_WORD_CITIES
                                ]
                                cities = [w for w in run if w not in countries]
                                if countries and cities:
                                    # "Frames - Turkey Istanbul, TN" -> "Istanbul, Turkey"
                                    return f"{self._fmt_place(self._norm(cities[-1]))}, {self._fmt_place(self._norm(countries[-1]))}"
                                if countries:
                                    return self._fmt_place(self._norm(countries[-1]))
                                # "Yieldstar Austin, TX" -> "Austin, TX"
                                return f"{self._fmt_place(self._norm(cities[-1]))}, {code}"
                        return None
                    return ", ".join(self._fmt_place(self._norm(s)) for s in keep)
                return None

        # 1c) trailing run of known place words ("Place Amedee Bonnet Lyon" -> "Lyon",
        #     "Barcelona Spain" -> "Barcelona, Spain") — checked before the reject
        #     list so a real place at the end is salvaged even when junk precedes it
        words = low.split()
        if len(words) >= 2:
            known_run = []
            for w in reversed(words):
                w_n = self._norm(w)
                # Country codes are intentionally not expanded in free text: ID in
                # "Entra ID" and CA in titles are not locations. Codes remain valid
                # only in comma-address form handled above.
                if (w in self.KNOWN_PLACES or w_n in self.NORM_KNOWN
                        or w in self.config.COUNTRIES_AND_REGIONS):
                    known_run.append(w)
                else:
                    break
            known_run = list(reversed(known_run))
            if known_run:
                parts_out = []
                for w in known_run:
                    parts_out.append(self._fmt_place(self._norm(w)))
                return ", ".join(parts_out)

        # 2) reject words (UI text, departments, brands, abbreviations, job words,
        #    workload terms, tech stacks, business units)
        if self.LOCATION_REJECT_RE.search(low):
            return None

        # 3) role words / title blacklist
        if self.config.ROLE_WORD_PATTERN.search(line) or low in self.config.HARD_TITLE_BLACKLIST:
            return None

        # 4) currency / long digit runs / emails / symbols
        if re.search(r"[£$€¥%@&+]", line) or re.search(r"\d{3,}", low) or re.search(r"\d+%", low):
            return None

        # 5) work-mode / workload words — try to salvage a city after a mode prefix
        if re.search(
            r"\b(full[- ]?time|part[- ]?time|internship|intern|trainee|stage|"
            r"werkstudent|working student|praktikum|fixed[- ]?term|permanent|"
            r"contract|temporary|remote|hybrid|onsite|on[- ]?site|home office|"
            r"salary|annum|hourly|experience|years?|days?|weeks?|months?|"
            r"vollzeit|teilzeit|seasonal)\b", low,
        ):
            m = re.search(
                r"\b(?:remote|hybrid|onsite|on-site|full[- ]?time|part[- ]?time|"
                r"internship|trainee|stage|werkstudent|vollzeit|teilzeit|seasonal)\b"
                r"[^a-zA-Z]{1,20}([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'\-]{2,45})$",
                line, re.IGNORECASE,
            )
            if m:
                cand = m.group(1).strip()
                if cand.lower() != line.lower():
                    res = self._location_from_line(cand)
                    if res:
                        return res
            return None



        # 7) bare 2-letter codes are NEVER a location on their own
        #    ("FL", "GA", "DE" from store data are useless; state codes are
        #    only accepted inside "City, XX" via the comma branch above)
        if re.fullmatch(r"[a-z]{2}", low):
            return None

        # 8) single known city / country / region (diacritic-insensitive)
        if low in self.KNOWN_CITIES or low in self.config.COUNTRIES_AND_REGIONS or nlow in self.NORM_KNOWN:
            canonical = self.NORM_KNOWN.get(nlow, low)
            return self._fmt_place(canonical)

        # 9) multi-word city completion (e.g. "Palo" -> "Palo Alto")
        for two in self.MULTI_WORD_CITIES:
            if low == two or low.startswith(two + " "):
                return self._fmt_place(two)

        # 10) heuristic: a phrase is a plausible place ONLY if every word is a
        #     known city/country/region token (NO free-form proper-noun guessing —
        #     that produced "Java", "Vice President", "Mack", "Hotels", ...)
        if len(words) <= 5:
            known_hits = sum(
                1 for w in words
                if w in self.KNOWN_PLACES or self._norm(w) in self.NORM_KNOWN
                or w in self.config.COUNTRIES_AND_REGIONS
            )
            if known_hits and known_hits == len(words) and len(low) >= 3:
                return ", ".join(self._fmt_place(self._norm(w)) for w in words)
        return None

    def extract_location(self, text):
        if not text:
            return "Not Specified"
        text = self.fix_encoding(str(text))
        if self._norm(text.strip()) in {"global", "worldwide", "united", "anywhere"}:
            return "Not Specified"

        # v7: preserve structural boundaries. Location hints are passed as the
        # first line, so evaluate lines independently before any flattening.
        raw_lines = [
            re.sub(r"[ \t]+", " ", part).strip()
            for part in re.split(r"[\r\n|•;]+", text)
            if part.strip()
        ]
        for line in raw_lines:
            res = self._location_from_line(line)
            if res:
                return res
            # Explicit City - Country or Mode - City structures.
            for part in re.split(r"\s+[-–—]\s+", line):
                res = self._location_from_line(part)
                if res:
                    return res

        # Last fallback: exact full text after safe space normalization.
        flat = re.sub(r"[ \t]+", " ", text).strip()
        if "\n" not in flat and "\r" not in flat:
            res = self._location_from_line(flat)
            if res:
                return res
        return "Not Specified"

    # FIXED: URL-path location parser, now validation-gated.
    # Only returns a value if it is a KNOWN place (city/country/region) found as a
    # segment AFTER a real job marker. UI route segments (JobDetail, externaljobs,
    # jobsuche) and last-segment fallbacks are rejected, killing the "JobDetail"
    # garbage and truncated city names ("Palo" from "Palo-Alto-CA").
    def extract_location_from_url(self, url):
        if not url:
            return None
        try:
            url_decoded = urllib.parse.unquote(url)
            parsed = urlparse(url_decoded)
            path = parsed.path
            segments = [s for s in path.split("/") if s]
            if not segments:
                return None

            # "in-[location]" pattern (e.g. /jobs-in-berlin)
            in_match = re.search(r"\bin-([a-z-]+)\b", path.lower())
            if in_match:
                cand = in_match.group(1).replace("-", " ").strip()
                cand = re.sub(r"\b(jid|id|\d+)\b", "", cand, flags=re.IGNORECASE).strip()
                if cand in self.KNOWN_PLACES:
                    return self._fmt_place(cand)

            # Candidate = segment right after the LAST job marker in the path
            # (e.g. /en/careers/jobs/hsinchu/123 -> "hsinchu", not "jobs")
            candidate = None
            for i, s in enumerate(segments):
                if s.lower() in self.config.URL_JOB_MARKERS and i + 1 < len(segments):
                    candidate = segments[i + 1]
            if candidate is None:
                # FIXED: Hays-style URLs bury the city inside one giant hyphenated
                # slug with NO standalone job marker
                # ("stellenangebote-jobs-detail-...-karlsruhe-883930/1").
                # Scan every slug part across all path segments instead.
                all_parts = []
                for seg in segments:
                    seg = seg.split(".")[0]
                    all_parts.extend(
                        p for p in re.split(r"[\-_]", seg)
                        if p and not p.isdigit() and len(p) >= 3
                    )
                for n in range(min(3, len(all_parts)), 0, -1):
                    for i in range(len(all_parts) - n + 1):
                        for sep in (" ", "-"):
                            joined = sep.join(all_parts[i:i + n]).lower()
                            if joined in self.KNOWN_PLACES or self._norm(joined) in self.NORM_KNOWN:
                                return self._fmt_place(joined)
                for p in all_parts:
                    p_low = p.lower()
                    if (p_low in self.KNOWN_CITIES or p_low in self.config.COUNTRIES_AND_REGIONS
                            or self._norm(p_low) in self.NORM_KNOWN):
                        return self._fmt_place(p_low)
                return None

            candidate = candidate.split(".")[0]
            parts = [p for p in re.split(r"[\-_]", candidate) if p and not p.isdigit()]
            if not parts:
                return None

            # Longest-first known-place subsequence scan within the slug parts
            best = None
            for n in range(min(4, len(parts)), 0, -1):
                for i in range(len(parts) - n + 1):
                    joined = " ".join(parts[i:i + n]).lower()
                    if joined in self.KNOWN_PLACES or self._norm(joined) in self.NORM_KNOWN:
                        best = joined
                        break
                if best:
                    break
            if best:
                return self._fmt_place(best)

            # Last resort: a single part that is a known city/country/region
            for p in parts:
                p_low = p.lower()
                if (p_low in self.KNOWN_CITIES or p_low in self.config.COUNTRIES_AND_REGIONS
                        or self._norm(p_low) in self.NORM_KNOWN):
                    return self._fmt_place(p_low)
        except Exception:
            pass
        return None

    # FIXED: Added a robust country and region scanner fallback.
    # Searches any text for major global and European country names or regional states (Piemonte, Lombardia, etc.) as whole words.
    # FIXED: Region scanner, now end-anchored and casing-aware.
    # "global"/"worldwide" are excluded, "uk" becomes "UK", and matches are only
    # accepted at end-of-string (title scans) or end-of-line (context scans).
    def extract_country_or_region(self, text, end_of_string=True):
        if not text:
            return None
        text = self.fix_encoding(text)
        low = text.lower()
        m = self.REGION_END_RE.search(low) if end_of_string else self.REGION_LINE_RE.search(low)
        if m:
            return self._fmt_region(m.group(1))
        return None

    def parse_job_metadata(self, name, title, context_text, clean_url=""):
        title = self.fix_encoding(title or "")
        context_text = self.fix_encoding(context_text or "")
        combined = f"{title}\n{context_text}".strip()
        cl = combined.casefold()

        # v7: card/listing text cannot prove immigration support or Blue Card.
        eu_blue_card = "Unknown"
        reloc_support = "Unknown"
        workload = "Unknown"
        if any(k in cl for k in ["part time", "part-time", "parttime", "teilzeit", "deeltijd"]):
            workload = "Part-time"
        elif any(k in cl for k in [
            "internship", "tirocinio", "apprendistato", "trainee", "praktikum",
            "stagiaire", "ausbildung", "duales studium", "working student",
            "werkstudent", "stage "
        ]):
            workload = "Internship"
        elif any(k in cl for k in ["full time", "full-time", "fulltime", "vollzeit", "voltijd"]):
            workload = "Full-time"
        elif any(k in cl for k in ["contract", "fixed-term", "fixed term", "temporary"]):
            workload = "Contract"

        work_mode = "Unknown"
        remote_hit = any(k in cl for k in [
            "fully remote", "remote-first", "remote", "da remoto", "remoto",
            "home office", "homeoffice", "thuiswerk", "télétravail"
        ])
        hybrid_hit = any(k in cl for k in ["hybrid", "ibrido", "smart working", "smartworking", "hybride"])
        if remote_hit and hybrid_hit:
            work_mode = "Remote/Hybrid"
        elif remote_hit:
            work_mode = "Remote"
        elif hybrid_hit:
            work_mode = "Hybrid"
        elif any(k in cl for k in ["on-site", "onsite", "in-office", "in office"]):
            work_mode = "On-site"

        location, source = "Not Specified", "none"
        # Explicit card location hint/context, then title and URL.
        loc = self.extract_location(context_text)
        if loc != "Not Specified":
            location, source = loc, "card"
        if location == "Not Specified":
            loc = self.extract_location(title)
            if loc != "Not Specified":
                location, source = loc, "title"
        if location == "Not Specified" and clean_url:
            url_loc = self.extract_location_from_url(clean_url)
            if url_loc and self._norm(url_loc) not in {"global", "worldwide", "united"}:
                location, source = url_loc, "url"
        if location == "Not Specified":
            reg = self.extract_country_or_region(context_text, end_of_string=False)
            if reg and self._norm(reg) not in {"global", "worldwide", "united"}:
                location, source = reg, "region"

        # Reject company names as locations. v7 never stamps headquarters into
        # the verified Job Location field.
        if location != "Not Specified":
            low_loc = location.casefold().strip()
            loc_words = set(re.findall(r"[a-zà-ÿ]+", low_loc))
            name_words = set(re.findall(r"[a-zà-ÿ]+", name.casefold()))
            if loc_words and loc_words <= name_words and self._norm(low_loc) not in self.NORM_KNOWN:
                location, source = "Not Specified", "none"
        return location, f"{workload} / {work_mode}", eu_blue_card, reloc_support, source

    def canonical_job_id(self, company, url, title="", location="", provider="auto"):
        """Stable identity independent of apply/detail mirror URLs."""
        u = urllib.parse.unquote(url or "")
        candidates = []
        for pattern in (
            r"(?i)(?:jobid|job_id|gh_jid|reqid|requisitionid|career_job_req_id|postingid|r)=([A-Za-z]*\d{4,})",
            r"(?i)(?:^|[/_-])(R\d{5,})(?:[-_/?]|$)",
            r"(?i)/jobs?/(\d{5,})(?:/|$)",
            r"(?i)/job/([0-9a-f]{8}-[0-9a-f-]{27,})(?:/|$)",
            r"(?i)/([0-9a-f]{8}-[0-9a-f-]{27,})(?:/|$)",
            r"(?i)/(\d{5,})(?:/?(?:[?#]|$))",
        ):
            candidates.extend(re.findall(pattern, u))
        identity = candidates[0].casefold() if candidates else ""
        p = urlparse(url or "")
        if not identity:
            identity = (p.netloc.casefold().removeprefix("www.") + p.path.rstrip("/").casefold())
        if not identity and title:
            identity = f"title:{self._norm(title)}|loc:{self._norm(location)}"
        return f"{company.casefold()}|{provider.casefold()}|{identity}"

    def _record_quality(self, rec):
        score = 0
        if rec.get("URL Type") == "real": score += 20
        if rec.get("Job Location") not in {"Unknown", "Not Specified", "Global", "United"}: score += 8
        if rec.get("Location Source") in {"card", "detail"}: score += 5
        if rec.get("Raw Job Title"): score += 1
        if rec.get("Raw Location"): score += 1
        if re.search(r"applicationmethods|/apply(?:/|$)", rec.get("Job URL", ""), re.I): score -= 30
        return score

    def _scope_allows(self, target_row, location, context="", url=""):
        policy = (target_row.get("scope_policy") or "global").lower()
        target = (target_row.get("target_country") or "Global").strip()
        if policy == "global" or target.casefold() == "global":
            return True
        if policy == "seed_url":
            return True
        blob = self._norm(" ".join([location or "", context or "", urllib.parse.unquote(url or "")]))
        aliases = {
            "germany": {"germany", "deutschland", "berlin", "hamburg", "munich", "munchen", "muenchen", "frankfurt", "cologne", "koln", "koeln", "dusseldorf", "duesseldorf", "stuttgart", "hannover", "bremen", "leipzig", "dresden", "bayern", "bavaria"},
            "italy": {"italy", "italia", "milan", "milano", "rome", "roma", "turin", "torino", "bologna", "napoli", "parma", "venice", "venezia", "florence", "firenze", "lombardia", "lombardy", "piemonte", "toscana", "sicilia"},
            "netherlands": {"netherlands", "nederland", "amsterdam", "rotterdam", "utrecht", "haarlem", "delft", "eindhoven", "north holland", "noord holland", "zuid holland"},
            "united kingdom": {"united kingdom", "england", "scotland", "wales", "northern ireland", "london", "manchester", "birmingham", "edinburgh", "glasgow", "uk"},
            "ireland": {"ireland", "dublin", "cork", "galway", "limerick"},
        }
        return any(re.search(r"(?:^|[^a-z])" + re.escape(a) + r"(?:$|[^a-z])", blob) for a in aliases.get(target.casefold(), {target.casefold()}))

    def _fetch_provider_jobs(self, target_row):
        """Provider APIs first. Returns (jobs, diagnostic)."""
        provider = (target_row.get("provider") or "auto").lower()
        slug = (target_row.get("board_slug") or "").strip()
        if not slug or provider not in {"greenhouse", "ashby", "lever", "personio", "recruitee"}:
            return [], "provider adapter not configured"
        try:
            if provider == "greenhouse":
                url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
            elif provider == "ashby":
                url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false"
            elif provider == "lever":
                url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
            elif provider == "personio":
                url = f"https://{slug}.jobs.personio.de/xml?language=en"
            else:
                url = f"https://{slug}.recruitee.com/api/offers/"
            headers = {
                "User-Agent": "Mozilla/5.0 Chrome/126 Safari/537.36",
                "Accept": "application/json,text/xml,*/*",
            }
            raw = self._http_fetch_with_retry(url, headers)
            jobs = []
            if provider == "personio":
                import xml.etree.ElementTree as ET
                root = ET.fromstring(raw)
                for pos in root.findall(".//position"):
                    pid = (pos.findtext("id") or "").strip()
                    job_url = (pos.findtext("jobUrl") or "").strip()
                    if not job_url and pid:
                        job_url = f"https://{slug}.jobs.personio.de/job/{pid}"
                    jobs.append({
                        "job_title": (pos.findtext("name") or "").strip(),
                        "job_url": job_url,
                        "location_hint": (pos.findtext("office") or "").strip(),
                        "card_context": " | ".join(filter(None, [pos.findtext("department"), pos.findtext("employmentType"), pos.findtext("schedule")])),
                        "extraction_method": "personio_api",
                    })
                return jobs, f"personio API: {len(jobs)}"
            data = json.loads(raw)
            if provider == "greenhouse":
                for it in data.get("jobs") or []:
                    loc = (it.get("location") or {}).get("name") or ""
                    content = re.sub(r"<[^>]+>", " ", it.get("content") or "")
                    jobs.append({"job_title": it.get("title") or "", "job_url": it.get("absolute_url") or "", "location_hint": loc, "card_context": content[:1200], "extraction_method": "greenhouse_api"})
            elif provider == "ashby":
                for it in data.get("jobs") or []:
                    jobs.append({"job_title": it.get("title") or "", "job_url": it.get("jobUrl") or it.get("applyUrl") or "", "location_hint": it.get("location") or "", "card_context": " | ".join(filter(None, [it.get("department"), it.get("employmentType"), it.get("workplaceType")])), "extraction_method": "ashby_api"})
            elif provider == "lever":
                for it in data:
                    cats = it.get("categories") or {}
                    loc = cats.get("location") or cats.get("allLocations") or ""
                    if isinstance(loc, list): loc = ", ".join(loc)
                    jobs.append({"job_title": it.get("text") or "", "job_url": it.get("hostedUrl") or "", "location_hint": str(loc), "card_context": " | ".join(filter(None, [cats.get("team"), cats.get("commitment"), it.get("workplaceType")])), "extraction_method": "lever_api"})
            elif provider == "recruitee":
                for it in data.get("offers") or []:
                    jobs.append({"job_title": it.get("title") or "", "job_url": it.get("careers_url") or "", "location_hint": it.get("location") or "", "card_context": it.get("department") or "", "extraction_method": "recruitee_api"})
            return jobs, f"{provider} API: {len(jobs)}"
        except Exception as exc:
            return [], f"{provider} API failed: {type(exc).__name__}: {exc}"

    def extract_visible_jobs(self, target):
        all_results = []
        seen = set()
        extractors = [
            self._extract_json_ld,
            self._extract_next_data_jobs,
            self._extract_semantic_cards,
            self._extract_anchor_sweep,
        ]
        for extractor in extractors:
            try:
                rows = extractor(target)
                for j in rows:
                    title = (j.get("job_title") or "").strip()
                    url = (j.get("job_url") or "").strip()
                    loc = (j.get("location_hint") or "").strip()
                    key = f"{title.lower()}|{url.lower()}|{loc.lower()}"
                    if title and url and key not in seen:
                        seen.add(key)
                        all_results.append(j)
            except Exception as exc:
                print(f"      extractor {extractor.__name__} failed: {type(exc).__name__}: {exc}")
        if len(all_results) < 3:
            for extractor in [self._extract_url_pattern_clusters, self._extract_click_cards]:
                try:
                    rows = extractor(target)
                    for j in rows:
                        title = (j.get("job_title") or "").strip()
                        url = (j.get("job_url") or "").strip()
                        loc = (j.get("location_hint") or "").strip()
                        key = f"{title.lower()}|{url.lower()}|{loc.lower()}"
                        if title and url and key not in seen:
                            seen.add(key)
                            all_results.append(j)
                except Exception as exc:
                    print(f"      fallback extractor {extractor.__name__} failed: {type(exc).__name__}: {exc}")
        return all_results
    def _extract_json_ld(self, target):
        js = r"""
        () => {
            const jobs = [];
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            const addItem = (item) => {
                if (!item || typeof item !== 'object') return;
                const type = item['@type'];
                const isJob =
                    type === 'JobPosting' ||
                    (Array.isArray(type) && type.includes('JobPosting'));
                if (!isJob) return;
                let locStr = '';
                const loc = item.jobLocation;
                if (Array.isArray(loc)) {
                    locStr = loc.map(l => {
                        const a = l.address || {};
                        return [a.addressLocality, a.addressRegion, a.addressCountry].filter(Boolean).join(', ');
                    }).filter(Boolean).join(' | ');
                } else if (loc && loc.address) {
                    const a = loc.address;
                    locStr = [a.addressLocality, a.addressRegion, a.addressCountry].filter(Boolean).join(', ');
                }
                const rawUrl = item.url || item['@id'] || window.location.href;
                let fullUrl = rawUrl;
                try { fullUrl = new URL(rawUrl, window.location.href).href; } catch(e) {}
                jobs.push({
                    job_title: item.title || item.name || '',
                    job_url: fullUrl,
                    card_context: String(item.description || '').substring(0, 800),
                    location_hint: locStr
                });
            };
            scripts.forEach(s => {
                try {
                    const data = JSON.parse(s.textContent);
                    const items = Array.isArray(data) ? data : (data['@graph'] || [data]);
                    items.forEach(addItem);
                } catch(e) {}
            });
            return jobs;
        }
        """
        return target.evaluate(js) or []
    def _extract_next_data_jobs(self, target):
        js = r"""
        () => {
            const jobs = [];
            const seen = new Set();
            const roleRe = /\b(engineer|developer|manager|analyst|scientist|specialist|consultant|architect|designer|director|lead|head|principal|senior|junior|intern|trainee|associate|advisor|officer|administrator|recruiter|counsel|lawyer|accountant|controller|planner|coordinator|assistant|representative|agent|technician|mechanic|operator|expert|owner|scrum master|product owner|sales|marketing|finance|security|devops|frontend|backend|full stack|fullstack|software|data|qa|quality)\b/i;
            
            // FIXED: Upgraded with a helper function to resolve complex dynamic locations and prevent [object Object] serializations
            const getLocString = (loc) => {
                if (!loc) return '';
                if (typeof loc === 'string') return loc;
                if (typeof loc === 'object') {
                    const parts = [
                        loc.name, loc.city, loc.office, loc.country, loc.region, loc.locationName,
                        loc.addressLocality, loc.addressCountry, loc.addressRegion
                    ].filter(Boolean);
                    if (parts.length > 0) return parts.join(', ');
                    return JSON.stringify(loc);
                }
                return String(loc);
            };
            const add = (title, url, ctx, loc) => {
                title = String(title || '').trim();
                url = String(url || '').trim();
                if (!title || title.length < 4 || title.length > 150) return;
                if (!roleRe.test(title)) return;
                if (!url) {
                    const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').substring(0, 70);
                    url = window.location.href.split('?')[0].split('#')[0] + '#job=' + slug;
                } else {
                    try { url = new URL(url, window.location.href).href; } catch(e) {}
                }
                const key = (title + '|' + url).toLowerCase();
                if (seen.has(key)) return;
                seen.add(key);
                jobs.push({
                    job_title: title,
                    job_url: url,
                    card_context: String(ctx || '').substring(0, 800),
                    location_hint: getLocString(loc)
                });
            };
            const scan = (obj, depth = 0) => {
                if (!obj || depth > 8) return;
                if (Array.isArray(obj)) {
                    obj.forEach(x => scan(x, depth + 1));
                    return;
                }
                if (typeof obj !== 'object') return;
                const keys = Object.keys(obj);
                const keyBlob = keys.join(' ').toLowerCase();
                const title =
                    obj.title || obj.jobTitle || obj.positionTitle ||
                    obj.name || obj.label || obj.displayName;
                const url =
                    obj.url || obj.jobUrl || obj.applyUrl || obj.absoluteUrl ||
                    obj.externalUrl || obj.externalPath || obj.path || obj.link;
                const loc =
                    obj.location || obj.locationName || obj.city ||
                    obj.office || obj.country || obj.region;
                const id =
                    obj.jobId || obj.jobID || obj.requisitionId ||
                    obj.reqId || obj.postingId || obj.id;
                if (title && (url || id) && /(job|posting|position|requisition|vacancy|opening|role)/.test(keyBlob)) {
                    add(title, url, JSON.stringify(obj).slice(0, 800), loc);
                }
                for (const k of keys) {
                    const v = obj[k];
                    if (v && typeof v === 'object') scan(v, depth + 1);
                }
            };
            const scripts = document.querySelectorAll(
                'script#__NEXT_DATA__, script[type="application/json"], script[id*="__NEXT_DATA__"]'
            );
            scripts.forEach(s => {
                const txt = s.textContent || '';
                if (!txt || txt.length > 8000000) return;
                try {
                    const data = JSON.parse(txt);
                    scan(data);
                } catch(e) {}
            });
            return jobs;
        }
        """
        return target.evaluate(js) or []
    def _extract_semantic_cards(self, target):
        js = r"""
        () => {
        } """ + JS_HELPERS + r"""
            const jobs = [];
            const seen = new Set();
            const cardSelectors = [
                '[data-job-id]', '[data-jobid]', '[data-job]',
                '[data-position-id]', '[data-posting-id]', '[data-requisition-id]',
                '[data-automation*="job" i]',
                '[data-testid*="job-card" i]', '[data-testid*="job-item" i]',
                '[data-testid*="posting" i]', '[data-qa*="job" i]',
                'ef-jobs-list-item',
                '.job-card', '.job-item', '.job-listing', '.job-row',
                '.job-result', '.job-post', '.job-tile', '.job-entry',
                '.position-card', '.position-item', '.position-listing',
                '.career-card', '.career-item', '.opening-card',
                '.vacancy-card', '.vacancy-item', '.role-card',
                '.posting', '.posting-item',
                '[class*="job-card" i]', '[class*="job-item" i]',
                '[class*="job-listing" i]', '[class*="job-row" i]',
                '[class*="position-card" i]', '[class*="position-item" i]',
                '[class*="vacancy-card" i]', '[class*="opening" i]',
                '[class*="posting" i]',
                'article[class*="job" i]', 'article[class*="position" i]',
                'li[class*="job" i]', 'li[class*="position" i]',
                'li[class*="posting" i]', 'tr[class*="job" i]',
                'tr[class*="position" i]',
                '[role="link"]', '[role="button"]', '[data-item="true"]', '[data-info]'
            ];
            const cards = [];
            for (const sel of cardSelectors) {
                for (const c of querySelectorAllDeep(sel)) cards.push(c);
            }
            cards.forEach(card => {
                if (!card || !isVisible(card) || isBadScope(card)) return;
                const fullText = cleanText(card.innerText || card.textContent || '');
                if (fullText.length < 8 || fullText.length > 3000) return;
                const linkCount = querySelectorAllDeep('a[href]', card).length;
                if (linkCount > 20) return;
                const attrs = cleanText([
                    getClassName(card),
                    card.id || '',
                    card.getAttribute?.('data-job-id') || '',
                    card.getAttribute?.('data-jobid') || '',
                    card.getAttribute?.('data-posting-id') || '',
                    card.getAttribute?.('data-requisition-id') || '',
                    card.getAttribute?.('data-testid') || '',
                    card.getAttribute?.('data-qa') || '',
                    card.getAttribute?.('data-automation') || ''
                ].join(' '));
                const hasJobAttr = /(job|position|posting|opening|vacancy|role|requisition)/i.test(attrs);
                let jobUrl = pickJobUrl(card);
                const title = titleFromScope(card);
                const loc = locationFromScope(card);
                if (!title) return;
                if (!jobUrl && roleWordRe.test(title)) {
                    const hasContextSignal = loc || /(full[- ]?time|part[- ]?time|intern|remote|hybrid|onsite|on-site)/i.test(fullText);
                    if (hasContextSignal) jobUrl = synthJobUrl(title, loc);
                }
                if (!jobUrl) return;
                const key = (title + '|' + jobUrl + '|' + loc).toLowerCase();
                if (seen.has(key)) return;
                seen.add(key);
                jobs.push({
                    job_title: title,
                    job_url: jobUrl,
                    card_context: fullText.substring(0, 800),
                    location_hint: loc
                });
            });
            return jobs;
        }
        """
        js_fixed = js.replace("() => {\n        } ", "() => { ")
        return target.evaluate(js_fixed) or []
    def _extract_anchor_sweep(self, target):
        js = r"""
        () => {
        } """ + JS_HELPERS + r"""
            const jobs = [];
            const seen = new Set();
            for (const a of querySelectorAllDeep('a[href]')) {
                if (!a || !isVisible(a) || isBadScope(a)) continue;
                const href = a.href;
                if (!looksJobUrl(href)) continue;
                const scope = scopeForAnchor(a);
                if (!scope || isBadScope(scope)) continue;
                const scopeText = cleanText(scope.innerText || scope.textContent || '');
                if (scopeText.length > 3000) continue;
                const linkCount = querySelectorAllDeep('a[href]', scope).length;
                if (linkCount > 20) continue;
                let title = firstGoodLine(a.innerText || a.textContent || '');
                if (!title || genericTextRe.test(title) || uiTextRe.test(title)) {
                    title = titleFromScope(scope);
                }
                if (!title) continue;
                const loc = locationFromScope(scope);
                const key = (title + '|' + href + '|' + loc).toLowerCase();
                if (seen.has(key)) continue;
                seen.add(key);
                jobs.push({
                    job_title: title,
                    job_url: href,
                    card_context: scopeText.substring(0, 800),
                    location_hint: loc
                });
            }
            return jobs;
        }
        """
        js_fixed = js.replace("() => {\n        } ", "() => { ")
        return target.evaluate(js_fixed) or []
    def _extract_url_pattern_clusters(self, target):
        js = r"""
        () => {
        } """ + JS_HELPERS + r"""
            const groups = {};
            const jobs = [];
            const seen = new Set();
            for (const a of querySelectorAllDeep('a[href]')) {
                if (!a || !isVisible(a) || isBadScope(a)) continue;
                if (!looksJobUrl(a.href)) continue;
                try {
                    const u = new URL(a.href);
                    const seg = u.pathname.split('/').filter(Boolean);
                    if (seg.length < 2) continue;
                    const pattern = u.host + '/' + seg.slice(0, -1).join('/');
                    if (!groups[pattern]) groups[pattern] = [];
                    groups[pattern].push(a);
                } catch(e) {}
            }
            for (const [pattern, anchors] of Object.entries(groups)) {
                if (anchors.length < 2) continue;
                if (!jobUrlRe.test(pattern) && !anchors.some(a => jobUrlRe.test(a.href))) continue;
                anchors.forEach(a => {
                    const scope = scopeForAnchor(a);
                    if (!scope || isBadScope(scope)) return;
                    const title = firstGoodLine(a.innerText || '') || titleFromScope(scope);
                    if (!title || genericTextRe.test(title) || uiTextRe.test(title)) return;
                    const loc = locationFromScope(scope);
                    const ctx = cleanText(scope.innerText || '');
                    const key = (title + '|' + a.href + '|' + loc).toLowerCase();
                    if (seen.has(key)) return;
                    seen.add(key);
                    jobs.push({
                        job_title: title,
                        job_url: a.href,
                        card_context: ctx.substring(0, 800),
                        location_hint: loc
                    });
                });
            }
            return jobs;
        }
        """
        js_fixed = js.replace("() => {\n        } ", "() => { ")
        return target.evaluate(js_fixed) or []
    def _extract_click_cards(self, target):
        js = r"""
        () => {
        } """ + JS_HELPERS + r"""
            const jobs = [];
            const seen = new Set();
            const candidates = querySelectorAllDeep([
                '[data-job-id]', '[data-jobid]', '[data-posting-id]',
                '[data-requisition-id]', '[data-testid*="job" i]',
                '[class*="job-card" i]', '[class*="job-item" i]',
                '[class*="position-card" i]', '[class*="posting" i]',
                '[class*="opening" i]', '[class*="vacancy" i]',
                'li[role="listitem"]',
                'article',
                'tr',
                '[role="link"]', '[role="button"]', '[data-item="true"]', '[data-info]'
            ].join(','));
            candidates.forEach(card => {
                if (!card || !isVisible(card) || isBadScope(card)) return;
                const text = cleanText(card.innerText || card.textContent || '');
                if (text.length < 15 || text.length > 2500) return;
                const title = titleFromScope(card);
                if (!title) return;
                if (!roleWordRe.test(title)) return;
                if (genericTextRe.test(title) || uiTextRe.test(title)) return;
                const loc = locationFromScope(card);
                const contextSignal =
                    loc ||
                    /(full[- ]?time|part[- ]?time|intern|remote|hybrid|onsite|on-site|department|team|office)/i.test(text);
                if (!contextSignal) return;
                let jobUrl = pickJobUrl(card);
                if (!jobUrl) jobUrl = synthJobUrl(title, loc);
                const key = (title + '|' + jobUrl + '|' + loc).toLowerCase();
                if (seen.has(key)) return;
                seen.add(key);
                jobs.push({
                    job_title: title,
                    job_url: jobUrl,
                    card_context: text.substring(0, 800),
                    location_hint: loc
                });
            });
            return jobs;
        }
        """
        js_fixed = js.replace("() => {\n        } ", "() => { ")
        return target.evaluate(js_fixed) or []
    def wait_for_dom_quiet(self, page, target, timeout_ms=5000):
        try:
            prev = target.evaluate("""() => {
                return [
                    document.querySelectorAll('a,button,li,tr,article').length,
                    (document.body?.innerText || '').length
                ].join('|');
            }""")
            deadline = time.time() + timeout_ms / 1000
            stable_rounds = 0
            while time.time() < deadline:
                page.wait_for_timeout(500)
                curr = target.evaluate("""() => {
                    return [
                        document.querySelectorAll('a,button,li,tr,article').length,
                        (document.body?.innerText || '').length
                    ].join('|');
                }""")
                if curr == prev:
                    stable_rounds += 1
                    if stable_rounds >= 2:
                        return
                else:
                    stable_rounds = 0
                    prev = curr
        except Exception:
            pass
    def progressive_scroll_and_wait(self, page, target):
        try:
            prev_height = target.evaluate("document.body.scrollHeight")
            for step in [0.25, 0.5, 0.75, 1.0]:
                target.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {step})")
                page.wait_for_timeout(600)
            page.wait_for_timeout(1000)
            new_height = target.evaluate("document.body.scrollHeight")
            return new_height > prev_height
        except Exception:
            return False
    def aggressive_infinite_scroll(self, page, target):
        unchanged = 0
        last_height = 0
        for i in range(self.config.MAX_INFINITE_SCROLL):
            try:
                height = target.evaluate("document.body.scrollHeight")
                target.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1200)
                new_height = target.evaluate("document.body.scrollHeight")
                if new_height == height == last_height:
                    unchanged += 1
                    if unchanged >= 2:
                        return i + 1
                else:
                    unchanged = 0
                last_height = height
            except Exception:
                return i
        return self.config.MAX_INFINITE_SCROLL
    def click_load_more_repeatedly(self, page, target):
        clicks = 0
        for _ in range(self.config.MAX_LOAD_MORE_CLICKS):
            js = r"""
            () => {
            } """ + JS_HELPERS + r"""
                const patterns = [
                    /load more/i, /show more/i, /see more/i, /view more/i,
                    /more results/i, /more jobs/i, /more positions/i,
                    /carica altro/i, /mehr laden/i, /meer laden/i
                ];
                for (const el of querySelectorAllDeep('button, a')) {
                    if (!isVisible(el) || isBadScope(el)) continue;
                    const txt = cleanText(el.innerText || el.textContent || '');
                    const disabled =
                        el.disabled === true ||
                        el.getAttribute('aria-disabled') === 'true' ||
                        el.classList.contains('disabled');
                    if (disabled) continue;
                    if (patterns.some(p => p.test(txt))) {
                        // v7: require nearby job-list evidence; do not expand generic
                        // marketing, biography, FAQ or article "show more" controls.
                        let scope = el.parentElement;
                        let jobEvidence = /more jobs|more positions|more results/i.test(txt);
                        for (let depth = 0; scope && depth < 5 && !jobEvidence; depth++, scope = scope.parentElement) {
                            const attrs = [getClassName(scope), scope.id || '',
                                           scope.getAttribute?.('data-testid') || ''].join(' ');
                            const links = querySelectorAllDeep('a[href]', scope)
                                .filter(a => looksJobUrl(a.href)).length;
                            if (/job|vacanc|position|opening|career/i.test(attrs) || links >= 2) {
                                jobEvidence = true;
                            }
                        }
                        if (!jobEvidence) continue;
                        el.scrollIntoView({behavior: 'instant', block: 'center'});
                        el.click();
                        return true;
                    }
                }
                return false;
            }
            """
            js_fixed = js.replace("() => {\n            } ", "() => { ")
            try:
                clicked = target.evaluate(js_fixed)
                if not clicked:
                    break
                clicks += 1
                page.wait_for_timeout(2500)
                self.wait_for_dom_quiet(page, target, timeout_ms=4000)
            except Exception:
                break
        return clicks
    def try_increase_page_size(self, page, target):
        js = r"""
        () => {
            const selects = document.querySelectorAll('select');
            for (const sel of selects) {
                const label = [
                    sel.getAttribute('aria-label') || '',
                    sel.getAttribute('name') || '',
                    sel.id || '',
                    sel.parentElement?.innerText || ''
                ].join(' ').toLowerCase();
                if (!/(items?\s*per\s*page|per\s*page|page\s*size|show)/i.test(label)) {
                    continue;
                }
                let best = null;
                let bestNum = 0;
                for (const opt of sel.options) {
                    const n = parseInt(opt.value || opt.textContent, 10);
                    if (!isNaN(n) && n > bestNum) {
                        bestNum = n;
                        best = opt;
                    }
                }
                if (best && String(sel.value) !== String(best.value)) {
                    sel.value = best.value;
                    sel.dispatchEvent(new Event('input', {bubbles: true}));
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                    return bestNum;
                }
            }
            return 0;
        }
        """
        try:
            val = target.evaluate(js)
            if val:
                page.wait_for_timeout(2500)
                self.wait_for_dom_quiet(page, target, timeout_ms=4000)
                return val
        except Exception:
            pass
        return 0
    # FIXED: Added a robust global Next Button Fallback.
    # If standard, structured pagination blocks don't exist, we scan the whole page for visible standalone 
    # button/link elements with 'Next', REL='next', or localized equivalent text, and click them!
    def execute_advanced_pagination(self, page, target, current_page_num, seed_query_params=None):
        # FIXED: keep the seed page's filter params (e.g. IKEA orgIds=22908) when
        # following pagination links, so the regional scope isn't lost mid-crawl.
        seed_query_params = seed_query_params or []
        js = r"""
        (targetPage) => {
        } """ + JS_HELPERS + r"""
            const isDisabled = (el) => {
                if (!el) return true;
                return el.disabled === true ||
                       el.getAttribute('aria-disabled') === 'true' ||
                       el.classList.contains('disabled') ||
                       el.classList.contains('mat-button-disabled');
            };
            
            const SEED = __SEED_PARAMS__;
            const mergeSeed = (href) => {
                try {
                    const u = new URL(href, window.location.href);
                    if (u.origin !== window.location.origin) return href;
                    const have = new Set(u.searchParams.keys());
                    for (const pair of SEED) {
                        if (!have.has(pair[0])) u.searchParams.append(pair[0], pair[1]);
                    }
                    return u.href;
                } catch(e) { return href; }
            };
            const clickEl = (el) => {
                if (el && el.tagName === 'A' && el.href) {
                    el.href = mergeSeed(el.href);
                }
                el.scrollIntoView({behavior: 'instant', block: 'center'});
                el.click();
            };
            const nextPatterns = [
                /next/i, /weiter/i, /suivant/i, /siguiente/i,
                /successivo/i, /volgende/i, /›/, /»/, /►/
            ];
            // 1. Structured pagination scopes (including paginators like mat-paginator)
            const paginationScopes = querySelectorAllDeep([
                'nav[aria-label*="pagination" i]',
                'nav[class*="pagination" i]',
                'nav[aria-label*="paginator" i]',
                'nav[class*="paginator" i]',
                '[class*="pagination" i]',
                '[class*="paginator" i]',
                'mat-paginator',
                '[data-testid*="pagination" i]',
                '[data-testid*="paginator" i]',
                '[role="navigation"]'
            ].join(','));
            
            for (const nav of paginationScopes) {
                if (!isVisible(nav)) continue;
                for (const el of querySelectorAllDeep('a, button, li, span[tabindex]', nav)) {
                    const txt = cleanText(el.innerText || el.textContent || '');
                    if (txt === String(targetPage) && isVisible(el) && !isDisabled(el)) {
                        const clickable = querySelectorAllDeep('a, button', el)[0] || el;
                        clickEl(clickable);
                        return 'page_number_structured';
                    }
                }
            }
            
            for (const nav of paginationScopes) {
                if (!isVisible(nav)) continue;
                for (const el of querySelectorAllDeep('a, button', nav)) {
                    if (!isVisible(el) || isDisabled(el)) continue;
                    const blob = [
                        el.innerText || '',
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('title') || '',
                        getClassName(el),
                        el.getAttribute('rel') || ''
                    ].join(' ');
                    if (nextPatterns.some(p => p.test(blob)) || /rel="?next"?/i.test(blob)) {
                        clickEl(el);
                        return 'next_structured';
                    }
                }
            }
            
            // 2. Global standalone page number buttons (for class-less pagination widgets like Bolt)
            for (const el of querySelectorAllDeep('a, button, [role="button"]')) {
                if (!isVisible(el) || isDisabled(el)) continue;
                const txt = cleanText(el.innerText || el.textContent || '');
                if (txt === String(targetPage)) {
                    // Bubble up parents to verify sibling page digits exist (ensuring it is a real paginator button)
                    let gp = el.parentElement;
                    while (gp && gp.tagName !== 'BODY') {
                        const txtGP = cleanText(gp.innerText || '');
                        const otherPage = String(targetPage === 2 ? 1 : targetPage - 1);
                        if (txtGP.includes(otherPage) && txtGP.length < 500) {
                            clickEl(el);
                            return 'global_page_number';
                        }
                        gp = gp.parentElement;
                    }
                }
            }
            // 3. Strict fallback: never click a generic carousel/content "Next".
            // Require paginator ancestry, sibling page numbers, or a page-shaped URL.
            for (const el of querySelectorAllDeep('a, button')) {
                if (!isVisible(el) || isDisabled(el)) continue;
                const blob = [
                    el.innerText || '', el.getAttribute('aria-label') || '',
                    el.getAttribute('title') || '', getClassName(el),
                    el.getAttribute('rel') || ''
                ].join(' ');
                if (!(nextPatterns.some(p => p.test(blob)) || /rel="?next"?/i.test(blob))) continue;
                let paginatorEvidence = false;
                let gp = el.parentElement;
                for (let depth = 0; gp && depth < 5; depth++, gp = gp.parentElement) {
                    const attrs = [getClassName(gp), gp.id || '',
                                   gp.getAttribute?.('aria-label') || '',
                                   gp.getAttribute?.('data-testid') || ''].join(' ');
                    const gpText = cleanText(gp.innerText || '');
                    if (/paginat|paginator|page-nav/i.test(attrs) ||
                        (/\b1\b/.test(gpText) && /\b2\b/.test(gpText) && gpText.length < 500)) {
                        paginatorEvidence = true;
                        break;
                    }
                }
                if (!paginatorEvidence && el.tagName === 'A' && el.href) {
                    try {
                        const u = new URL(el.href, window.location.href);
                        paginatorEvidence = /[?&](page|p|offset|start)=\d+/i.test(u.search) ||
                                            /\/page\/\d+\/?$/i.test(u.pathname);
                    } catch(e) {}
                }
                if (paginatorEvidence) {
                    clickEl(el);
                    return 'next_strict_fallback';
                }
            }
            return null;
        }
        """
        js_fixed = js.replace("(targetPage) => {\n        } ", "(targetPage) => { ")
        try:
            import json as _json
            js_fixed = js_fixed.replace("__SEED_PARAMS__", _json.dumps(seed_query_params))
            result = target.evaluate(js_fixed, str(current_page_num + 1))
            if result:
                page.wait_for_timeout(self.config.PAGINATION_WAIT_MS)
                self.wait_for_dom_quiet(page, target, timeout_ms=self.config.DOM_QUIET_MS)
                return True
        except Exception:
            pass
        return False
    # FIXED: Added a dynamic waiter that waits for job elements to be attached/rendered 
    # before checking landing pages or extracting to prevent premature extraction on blank loading states.
    def wait_for_job_cards_to_load(self, page, timeout_ms=5000):
        selectors = [
            ".job-card", ".job-item", ".job-listing", ".job-row",
            "a[href*='/job/']", "a[href*='/jobs/']", "a[href*='/o/']", "a[href*='/role/']",
            "[data-testid*='job']", "[class*='job-card']", "[class*='job-item']"
        ]
        combined_sel = ", ".join(selectors)
        try:
            page.wait_for_selector(combined_sel, state="attached", timeout=timeout_ms)
            page.wait_for_timeout(1000) # extra buffer for rendering
            return True
        except Exception:
            return False
    
    def _dedupe_records(self, company_jobs):
        """Canonical requisition dedupe, preferring evidence-rich real records."""
        out = {}
        for key, rec in company_jobs.items():
            cid = rec.get("Canonical Job ID") or self.canonical_job_id(
                rec.get("Company Name", ""), rec.get("Job URL", ""),
                rec.get("Job Title", ""), rec.get("Job Location", ""),
                rec.get("Provider", "auto"),
            )
            prev = out.get(cid)
            if prev is None or self._record_quality(rec) > self._record_quality(prev):
                out[cid] = rec
        return out

    def _detail_scan_for_company(self, page, name, company_jobs):
        """Visit real detail pages and enrich only from explicit page evidence."""
        if not self.detail_scan or not company_jobs:
            return
        urls=[]; seen=set()
        for rec in company_jobs.values():
            u=rec.get("Job URL", "")
            if u.startswith("http") and "#job=" not in u.lower() and u.casefold() not in seen:
                seen.add(u.casefold()); urls.append(u)
        urls=urls[:self.config.MAX_DETAIL_SCAN_PER_COMPANY]
        detail_start=time.monotonic(); enriched=0
        for url_i,url in enumerate(urls,1):
            if time.monotonic()-detail_start > self.config.DETAIL_SCAN_TIME_BUDGET_SEC:
                print(f"   -> {name}: detail budget exhausted at {url_i}/{len(urls)}")
                break
            with self._detail_lock:
                if self._detail_count >= self.config.MAX_DETAIL_SCAN_TOTAL:
                    break
                self._detail_count += 1
            self._last_activity=time.monotonic()
            try:
                page.goto(url,wait_until="domcontentloaded",timeout=self.config.DETAIL_SCAN_TIMEOUT_MS)
                page.wait_for_timeout(500)
                data=page.evaluate("""() => {
                    const out={desc:'',type:'',loc:'',remote:false};
                    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                        try {
                            const d=JSON.parse(s.textContent);
                            const items=Array.isArray(d)?d:(d['@graph']||[d]);
                            for (const it of items) {
                                const t=it['@type'];
                                if (t==='JobPosting'||(Array.isArray(t)&&t.includes('JobPosting'))) {
                                    out.desc=String(it.description||'').slice(0,12000);
                                    out.type=Array.isArray(it.employmentType)?it.employmentType.join(','):String(it.employmentType||'');
                                    const locs=Array.isArray(it.jobLocation)?it.jobLocation:[it.jobLocation];
                                    out.loc=locs.filter(Boolean).map(l=>{
                                        const a=l.address||{};
                                        let c=a.addressCountry||'';
                                        if (c&&typeof c==='object') c=c.name||'';
                                        return [a.addressLocality,a.addressRegion,c].filter(Boolean).join(', ');
                                    }).filter(Boolean).join(' | ');
                                    out.remote=String(it.jobLocationType||'').toUpperCase().includes('TELECOMMUTE');
                                    return out;
                                }
                            }
                        } catch(e) {}
                    }
                    out.desc=(document.body?document.body.innerText:'').slice(0,12000);
                    return out;
                }""") or {}
            except Exception as exc:
                print(f"      detail failed {url}: {type(exc).__name__}: {exc}")
                continue
            desc=(data.get("desc") or "").strip()
            rec=next((r for r in company_jobs.values() if r.get("Job URL","").casefold()==url.casefold()),None)
            if rec is None or not desc:
                continue
            sup=self.detector.detect(desc)
            visa=sup["visa"]["verdict"]
            reloc=sup["relocation"]["verdict"]
            rec["Visa Sponsorship"]=visa
            rec["Relocation Support"]=reloc
            rec["Relocation Required"]="Yes" if sup["relocation"]["required"] else "Unknown"
            if visa==VERDICT_YES or reloc==VERDICT_YES:
                rec["Relocation/Visa Support"]="Y"
            elif visa==VERDICT_NO and reloc==VERDICT_NO:
                rec["Relocation/Visa Support"]="N"
            else:
                rec["Relocation/Visa Support"]="Unknown"
            rec["Support Confidence"]=round(max(sup["visa"]["confidence"],sup["relocation"]["confidence"]),2)
            rec["Support Evidence"]="; ".join(filter(None,[self.detector.best_evidence(sup["visa"]),self.detector.best_evidence(sup["relocation"])]))
            rec["Support Evidence URL"]=url
            rec["Support Evidence Type"]="explicit_detail_sentence" if rec["Support Evidence"] else "none"

            # Blue Card is independent of general visa sponsorship.
            # Shared, evidence-based classifier (sponsorscout.scanning.jd_support).
            blue = detect_blue_card(self.detector, desc)
            blue_ev = ""
            for sent in self.detector.split_sentences(desc):
                if re.search(r"\b(?:eu\s+)?blue[- ]?card|blaue karte|carta blu|blauwe kaart|carte bleue|tarjeta azul\b", sent, re.I):
                    blue_ev = sent[:300]
                    break
            rec["EU Blue Card"] = blue
            rec["Blue Card Evidence"] = blue_ev

            # Employment/work mode: update only when explicit.
            emp=(data.get("type") or "").casefold(); low=desc.casefold()
            workload=""
            if re.search(r"part[- _]?time|teilzeit|deeltijd",emp+" "+low): workload="Part-time"
            elif re.search(r"intern|trainee|praktikum|stagiaire|apprent",emp+" "+low): workload="Internship"
            elif re.search(r"contract|temporary|fixed[- _]?term",emp): workload="Contract"
            elif re.search(r"full[- _]?time|vollzeit|voltijd",emp+" "+low): workload="Full-time"
            mode=""
            if data.get("remote") or re.search(r"\bfully remote|remote[- ]first|100% remote\b",low): mode="Remote"
            elif re.search(r"\bhybrid|ibrido|hybride|smart working\b",low): mode="Hybrid"
            elif re.search(r"\bon[- ]site|in[- ]office\b",low): mode="On-site"
            old_parts=(rec.get("Job Type") or "Unknown / Unknown").split(" / ",1)
            if workload or mode:
                rec["Job Type"]=f"{workload or old_parts[0]} / {mode or (old_parts[1] if len(old_parts)>1 else 'Unknown')}"

            loc=(data.get("loc") or "").strip()
            if loc and rec.get("Job Location") in {"Unknown","Not Specified"}:
                parsed=self.extract_location(loc)
                if parsed!="Not Specified":
                    rec["Job Location"]=parsed; rec["Location Source"]="detail"
            enriched+=1
        if enriched:
            print(f"   -> {name}: detail-enriched {enriched} rows")

    def _extract_ld_location_from_html(self, html):
        """Parse JobPosting JSON-LD location out of raw HTML (fast, no browser)."""
        for m in re.finditer(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE,
        ):
            try:
                data = json.loads(m.group(1))
            except Exception:
                continue
            items = data if isinstance(data, list) else (
                data.get("@graph") if isinstance(data, dict) else [data])
            if isinstance(items, dict):
                items = [items]
            for it in items or []:
                if not isinstance(it, dict):
                    continue
                t = it.get("@type")
                if t != "JobPosting" and not (
                        isinstance(t, list) and "JobPosting" in t):
                    continue
                loc = it.get("jobLocation")
                if isinstance(loc, list):
                    loc = loc[0] if loc else None
                a = (loc or {}).get("address") or {}
                country = a.get("addressCountry")
                if isinstance(country, dict):
                    country = country.get("name") or ""
                loc_str = ", ".join(filter(None, [
                    a.get("addressLocality"), a.get("addressRegion"), country,
                ])).strip()
                if loc_str:
                    return loc_str
        return ""

    def _detail_location_from_url(self, url, timeout_ms=20000):
        """Extract location from ONE job detail page.
        1st pass: plain HTTP + JSON-LD parse (fast — no browser)
        2nd pass: headless browser for JS-only pages (only if needed)."""
        # ── Fast pass: static HTML JSON-LD ──
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"),
                "Accept": "text/html,application/xhtml+xml,*/*",
            })
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", "replace")
            ld = self._extract_ld_location_from_html(html)
            if ld:
                parsed = self.extract_location(ld)
                if parsed != "Not Specified":
                    return parsed, "detail"
            # fallback: "Location: X" / meta in static HTML
            m = re.search(
                r'(?i)(?:location|standort|luogo|locatie)\s*[:<]\s*'
                r'([A-Za-zÀ-ÿ][^<,\n]{2,60})', html)
            if m:
                parsed = self.extract_location(m.group(1).strip())
                if parsed != "Not Specified":
                    return parsed, "detail"
        except Exception:
            pass

        # ── Slow pass: headless browser (JS-rendered pages only) ──
        try:
            from playwright.sync_api import sync_playwright as _sp
            with _sp() as p:
                b = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage",
                          "--disable-http2", "--ignore-certificate-errors"],
                )
                try:
                    pg = b.new_page()
                    pg.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    pg.wait_for_timeout(2000)
                    ld = pg.evaluate(
                        """() => {
                            for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                                try {
                                    const d = JSON.parse(s.textContent);
                                    const items = Array.isArray(d) ? d : (d['@graph'] || [d]);
                                    for (const it of items) {
                                        const t = it['@type'];
                                        if (t === 'JobPosting' || (Array.isArray(t) && t.includes('JobPosting'))) {
                                            const a = (it.jobLocation && it.jobLocation.address) || {};
                                            const s2 = [a.addressLocality, a.addressRegion, a.addressCountry].filter(Boolean).join(', ');
                                            if (s2) return s2;
                                        }
                                    }
                                } catch(e) {}
                            }
                            return '';
                        }"""
                    ) or ""
                    pg.close()
                    if ld:
                        parsed = self.extract_location(ld)
                        if parsed != "Not Specified":
                            return parsed, "detail"
                finally:
                    try:
                        b.close()
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    def _enrich_ns_locations(self, rows, max_workers=6, max_fetch=None):
        """Enrich rows whose location is 'Not Specified' by visiting the job
        detail page. Returns number of rows enriched (mutates rows in place)."""
        import concurrent.futures as _cf
        targets = [r for r in rows if (r.get("Job Location") or "").strip() == "Not Specified"]
        if not targets:
            return 0
        if max_fetch:
            targets = targets[:max_fetch]
        print(f"   Detail-page location enrichment: {len(targets)} rows to check...")

        def fetch(r):
            res = self._detail_location_from_url(r["Job URL"])
            if res:
                r["Job Location"] = res[0]
                r["Location Source"] = res[1]
                return 1
            return 0

        done = 0
        checked = 0
        with _cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
            for ok in ex.map(fetch, targets):
                done += ok
                checked += 1
                if checked % 100 == 0:
                    print(f"      ...{checked}/{len(targets)} checked, {done} recovered", flush=True)
        print(f"   Detail enrichment done: {done}/{len(targets)} locations recovered")
        return done

    def _fetch_jd_text(self, url, timeout_ms=15000):
        """Fetch a job page (fast HTTP) and extract the description text.
        Returns (desc_text, ld_location) — empty strings when unavailable."""
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"),
                "Accept": "text/html,application/xhtml+xml,*/*",
            })
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", "replace")
        except Exception:
            return "", ""
        desc = ""
        loc = ""
        # JSON-LD JobPosting: description + location
        for m in re.finditer(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE,
        ):
            try:
                data = json.loads(m.group(1))
            except Exception:
                continue
            items = data if isinstance(data, list) else (
                data.get("@graph") if isinstance(data, dict) else [data])
            if isinstance(items, dict):
                items = [items]
            for it in items or []:
                if not isinstance(it, dict):
                    continue
                t = it.get("@type")
                if t != "JobPosting" and not (
                        isinstance(t, list) and "JobPosting" in t):
                    continue
                d = it.get("description") or ""
                if isinstance(d, list):
                    d = " ".join(str(x) for x in d)
                if isinstance(d, dict):
                    d = d.get("text") or ""
                if str(d).strip() and not desc:
                    desc = re.sub(r"<[^>]+>", " ", str(d))
                    desc = re.sub(r"\s+", " ", desc).strip()[:8000]
                jl = it.get("jobLocation")
                if isinstance(jl, list):
                    jl = jl[0] if jl else {}
                a = (jl or {}).get("address") or {}
                loc = ", ".join(filter(None, [
                    a.get("addressLocality"), a.get("addressRegion"),
                    a.get("addressCountry") if not isinstance(a.get("addressCountry"), dict)
                    else (a.get("addressCountry") or {}).get("name", ""),
                ])).strip()
        if not desc:
            # meta description / og:description fallback
            m = re.search(
                r'<meta[^>]*(?:name|property)=["\'](?:og:)?description["\'][^>]*content=["\']([^"\']{50,1500})["\']',
                html, re.I)
            if m:
                desc = re.sub(r"<[^>]+>", " ", m.group(1))
                desc = re.sub(r"\s+", " ", desc).strip()[:8000]
        return desc, loc

    def _enrich_support_from_detail(self, rows, max_fetch=None, use_browser=True):
        """Run the context-aware support detector on each row's job detail page.
        HTTP fast-path first; falls back to ONE shared headless browser for
        JS-only pages (Ashby/Greenhouse/etc.). Updates columns in place.
        Returns number of rows with NEW detector evidence."""
        if not rows:
            return 0
        targets = rows
        if max_fetch:
            targets = targets[:max_fetch]
        cap = self.config.MAX_DETAIL_SCAN_TOTAL
        done = 0
        changed = 0
        browser = None
        try:
            for r in targets:
                if done >= cap:
                    break
                url = r.get("Job URL") or ""
                if not url.startswith("http") or "#job=" in url.lower():
                    continue
                desc, loc = self._fetch_jd_text(url)
                done += 1
                if not desc and use_browser:
                    # JS-only page: fetch body text with one shared browser
                    try:
                        from playwright.sync_api import sync_playwright as _sp
                        if browser is None:
                            _pw_ctx = _sp().start()
                            browser = _pw_ctx.chromium.launch(
                                headless=True,
                                args=["--no-sandbox", "--disable-dev-shm-usage",
                                      "--disable-http2", "--ignore-certificate-errors"],
                            )
                        pg = browser.new_page()
                        try:
                            pg.goto(url, wait_until="domcontentloaded",
                                    timeout=20000)
                            pg.wait_for_timeout(1500)
                            desc = (pg.evaluate(
                                "() => (document.body ? document.body.innerText : '').slice(0, 8000)"
                            ) or "")
                        except Exception:
                            desc = ""
                        finally:
                            try:
                                pg.close()
                            except Exception:
                                pass
                    except Exception:
                        desc = ""
                if not desc:
                    continue
                sup = self.detector.detect(desc)
                if not sup["visa"]["evidence"] and not sup["relocation"]["evidence"]:
                    continue
                r["Visa Sponsorship"] = sup["visa"]["verdict"]
                r["Relocation Support"] = sup["relocation"]["verdict"]
                r["Relocation Required"] = "Yes" if sup["relocation"]["required"] else "No"
                r["Support Confidence"] = round(max(
                    sup["visa"]["confidence"], sup["relocation"]["confidence"]), 2)
                r["Support Evidence"] = "; ".join(filter(None, [
                    self.detector.best_evidence(sup["visa"]),
                    self.detector.best_evidence(sup["relocation"]),
                ]))
                cl = desc.lower()
                if sup["visa"]["verdict"] == VERDICT_YES:
                    r["Relocation/Visa Support"] = "Y"
                if sup["relocation"]["verdict"] == VERDICT_YES:
                    r["Relocation/Visa Support"] = "Y"
                elif sup["relocation"]["verdict"] == VERDICT_NO:
                    r["Relocation/Visa Support"] = "N"
                # EU Blue Card uses the shared evidence-based classifier, NOT a
                # blanket "visa verdict Yes => Blue Card Y" shortcut.
                r["EU Blue Card"] = detect_blue_card(self.detector, desc)
                changed += 1
                if changed % 50 == 0:
                    print(f"      ...support detection {changed} rows enriched (of {len(targets)})",
                          flush=True)
        finally:
            try:
                if browser is not None:
                    try:
                        bp = getattr(browser, "process", None)
                        if bp is not None:
                            bp.kill()
                    except Exception:
                        pass
                    try:
                        browser.close()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                _pw_ctx.stop()
            except Exception:
                pass
        print(f"   Support detection: {changed} rows enriched from detail pages")
        return changed

    def reprocess_csv(self, input_csv=None, output_csv=None, detail=False):
        raise RuntimeError(
            "The unsafe v6-style reprocessor is disabled in v7. "
            "Use repair_scraped_jobs_v7.py, which preserves all rows across direct/recruiter/quarantine outputs."
        )
        """Deprecated unreachable v6 implementation retained below for migration reference only.
        Applies title cleaning, location re-parsing, HQ policy, and dedupe.
        Usage:  python job_scanner.py --reprocess --input scraped_jobs.csv
                python job_scanner.py --reprocess --input x.csv --detail   # + visit NS job pages
        """
        input_csv = input_csv or self.input_csv
        if not os.path.exists(input_csv):
            raise FileNotFoundError(f"Input CSV '{input_csv}' not found.")
        if not output_csv:
            output_csv = input_csv.replace(".csv", "_cleaned.csv")

        columns = [
            "Company Name", "Industry Type", "Job Title", "Job Location",
            "Job Type", "Job URL", "EU Blue Card", "Relocation/Visa Support",
            "Location Source", "URL Type",
            "Visa Sponsorship", "Relocation Support", "Relocation Required",
            "Support Confidence", "Support Evidence",
        ]
        with open(input_csv, newline="", encoding="utf-8-sig") as f:
            first_line = f.readline()
            f.seek(0)
            # FIXED: auto-detect headerless CSVs (first data row used as header)
            has_header = "Company Name" in first_line and "Job Title" in first_line
            if has_header:
                rows = list(csv.DictReader(f))
            else:
                reader = csv.reader(f)
                data = list(reader)
                if not data:
                    rows = []
                else:
                    rows = [
                        dict(zip(columns, row + [""] * (len(columns) - len(row))))
                        for row in data
                    ]
        hdr_flag = "yes" if has_header else "NO (auto-detected)"
        print(f"Reprocessing {len(rows)} rows from '{input_csv}' (header={hdr_flag})")

        brand_words = ("lenscrafters", "sunglass hut", "target optical",
                       "oakley", "opsm", "for eyes", "ray-ban")
        stats = {
            "title_changed": 0, "title_rejected": 0, "location_changed": 0,
            "global_fixed": 0, "uk_fixed": 0, "jobdetail_fixed": 0,
            "brand_fixed": 0, "dropped_dup": 0, "kept": 0,
        }
        out_rows = []
        seen_tl = set()

        for r in rows:
            name = (r.get("Company Name") or "").strip()
            industry = (r.get("Industry Type") or "Unknown").strip()
            old_title = (r.get("Job Title") or "").strip()
            old_loc = (r.get("Job Location") or "").strip()
            url = (r.get("Job URL") or "").strip()
            job_type = (r.get("Job Type") or "").strip()
            blue = (r.get("EU Blue Card") or "").strip()
            visa = (r.get("Relocation/Visa Support") or "").strip()

            new_title = self.clean_job_title(old_title)
            if not new_title or not self.is_valid_job_title(new_title):
                stats["title_rejected"] += 1
                continue
            if new_title != old_title:
                stats["title_changed"] += 1

            # re-derive location from the OLD location text (best available context)
            location, _, _, _, source = self.parse_job_metadata(
                name, new_title, old_loc, url)
            if location != old_loc:
                stats["location_changed"] += 1
            old_low = old_loc.lower()
            if old_low == "global":
                stats["global_fixed"] += 1
            if old_low == "uk":
                stats["uk_fixed"] += 1
            if "jobdetail" in old_low:
                stats["jobdetail_fixed"] += 1
            if any(b in old_low for b in brand_words):
                stats["brand_fixed"] += 1

            # dedupe on (company, title, location), preferring real URLs
            key = (name.lower(), new_title.lower(), location.lower())
            is_synth = "#job=" in url.lower()
            if key in seen_tl:
                stats["dropped_dup"] += 1
                if not is_synth:
                    for i, prev in enumerate(out_rows):
                        if (prev["Company Name"].lower(),
                                prev["Job Title"].lower(),
                                prev["Job Location"].lower()) == key:
                            if "#job=" in prev["Job URL"].lower():
                                out_rows[i] = dict(prev)
                                out_rows[i]["Job URL"] = url
                            break
                continue
            seen_tl.add(key)

            out_rows.append({
                "Company Name": name,
                "Industry Type": industry,
                "Job Title": new_title,
                "Job Location": location,
                "Job Type": job_type,  # keep original crawl value (best available)
                "Job URL": url,
                "EU Blue Card": blue,
                "Relocation/Visa Support": visa,
                "Location Source": source,
                "URL Type": "synthetic" if is_synth else "real",
                # carry over support columns if present in input, else defaults
                "Visa Sponsorship": (r.get("Visa Sponsorship") or "Unknown").strip(),
                "Relocation Support": (r.get("Relocation Support") or "Unknown").strip(),
                "Relocation Required": (r.get("Relocation Required") or "No").strip(),
                "Support Confidence": (r.get("Support Confidence") or "").strip(),
                "Support Evidence": (r.get("Support Evidence") or "").strip(),
            })
            stats["kept"] += 1

        # FIXED: optional detail-page enrichment — visit 'Not Specified' rows'
        # job pages and recover locations from JSON-LD / page body
        if detail and out_rows:
            self._enrich_ns_locations(out_rows)
            # FIXED: also run the context-aware support detector on fetched pages
            self._enrich_support_from_detail(out_rows)

        with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=columns)
            w.writeheader()
            w.writerows(out_rows)

        report = (
            "\n=== REPROCESS REPORT ===\n"
            f"Input rows        : {len(rows)}\n"
            f"Kept (cleaned)    : {stats['kept']}\n"
            f"Titles changed    : {stats['title_changed']}\n"
            f"Titles rejected   : {stats['title_rejected']}\n"
            f"Locations changed : {stats['location_changed']}\n"
            f"  'Global' fixed  : {stats['global_fixed']}\n"
            f"  'Uk' fixed      : {stats['uk_fixed']}\n"
            f"  'JobDetail' fix : {stats['jobdetail_fixed']}\n"
            f"  store-brand fix : {stats['brand_fixed']}\n"
            f"Dup rows removed  : {stats['dropped_dup']}\n"
            f"Output            : {output_csv}\n"
        )
        print(report)
        with open(output_csv.replace(".csv", "_clean_report.txt"),
                  "w", encoding="utf-8") as f:
            f.write(report)

    def _try_ats_fallback(self, p, name, process_job):
        """Zero-yield rescue: pull jobs from public ATS JSON/XML APIs
        (Greenhouse / Lever / Ashby / Personio / Recruitee / Workable).
        Returns number of jobs added."""
        import xml.etree.ElementTree as ET
        entries = self.config.ATS_FALLBACK.get(name)
        if not entries:
            return 0
        api_builders = {
            "ashby": lambda slug: ("https://api.ashbyhq.com/posting-api/job-board/"
                                   f"{slug}?includeCompensation=false", "json"),
            "lever": lambda slug: (f"https://api.lever.co/v0/postings/{slug}?mode=json", "json"),
            "greenhouse": lambda slug: (f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", "json"),
            "personio": lambda slug: (f"https://{slug}.jobs.personio.de/xml?language=en", "xml"),
            "recruitee": lambda slug: (f"https://{slug}.recruitee.com/api/offers/", "json"),
            "workable": lambda slug: (f"https://www.workable.com/api/accounts/{slug}?details=true", "json"),
        }
        added = 0
        for ats, slugs in entries.items():
            if ats not in api_builders:
                continue
            for slug in slugs:
                url, fmt = api_builders[ats](slug)
                try:
                    req = urllib.request.Request(url, headers={
                        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                       "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"),
                        "Accept": "application/json,text/xml,*/*",
                    })
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        if resp.status != 200:
                            continue
                        raw = resp.read().decode("utf-8", "replace")
                    jobs = []
                    if fmt == "json":
                        import json as _json
                        data = _json.loads(raw)
                        if ats == "greenhouse":
                            for it in data.get("jobs") or []:
                                jobs.append({
                                    "job_title": it.get("title") or "",
                                    "job_url": it.get("absolute_url") or "",
                                    "location_hint": (it.get("location") or {}).get("name") or "",
                                    "card_context": " | ".join(filter(None, [
                                        it.get("department") or "",
                                        it.get("employment_type") or "",
                                    ])),
                                })
                        elif ats == "lever":
                            for it in data:
                                cats = it.get("categories") or {}
                                loc = cats.get("location") or cats.get("allLocations") or ""
                                if isinstance(loc, list):
                                    loc = ", ".join(loc)
                                jobs.append({
                                    "job_title": it.get("text") or "",
                                    "job_url": it.get("hostedUrl") or "",
                                    "location_hint": str(loc),
                                    "card_context": " | ".join(filter(None, [
                                        cats.get("team") or "",
                                        cats.get("commitment") or "",
                                        it.get("workplaceType") or "",
                                    ])),
                                })
                        elif ats == "ashby":
                            for it in (data.get("jobs") or []):
                                jobs.append({
                                    "job_title": it.get("title") or "",
                                    "job_url": it.get("jobUrl") or it.get("applyUrl") or "",
                                    "location_hint": it.get("location") or "",
                                    "card_context": " | ".join(filter(None, [
                                        it.get("department") or "",
                                        it.get("employmentType") or "",
                                    ])),
                                })
                        elif ats == "recruitee":
                            for it in (data.get("offers") or []):
                                jobs.append({
                                    "job_title": it.get("title") or "",
                                    "job_url": it.get("careers_url") or "",
                                    "location_hint": it.get("location") or "",
                                    "card_context": it.get("department") or "",
                                })
                        elif ats == "workable":
                            for it in (data.get("jobs") or []):
                                loc = " ".join(filter(None, [
                                    it.get("city") or "", it.get("country") or ""])).strip()
                                jobs.append({
                                    "job_title": it.get("title") or "",
                                    "job_url": it.get("url") or "",
                                    "location_hint": loc,
                                    "card_context": " | ".join(filter(None, [
                                        it.get("department") or "",
                                        it.get("employment_type") or "",
                                        it.get("worktype") or "",
                                    ])),
                                })
                    else:  # personio xml
                        try:
                            root = ET.fromstring(raw)
                        except Exception:
                            continue
                        for pos in root.findall(".//position"):
                            jobs.append({
                                "job_title": (pos.findtext("name") or "").strip(),
                                "job_url": (pos.findtext("jobUrl") or "").strip(),
                                "location_hint": (pos.findtext("office") or "").strip(),
                                "card_context": " | ".join(filter(None, [
                                    (pos.findtext("department") or "").strip(),
                                    (pos.findtext("employmentType") or "").strip(),
                                    (pos.findtext("schedule") or "").strip(),
                                ])),
                            })
                    for j in jobs:
                        if process_job(j):
                            added += 1
                    if added:
                        print(f"   -> {name}: ATS API fallback ({ats}/{slug}) added {added} jobs")
                        return added
                except Exception:
                    continue
        return added

    def _ensure_output_header(self, columns, path=None):
        path = path or self.output_csv
        if not columns:
            return
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                csv.DictWriter(f, fieldnames=columns).writeheader()
            return
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            first = next(reader, [])
        if first != columns:
            raise ValueError(
                f"Output schema mismatch for {path}. Expected {columns!r}, found {first!r}. "
                "Use a fresh output path or explicitly migrate the file."
            )

    def _kill_child_processes(self):
        """Kill lingering Playwright node-driver / chrome child processes
        (descendants of THIS process only) so they cannot dump EPIPE /
        unhandled-error output to the terminal after the script exits."""
        import signal, subprocess
        try:
            def _kill_children(ppid):
                try:
                    out = subprocess.run(["pgrep", "-P", str(ppid)],
                                         capture_output=True, text=True, timeout=5)
                    kids = [int(x) for x in out.stdout.split() if x.strip()]
                except Exception:
                    return []
                for k in kids:
                    try:
                        os.kill(k, signal.SIGKILL)
                    except Exception:
                        pass
                return kids
            level = [os.getpid()]
            for _ in range(4):  # python -> node driver -> chrome -> zygotes
                nxt = []
                for pid in level:
                    nxt += _kill_children(pid)
                if not nxt:
                    break
                level = nxt
        except Exception:
            pass

    def execute_crawler(self):
        """v7 crawl: provider-first, fresh/transactional outputs, separated recruiters."""
        import threading
        import concurrent.futures as cf

        targets = self.read_seed_file()
        if self.only_companies:
            wanted = {c.strip().lower() for c in self.only_companies if c and c.strip()}
            targets = [t for t in targets if t.get("name", "").strip().lower() in wanted]
            if not targets:
                print(f"no career targets matched only_companies={self.only_companies}")
                return
        crawl_start = time.monotonic()
        self._last_activity = time.monotonic()
        self._detail_lock = threading.Lock()
        self._detail_count = 0

        # Gate the run: if DNS/network is down, abort BEFORE truncating any output
        # files, so a failed pre-flight never wipes a previous good dataset.
        self._preflight_connectivity()

        columns = [
            "Company Name", "Seed Name", "Source Type", "Hiring Company", "Target Country", "Scope Policy",
            "Industry Type", "Sponsorship History Score", "English Friendly Score", "Remote Score",
            "Job Title", "Raw Job Title", "Job Location", "Raw Location", "Job Type",
            "Job URL", "Canonical Job ID", "Provider", "Extraction Method",
            "EU Blue Card", "Blue Card Evidence", "Relocation/Visa Support",
            "Location Source", "URL Type", "Visa Sponsorship", "Relocation Support",
            "Relocation Required", "Support Confidence", "Support Evidence",
            "Support Evidence URL", "Support Evidence Type", "Record Status",
            "Quarantine Reason", "Run ID", "Scanned At",
        ]
        base = self.output_csv[:-4] if self.output_csv.lower().endswith(".csv") else self.output_csv
        recruiter_csv = base + "_recruiter.csv"
        quarantine_csv = base + "_quarantine.csv"
        scan_log_csv = base + "_scan_log.csv"
        log_columns = [
            "Run ID", "Seed Name", "Company", "Source Type", "Target Country", "Status",
            "Provider", "Jobs Found", "Quarantined", "Duplicates", "Rejected Scope",
            "Error", "Diagnostics", "Duration Sec", "Seed URL",
        ]

        output_paths = [self.output_csv, recruiter_csv, quarantine_csv]
        if not self.resume:
            for path in output_paths:
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    csv.DictWriter(f, fieldnames=columns).writeheader()
            with open(scan_log_csv, "w", newline="", encoding="utf-8-sig") as f:
                csv.DictWriter(f, fieldnames=log_columns).writeheader()
        else:
            for path in output_paths:
                self._ensure_output_header(columns, path)
            if not os.path.exists(scan_log_csv) or os.path.getsize(scan_log_csv) == 0:
                with open(scan_log_csv, "w", newline="", encoding="utf-8-sig") as f:
                    csv.DictWriter(f, fieldnames=log_columns).writeheader()
            else:
                self._ensure_output_header(log_columns, scan_log_csv)

        file_lock = threading.Lock()
        seen_lock = threading.Lock()
        seen_global = set()
        if self.resume:
            for path in (self.output_csv, recruiter_csv):
                with open(path, newline="", encoding="utf-8-sig") as f:
                    for row in csv.DictReader(f):
                        cid = (row.get("Canonical Job ID") or "").strip()
                        if cid:
                            seen_global.add(cid)

        print(f"v7 scan started: {len(targets)} enabled targets; run_id={self.run_id}; "
              f"resume={self.resume}; detail={self.detail_scan}")

        def crawl_target(idx, target_row):
            if self.cancel_event is not None and self.cancel_event.is_set():
                print(f"   CANCELLED: skipping target [{idx}] {target_row.get('name', '?')}")
                return 0, 0, "cancelled"
            name = target_row["name"]
            seed_name = target_row["seed_name"]
            seed_url = target_row["careers_url"]
            provider = target_row.get("provider", "auto")
            source_type = target_row.get("source_type", "direct_employer")
            started = time.monotonic()
            company_jobs = {}
            quarantine = []
            diagnostics = []
            stats = {
                "duplicates": 0, "rejected_scope": 0, "quarantined": 0,
                "rejected_url": 0, "rejected_title": 0, "synthetic": 0,
            }
            browser = ctx = page = None
            error = ""
            print(f"\n[{idx}/{len(targets)}] {seed_name} -> {name} [{source_type}, {target_row.get('target_country')}]")

            def base_record(raw_title, clean_title, raw_location, clean_url, reason=""):
                now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                return {
                    "Company Name": name,
                    "Seed Name": seed_name,
                    "Source Type": source_type,
                    "Hiring Company": name if source_type == "direct_employer" else "Unknown",
                    "Target Country": target_row.get("target_country", "Global"),
                    "Scope Policy": target_row.get("scope_policy", "global"),
                    "Industry Type": target_row.get("industry", "Unknown"),
                    "Sponsorship History Score": target_row.get("sponsorship_history") if target_row.get("sponsorship_history") is not None else "",
                    "English Friendly Score": target_row.get("english_friendly") if target_row.get("english_friendly") is not None else "",
                    "Remote Score": target_row.get("remote_score") if target_row.get("remote_score") is not None else "",
                    "Job Title": clean_title or raw_title or "Unknown",
                    "Raw Job Title": raw_title or "",
                    "Job Location": "Unknown",
                    "Raw Location": raw_location or "",
                    "Job Type": "Unknown / Unknown",
                    "Job URL": clean_url or "",
                    "Canonical Job ID": "",
                    "Provider": provider,
                    "Extraction Method": "unknown",
                    "EU Blue Card": "Unknown",
                    "Blue Card Evidence": "",
                    "Relocation/Visa Support": "Unknown",
                    "Location Source": "none",
                    "URL Type": "synthetic" if "#job=" in (clean_url or "").lower() else "real",
                    "Visa Sponsorship": "Unknown",
                    "Relocation Support": "Unknown",
                    "Relocation Required": "Unknown",
                    "Support Confidence": 0.0,
                    "Support Evidence": "",
                    "Support Evidence URL": "",
                    "Support Evidence Type": "none",
                    "Record Status": "quarantine" if reason else "accepted",
                    "Quarantine Reason": reason,
                    "Run ID": self.run_id,
                    "Scanned At": now,
                }

            def quarantine_job(raw_title, raw_url, raw_location, reason, method="unknown"):
                clean_url = self.clean_and_normalize_url(raw_url)
                clean_title = self.clean_job_title(raw_title)
                rec = base_record(raw_title, clean_title, raw_location, clean_url, reason)
                rec["Extraction Method"] = method
                quarantine.append(rec)
                stats["quarantined"] += 1

            def process_job(job):
                raw_url = str(job.get("job_url") or "").strip()
                raw_title = str(job.get("job_title") or "").strip()
                raw_location = str(job.get("location_hint") or "").strip()
                context = str(job.get("card_context") or "").strip()
                method = str(job.get("extraction_method") or "dom_heuristic")
                clean_url = self.clean_and_normalize_url(raw_url)
                if "#job=" in clean_url.lower() and not self.allow_synthetic:
                    stats["synthetic"] += 1
                    quarantine_job(raw_title, raw_url, raw_location, "synthetic_non_actionable_url", method)
                    return False
                if not self.is_valid_job_url(clean_url):
                    stats["rejected_url"] += 1
                    quarantine_job(raw_title, raw_url, raw_location, "invalid_or_application_only_url", method)
                    return False
                if self.is_self_listing_url(clean_url, seed_url):
                    stats["rejected_url"] += 1
                    quarantine_job(raw_title, raw_url, raw_location, "self_listing_url", method)
                    return False
                clean_title = self.clean_job_title(raw_title)
                if not self.is_valid_job_title(clean_title):
                    stats["rejected_title"] += 1
                    quarantine_job(raw_title, raw_url, raw_location, "invalid_generic_or_department_title", method)
                    return False
                combined_context = f"{raw_location}\n{context}".strip()
                location, job_type, _, _, loc_source = self.parse_job_metadata(
                    name, clean_title, combined_context, clean_url
                )
                out_location = "Unknown" if location == "Not Specified" else location
                # Regional seed context resolves known local administrative-code collisions.
                if target_row.get("target_country") == "Italy" and out_location in {"Milan, MI", "Milan, Spain"}:
                    out_location, loc_source = "Milan, Italy", "seed_scope+card"
                if not self._scope_allows(target_row, out_location, combined_context, clean_url):
                    stats["rejected_scope"] += 1
                    rec = base_record(raw_title, clean_title, raw_location, clean_url, "outside_or_unproven_target_country")
                    rec.update({"Job Location": out_location, "Job Type": job_type,
                                "Location Source": loc_source, "Extraction Method": method})
                    quarantine.append(rec); stats["quarantined"] += 1
                    return False
                cid = self.canonical_job_id(
                    f"{name}|{target_row.get('target_country','Global')}", clean_url,
                    clean_title, out_location, provider,
                )
                rec = base_record(raw_title, clean_title, raw_location, clean_url)
                rec.update({
                    "Job Location": out_location,
                    "Job Type": job_type,
                    "Location Source": loc_source,
                    "Canonical Job ID": cid,
                    "Extraction Method": method,
                })
                prev = company_jobs.get(cid)
                if prev is not None:
                    stats["duplicates"] += 1
                    if self._record_quality(rec) > self._record_quality(prev):
                        company_jobs[cid] = rec
                    return False
                company_jobs[cid] = rec
                return True

            try:
                # Provider adapters are authoritative and avoid fragile DOM pagination.
                api_jobs, api_diag = self._fetch_provider_jobs(target_row)
                diagnostics.append(api_diag)
                for job in api_jobs:
                    process_job(job)
                provider_success = bool(api_jobs)

                # Browser fallback only when no provider data was available.
                if not provider_success:
                    if sync_playwright is None:
                        raise RuntimeError("Playwright is required for DOM fallback. Install requirements and run: playwright install chromium")
                    with sync_playwright() as pw:
                        browser = pw.chromium.launch(
                            headless=True,
                            args=["--no-sandbox", "--disable-dev-shm-usage",
                                  "--disable-http2", "--ignore-certificate-errors"],
                        )
                        ctx = browser.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
                            viewport={"width": 1440, "height": 900}, locale="en-US",
                            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                        )
                        page = ctx.new_page()
                        loaded = False
                        for attempt in range(1, self.config.GOTO_RETRIES + 1):
                            try:
                                page.goto(seed_url, wait_until="domcontentloaded", timeout=self.config.ACTION_TIMEOUT_MS)
                                loaded = True; break
                            except PlaywrightTimeoutError:
                                # Navigation timed out but a partial DOM may be usable.
                                diagnostics.append(f"seed timeout attempt {attempt}; partial DOM used")
                                loaded = True; break
                            except Exception as exc:
                                net = self._is_network_error(exc)
                                diagnostics.append(
                                    f"seed attempt {attempt}: {type(exc).__name__}: {exc}"
                                    f"{' [network]' if net else ''}"
                                )
                                if net and attempt < self.config.GOTO_RETRIES:
                                    backoff = self.config.GOTO_BACKOFF_BASE_SEC * (2 ** (attempt - 1))
                                    diagnostics.append(f"retrying in {backoff:.1f}s")
                                    page.wait_for_timeout(int(backoff * 1000))
                                elif attempt < self.config.GOTO_RETRIES:
                                    page.wait_for_timeout(1500)
                        if not loaded:
                            raise RuntimeError(f"seed page did not load: {seed_url}")
                        page.wait_for_timeout(min(3000, self.config.STABILIZATION_DELAY_SEC * 1000))
                        self.dismiss_initial_blockers(page)
                        self.navigate_to_fragment(page, seed_url)
                        self.wait_for_job_cards_to_load(page)
                        target = self.check_iframes(page) or page
                        size = self.try_increase_page_size(page, target)
                        if size: diagnostics.append(f"page size increased to {size}")
                        current = self.extract_visible_jobs(target)
                        if not current:
                            changed = self.handle_landing_page_redirect(page, seed_url) or self.trigger_search_if_present(page)
                            if changed:
                                page.wait_for_timeout(1500)
                                target = self.check_iframes(page) or page
                                current = self.extract_visible_jobs(target)
                        for job in current: process_job(job)
                        self.aggressive_infinite_scroll(page, target)
                        self.click_load_more_repeatedly(page, target)

                        prev_total = -1; empty_pages = 0; low_yield = 0
                        seed_params = parse_qsl(urlparse(seed_url).query)
                        for page_num in range(1, self.config.MAX_PAGINATION_PAGES + 1):
                            if time.monotonic() - started > self.config.MAX_COMPANY_TIME_SEC:
                                diagnostics.append(f"company budget reached at page {page_num}")
                                break
                            target = self.check_iframes(page) or page
                            self.progressive_scroll_and_wait(page, target)
                            batch = self.extract_visible_jobs(target)
                            added = sum(1 for job in batch if process_job(job))
                            self._last_activity = time.monotonic()
                            total = len(company_jobs)
                            if total == prev_total: empty_pages += 1
                            else: empty_pages = 0
                            prev_total = total
                            if empty_pages >= 3: break
                            if added <= 2: low_yield += 1
                            else: low_yield = 0
                            if low_yield >= self.config.LOW_YIELD_PAGES: break
                            if not self.execute_advanced_pagination(page, target, page_num, seed_params): break

                        company_jobs = self._dedupe_records(company_jobs)
                        if self.detail_scan and company_jobs:
                            self._detail_scan_for_company(page, name, company_jobs)
                        try: ctx.close()
                        except Exception: pass
                        try: browser.close()
                        except Exception: pass
                        browser = ctx = page = None
                elif self.detail_scan and company_jobs:
                    # API-first crawl still gets explicit detail evidence when requested.
                    if sync_playwright is None:
                        raise RuntimeError("Playwright is required for --detail. Install requirements and Chromium")
                    with sync_playwright() as pw:
                        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                        ctx = browser.new_context()
                        page = ctx.new_page()
                        self._detail_scan_for_company(page, name, company_jobs)
                        try: ctx.close()
                        except Exception: pass
                        try: browser.close()
                        except Exception: pass
                        browser = ctx = page = None
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                diagnostics.append(error)
            finally:
                try:
                    if page is not None: page.close()
                except Exception: pass
                try:
                    if ctx is not None: ctx.close()
                except Exception: pass
                try:
                    if browser is not None: browser.close()
                except Exception: pass

            # Scope can improve after detail scan; normalize internal sentinel.
            for rec in company_jobs.values():
                if rec.get("Job Location") == "Not Specified": rec["Job Location"] = "Unknown"

            written = 0
            duplicates_global = 0
            accepted_rows = []
            with seen_lock:
                for cid, rec in company_jobs.items():
                    if cid in seen_global:
                        duplicates_global += 1
                        continue
                    seen_global.add(cid)
                    accepted_rows.append(rec)
            stats["duplicates"] += duplicates_global
            destination = recruiter_csv if source_type == "recruiter" else self.output_csv
            with file_lock:
                if accepted_rows:
                    with open(destination, "a", newline="", encoding="utf-8-sig") as f:
                        w = csv.DictWriter(f, fieldnames=columns)
                        for rec in accepted_rows:
                            w.writerow({k: rec.get(k, "") for k in columns}); written += 1
                if quarantine:
                    with open(quarantine_csv, "a", newline="", encoding="utf-8-sig") as f:
                        w = csv.DictWriter(f, fieldnames=columns)
                        for rec in quarantine:
                            w.writerow({k: rec.get(k, "") for k in columns})
                status = "error" if error and not written else ("partial" if error else ("ok" if written else "empty"))
                with open(scan_log_csv, "a", newline="", encoding="utf-8-sig") as f:
                    csv.DictWriter(f, fieldnames=log_columns).writerow({
                        "Run ID": self.run_id, "Seed Name": seed_name, "Company": name,
                        "Source Type": source_type, "Target Country": target_row.get("target_country"),
                        "Status": status, "Provider": provider, "Jobs Found": written,
                        "Quarantined": len(quarantine), "Duplicates": stats["duplicates"],
                        "Rejected Scope": stats["rejected_scope"], "Error": error,
                        "Diagnostics": " | ".join(diagnostics)[-4000:],
                        "Duration Sec": round(time.monotonic()-started,1), "Seed URL": seed_url,
                    })
            print(f"   {status.upper()} {name}: wrote={written}, quarantined={len(quarantine)}, "
                  f"dups={stats['duplicates']}, scope_reject={stats['rejected_scope']}")
            return written, len(quarantine), status

        totals = collections.Counter()
        with cf.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for i, row in enumerate(targets, 1):
                if self.cancel_event is not None and self.cancel_event.is_set():
                    print(f"   CANCELLED: not submitting remaining {len(targets) - i + 1} targets")
                    break
                futures.append(executor.submit(crawl_target, i, row))
            for future in cf.as_completed(futures):
                try:
                    wrote, quarantined, status = future.result()
                    totals["written"] += wrote; totals["quarantined"] += quarantined; totals[status] += 1
                except Exception as exc:
                    totals["thread_errors"] += 1
                    print(f"Worker escaped error: {type(exc).__name__}: {exc}")

        elapsed = int(time.monotonic()-crawl_start)
        print(f"\nv7 scan complete in {elapsed}s: direct/recruiter rows={totals['written']}, "
              f"quarantined={totals['quarantined']}, thread_errors={totals['thread_errors']}")
        print(f"  Direct: {self.output_csv}\n  Recruiters: {recruiter_csv}\n  Quarantine: {quarantine_csv}\n  Log: {scan_log_csv}")

def extract_location_from_url(url):
    scanner = CareerPortalScanner()
    return scanner.extract_location_from_url(url)
