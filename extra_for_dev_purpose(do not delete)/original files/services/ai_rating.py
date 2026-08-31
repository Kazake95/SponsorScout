"""AI Job Rating, CV Tailoring & Cover Letter helpers.

This module no longer calls any AI API directly. Instead, SponsorScout
builds a prompt (rating / CV tailoring / cover letter), the user pastes it
into a web-based AI chat (opened via services.ai_webview), and pastes the
reply back. This module:

- Persists prompts, CV, base cover letter (unchanged from before).
- Builds the full prompt text for each task (job context + CV + template).
- Parses the text the user pastes back (JSON for ratings, plain text for
  CV/cover letter).

BUGFIX (AI-webview migration): removed _call_ai / _call_ai_once and all
provider/model/API-key/base-URL persistence (~400 lines). The parsing
helpers (_clean_ai_text, _extract_json_payload, _parse_ai_json) and the
rating-normalisation logic from the old rate_job() are kept verbatim --
they're still needed to interpret whatever text the user pastes back, and
were already hardened against messy AI output (markdown fences, single
quotes, embedded JSON, etc.).
"""
from __future__ import annotations

import ast
import json
import re
from typing import Optional

from sponsorscout.paths import USER_DATA_DIR, ensure_user_data_dir

# -- User data directory (same folder as the DB) -----------------------------
_USER_DIR = USER_DATA_DIR
ensure_user_data_dir()

PROMPT_PATH     = _USER_DIR / "ai_prompt.txt"
CV_PROMPT_PATH  = _USER_DIR / "cv_prompt.txt"
CL_PROMPT_PATH  = _USER_DIR / "cl_prompt.txt"
CL_LETTER_PATH  = _USER_DIR / "my_cover_letter.txt"
CV_PATH         = _USER_DIR / "my_cv.txt"

# -- Default prompts ----------------------------------------------------------
DEFAULT_AI_PROMPT = """You are a job eligibility assistant. Evaluate the job listing and rate it.

Rate the job from 1-10 based on:
- Relevance to the candidate's skills and experience
- Visa/sponsorship availability for EU candidates
- Remote work options and relocation support
- Salary and growth potential
- Company reputation and stability

Also provide a short eligibility verdict (2-3 sentences) explaining if the candidate
should apply, any key concerns, and what makes this role a good/poor fit.

Respond ONLY with valid JSON in this exact format:
{
  "rating": <number 1-10>,
  "verdict": "<2-3 sentence eligibility assessment>",
  "pros": ["<pro 1>", "<pro 2>"],
  "cons": ["<con 1>", "<con 2>"]
}"""

DEFAULT_CV_PROMPT = """You are an expert CV writer and career coach specialising in EU job applications and visa sponsorship roles.

Given the candidate's existing CV and a full job description, rewrite and tailor the CV to:
1. Mirror the exact language and keywords from the JD (for ATS systems).
2. Emphasise relevant skills, tools, and achievements that match the role requirements.
3. Quantify achievements wherever possible.
4. Add a targeted professional summary at the top (3-4 sentences) addressing this specific role.
5. Ensure sponsorship / relocation readiness is subtly conveyed where appropriate.
6. Keep the tone professional and concise.

Return ONLY the tailored CV text -- no commentary, no markdown headers, no preamble."""

DEFAULT_CL_PROMPT = """You are an expert cover letter writer specialising in EU tech and data roles.

Given the candidate's CV and a full job description, write a compelling, personalised cover letter that:
1. Opens with a strong hook referencing the specific company and role.
2. Highlights 2-3 key achievements from the CV that directly address the JD's requirements.
3. Shows genuine enthusiasm for the company's mission/products (infer from JD context).
4. Briefly addresses visa/sponsorship situation positively and confidently.
5. Closes with a clear call to action.

Format: 3-4 paragraphs, ~300-400 words. Professional but warm tone.
Return ONLY the cover letter text -- no subject lines, no placeholders like [Company Name]."""


# -- Persistence helpers -------------------------------------------------------

def load_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    return DEFAULT_AI_PROMPT

def save_prompt(text: str) -> None:
    PROMPT_PATH.write_text(text.strip(), encoding="utf-8")


def load_base_cover_letter() -> str:
    """Return the user's saved base cover / motivation letter template."""
    if CL_LETTER_PATH.exists():
        return CL_LETTER_PATH.read_text(encoding="utf-8").strip()
    return ""


def save_base_cover_letter(text: str) -> None:
    """Persist the user's base cover letter template for AI tailoring."""
    CL_LETTER_PATH.write_text(text.strip(), encoding="utf-8")

def load_cv_prompt() -> str:
    if CV_PROMPT_PATH.exists():
        return CV_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return DEFAULT_CV_PROMPT

def save_cv_prompt(text: str) -> None:
    CV_PROMPT_PATH.write_text(text.strip(), encoding="utf-8")

def load_cl_prompt() -> str:
    if CL_PROMPT_PATH.exists():
        return CL_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return DEFAULT_CL_PROMPT

def save_cl_prompt(text: str) -> None:
    CL_PROMPT_PATH.write_text(text.strip(), encoding="utf-8")

def load_cv() -> str:
    if CV_PATH.exists():
        return CV_PATH.read_text(encoding="utf-8").strip()
    return ""

def save_cv(text: str) -> None:
    CV_PATH.write_text(text.strip(), encoding="utf-8")


# -- Prompt builders ------------------------------------------------------------
# These build the FULL prompt text the user copies and pastes into the
# embedded AI chat. Mirrors the context the old _call_ai-based functions
# used to send over the network.

def build_rating_prompt(
    title: str,
    company: str,
    country: str,
    description: str,
    sponsorship_score: int,
    remote_type: str,
    eu_blue_card: bool,
    has_relocation: bool,
    custom_prompt: Optional[str] = None,
    objective: Optional[str] = None,
) -> str:
    """Build the full prompt for job eligibility rating."""
    system_prompt = custom_prompt or load_prompt()
    objective_line = f"Search objective: {objective}\n" if objective else ""

    cv_text = load_cv()
    cv_section = (
        f"\n=== CANDIDATE CV (use this to personalise the eligibility assessment) ===\n"
        f"{cv_text}\n"
        if cv_text else
        "\n(No CV on file -- rating based on job details only. Paste your CV in the AI Assistant tab for personalised results.)\n"
    )

    job_context = (
        f"Job Title: {title}\n"
        f"Company: {company}\n"
        f"Country: {country}\n"
        f"Sponsorship Score: {sponsorship_score}/100\n"
        f"Remote Type: {remote_type}\n"
        f"EU Blue Card: {'Yes' if eu_blue_card else 'No'}\n"
        f"Relocation Support: {'Yes' if has_relocation else 'No'}\n\n"
        f"Job Description:\n{(description or 'No description available.')}\n"
        f"{cv_section}"
    )

    return f"{system_prompt}\n\n{objective_line}Here is the job to evaluate:\n\n{job_context}"


def build_cv_prompt(cv_text: str, jd_text: str, custom_prompt: Optional[str] = None) -> str:
    """Build the full prompt for CV tailoring."""
    system_prompt = custom_prompt or load_cv_prompt()
    return (
        f"{system_prompt}\n\n"
        f"=== CANDIDATE CV ===\n{cv_text}\n\n"
        f"=== JOB DESCRIPTION ===\n{jd_text}"
    )


def build_cover_letter_prompt(
    cv_text: str,
    jd_text: str,
    custom_prompt: Optional[str] = None,
    base_letter: Optional[str] = None,
) -> str:
    """Build the full prompt for cover-letter generation."""
    system_prompt = custom_prompt or load_cl_prompt()

    saved_letter = (base_letter or "").strip() or load_base_cover_letter()
    template_section = ""
    if saved_letter:
        template_section = (
            f"\n=== EXISTING COVER LETTER TEMPLATE (use this as style/structure reference) ===\n"
            f"{saved_letter}\n"
        )

    return (
        f"{system_prompt}\n\n"
        f"=== CANDIDATE CV ===\n{cv_text}\n\n"
        f"=== JOB DESCRIPTION ===\n{jd_text}"
        f"{template_section}"
    )


# -- Response parsing helpers ---------------------------------------------------
# These handle whatever text the user pastes back from the AI chat: markdown
# code fences, single-quoted "JSON", embedded prose, etc.

def _clean_ai_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    cleaned = cleaned.strip("` \n\r\t")
    return cleaned.strip()


def _extract_json_payload(text: str) -> str:
    raw = _clean_ai_text(text)
    start = raw.find("{")
    if start == -1:
        return raw

    depth = 0
    for index, char in enumerate(raw[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return raw[start:index + 1]

    return raw[start:]


def _parse_ai_json(text: str) -> dict:
    """Parse JSON from pasted AI response text.

    Handles: bare JSON, markdown code blocks, text-with-embedded-JSON,
    single-quoted Python dicts.
    """
    cleaned = _clean_ai_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        payload = _extract_json_payload(text)

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    # Try replacing single quotes with double quotes (common when models
    # output Python-dict-style text instead of JSON).
    try:
        fixed = payload.replace("'", '"')
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Try ast.literal_eval for Python dict/bool syntax
    try:
        parsed = ast.literal_eval(payload)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed[0]
    except Exception:
        pass

    # Last resort: try to find any JSON-like object with "rating" key
    match = re.search(r'"rating"\s*:\s*\d+', text)
    if match:
        rating_val = int(re.search(r'\d+', match.group()).group())
        verdict_val = ""
        verdict_match = re.search(r'"verdict"\s*:\s*"([^"]*)"', text)
        if verdict_match:
            verdict_val = verdict_match.group(1)
        return {"rating": rating_val, "verdict": verdict_val or "No verdict provided.", "pros": [], "cons": []}

    raise json.JSONDecodeError("Could not extract JSON from pasted text", text, 0)


def parse_rating_result(pasted_text: str) -> dict:
    """Parse a job-rating response pasted back from a web AI chat.

    Returns dict with: rating (0-10 int), verdict, pros, cons, error (if any).
    Mirrors the normalisation logic of the old network-based rate_job().
    """
    if not pasted_text or not pasted_text.strip():
        return {"error": "Nothing pasted. Copy the AI's reply and paste it here."}

    try:
        result = _parse_ai_json(pasted_text)
    except json.JSONDecodeError:
        return {
            "error": (
                "Could not parse the pasted text as JSON. Make sure you "
                "copied the AI's full reply (it should look like a JSON "
                "object with \"rating\", \"verdict\", \"pros\", \"cons\")."
            )
        }

    rating = result.get("rating", 0)
    if isinstance(rating, str):
        rating = rating.strip()
        if rating.isdigit():
            rating = int(rating)
        else:
            try:
                rating = int(float(rating))
            except ValueError:
                rating = 0
    elif isinstance(rating, float):
        rating = int(round(rating))
    elif not isinstance(rating, int):
        rating = 0

    rating = max(0, min(10, rating))
    result["rating"] = rating

    verdict = result.get("verdict")
    if not isinstance(verdict, str):
        result["verdict"] = str(verdict or "No verdict provided.")

    pros = result.get("pros")
    if not isinstance(pros, list):
        pros = [str(pros)] if pros is not None else []
    result["pros"] = [str(item) for item in pros if item is not None]

    cons = result.get("cons")
    if not isinstance(cons, list):
        cons = [str(cons)] if cons is not None else []
    result["cons"] = [str(item) for item in cons if item is not None]

    result.setdefault("verdict", "No verdict provided.")
    result.setdefault("pros", [])
    result.setdefault("cons", [])
    return result


def parse_text_result(pasted_text: str) -> dict:
    """Parse a CV/cover-letter response pasted back from a web AI chat.

    Just strips markdown fences -- the result is free-form text.
    Returns dict with: text, error (if any).
    """
    if not pasted_text or not pasted_text.strip():
        return {"text": "", "error": "Nothing pasted. Copy the AI's reply and paste it here."}
    return {"text": _clean_ai_text(pasted_text), "error": None}


# -- JD fetcher -----------------------------------------------------------------

def fetch_jd_from_url(url: str) -> dict:
    """Fetch and aggressively clean a job description."""
    import re
    import urllib.request
    from html import unescape

    try:
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SponsorScout/1.0)"
            }
        )

        with urllib.request.urlopen(req, timeout=20) as resp:
            raw_html = resp.read().decode("utf-8", errors="ignore")

        # Many ATS systems double-encode HTML entities
        raw_html = unescape(unescape(raw_html))

        if BeautifulSoup:
            soup = BeautifulSoup(raw_html, "html.parser")

            # Remove non-content tags
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()

            text = soup.get_text("\n", strip=True)

        else:
            # Fallback if bs4 isn't installed
            raw_html = re.sub(
                r"<(script|style|noscript)[^>]*>.*?</\1>",
                " ",
                raw_html,
                flags=re.I | re.S,
            )

            text = re.sub(r"<[^>]+>", " ", raw_html)

        # Decode entities again after extraction
        text = unescape(unescape(text))

        # Remove any HTML tags that survived
        text = re.sub(r"</?[^>]+>", " ", text)

        # Replace common HTML whitespace entities
        text = text.replace("\xa0", " ")

        # Normalize line endings
        text = text.replace("\r", "")

        # Remove excessive spaces/tabs
        text = re.sub(r"[ \t]+", " ", text)

        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove leading/trailing whitespace on each line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(line for line in lines if line)

        return {
            "text": text.strip(),
            "error": None,
        }

    except Exception as exc:
        return {
            "text": "",
            "error": str(exc),
        }
