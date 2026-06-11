"""
AI Job Rating & Eligibility Service
Provider-agnostic — works with Google Gemini, NVIDIA NIM, and any
OpenAI-compatible endpoint (OpenAI, OpenRouter, Together, Groq, Ollama,
LM Studio, etc.), or a fully custom URL.

The user can type ANY model string from ANY provider. The UI suggestions are
provider-specific conveniences only, not an enforced allow-list. If a model
isn't enabled for the user's key/provider, the helper returns a clear error.
"""
from __future__ import annotations

import ast
import json
import os
import re
import urllib.request
import urllib.error
from typing import Optional
from sponsorscout.paths import USER_DATA_DIR, ensure_user_data_dir

# SECURITY: restrict API key file to owner-only read/write (0o600).
# Without this, any user on the machine can read the API key from
# ~/.sponsorscout/gemini_api_key.txt.
_KEY_FILE_MODE = 0o600

# ── User data directory (same folder as the DB) ──────────────────────────────
_USER_DIR = USER_DATA_DIR
ensure_user_data_dir()

PROMPT_PATH     = _USER_DIR / "ai_prompt.txt"
CV_PROMPT_PATH  = _USER_DIR / "cv_prompt.txt"
CL_PROMPT_PATH  = _USER_DIR / "cl_prompt.txt"
CL_LETTER_PATH  = _USER_DIR / "my_cover_letter.txt"
API_KEY_PATH    = _USER_DIR / "gemini_api_key.txt"
CV_PATH         = _USER_DIR / "my_cv.txt"
MODEL_PATH      = _USER_DIR / "ai_model.txt"
PROVIDER_PATH   = _USER_DIR / "ai_provider.txt"
BASE_URL_PATH   = _USER_DIR / "ai_base_url.txt"

# ── Provider settings ───────────────────────────────────────────────────────
# We do NOT enforce any specific model name. The user is free to type any
# model they want. The provider-specific suggestions below are UI conveniences
# only; providers regularly add/remove model IDs.
DEFAULT_MODEL     = "gemini-1.5-flash"   # most widely-available free tier
DEFAULT_PROVIDER  = "gemini"
DEFAULT_BASE_URLS = {
    # Google's free Gemini endpoint (v1beta for the modern generateContent API).
    "gemini": "https://generativelanguage.googleapis.com",
    # OpenAI's official chat-completions endpoint. Override for OpenRouter /
    # Groq / Together / Ollama / etc.
    "openai": "https://api.openai.com",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "ollama": "http://localhost:11434/v1",
    # Custom: user types the entire URL including the path.
    "custom": "",
}

SUGGESTED_MODELS_BY_PROVIDER = {
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ],
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
    ],
    "nvidia": [
        "openai/gpt-oss-20b",
        "nvidia/llama-3.1-nemotron-nano-8b-v1",
        "nvidia/llama-3.1-nemotron-nano-4b-v1.1",
        "nvidia/llama-3_3-nemotron-super-49b-v1_5",
    ],
    "openrouter": [
        "openai/gpt-oss-20b",
        "google/gemma-3-27b-it",
        "meta-llama/llama-3.1-8b-instruct",
    ],
    "groq": [
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
    ],
    "together": [
        "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "Qwen/Qwen2.5-7B-Instruct-Turbo",
    ],
    "ollama": [
        "llama3.1",
        "gemma3",
        "qwen2.5",
    ],
    "custom": [],
}
SUGGESTED_MODELS = [
    model
    for models in SUGGESTED_MODELS_BY_PROVIDER.values()
    for model in models
]

# ── Default prompts ─────────────────────────────────────────────────────────
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

Return ONLY the tailored CV text — no commentary, no markdown headers, no preamble."""

DEFAULT_CL_PROMPT = """You are an expert cover letter writer specialising in EU tech and data roles.

Given the candidate's CV and a full job description, write a compelling, personalised cover letter that:
1. Opens with a strong hook referencing the specific company and role.
2. Highlights 2-3 key achievements from the CV that directly address the JD's requirements.
3. Shows genuine enthusiasm for the company's mission/products (infer from JD context).
4. Briefly addresses visa/sponsorship situation positively and confidently.
5. Closes with a clear call to action.

Format: 3-4 paragraphs, ~300-400 words. Professional but warm tone.
Return ONLY the cover letter text — no subject lines, no placeholders like [Company Name]."""


# ── Persistence helpers ──────────────────────────────────────────────────────

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

def load_api_key() -> str:
    if API_KEY_PATH.exists():
        return API_KEY_PATH.read_text(encoding="utf-8").strip()
    return ""

def save_api_key(key: str) -> None:
    API_KEY_PATH.write_text(key.strip(), encoding="utf-8")
    os.chmod(API_KEY_PATH, _KEY_FILE_MODE)

def load_cv() -> str:
    if CV_PATH.exists():
        return CV_PATH.read_text(encoding="utf-8").strip()
    return ""

def save_cv(text: str) -> None:
    CV_PATH.write_text(text.strip(), encoding="utf-8")


# ── Model / provider persistence ────────────────────────────────────────────

def load_model() -> str:
    """Return the user's saved model name (free-form, any provider).

    Env-var override: SPONSORSCOUT_AI_MODEL
    """
    env = os.environ.get("SPONSORSCOUT_AI_MODEL", "").strip()
    if env:
        return env
    if MODEL_PATH.exists():
        saved = MODEL_PATH.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    return DEFAULT_MODEL

def save_model(name: str) -> None:
    if name and name.strip():
        MODEL_PATH.write_text(name.strip(), encoding="utf-8")

def load_provider() -> str:
    """Return a configured provider key from DEFAULT_BASE_URLS."""
    env = os.environ.get("SPONSORSCOUT_AI_PROVIDER", "").strip().lower()
    if env in DEFAULT_BASE_URLS:
        return env
    if PROVIDER_PATH.exists():
        saved = PROVIDER_PATH.read_text(encoding="utf-8").strip().lower()
        if saved in DEFAULT_BASE_URLS:
            return saved
    return DEFAULT_PROVIDER

def save_provider(name: str) -> None:
    name = (name or "").strip().lower()
    if name in DEFAULT_BASE_URLS:
        PROVIDER_PATH.write_text(name, encoding="utf-8")

def load_base_url() -> str:
    """Return the base URL the user has configured (or provider default)."""
    env = os.environ.get("SPONSORSCOUT_AI_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    if BASE_URL_PATH.exists():
        saved = BASE_URL_PATH.read_text(encoding="utf-8").strip()
        if saved:
            return saved.rstrip("/")
    return DEFAULT_BASE_URLS.get(load_provider(), "").rstrip("/")

def save_base_url(url: str) -> None:
    BASE_URL_PATH.write_text((url or "").strip(), encoding="utf-8")


# ── Universal AI call helper ────────────────────────────────────────────────

def _call_ai(
    api_key: str,
    prompt: str,
    max_tokens: int = 1024,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """Provider-agnostic AI call. Returns raw text from the model.

    Supports:
    - "gemini"   -> Google Gemini's generateContent endpoint
    - "openai"   -> OpenAI's /v1/chat/completions endpoint (also OpenAI-compatible
                   APIs: OpenRouter, Groq, Together, OpenAI, LM Studio, Ollama, etc.)
    - "custom"   -> user types the FULL URL (e.g. https://api.together.xyz/v1/chat/completions)

    The function transparently serialises the request in the right format and
    parses the response. Any 4xx/5xx error is raised as a `RuntimeError` so
    the caller can show a clean error to the user without depending on the
    `urllib` exception hierarchy.

    BUGFIX: previous version leaked `urllib.error.HTTPError` out of this
    function. The callers had to import urllib just to catch it, and any
    non-HTTP error (DNS, timeout, TLS, etc.) was lumped under the bare
    `except Exception` clause producing a generic message. We now wrap
    every error path in `RuntimeError` with a curated, human-readable
    message and a `from e` chain so the original traceback is preserved.
    """
    m  = (model     or load_model()).strip()
    p  = (provider  or load_provider()).strip().lower()
    bu = (base_url  or load_base_url()).strip().rstrip("/")
    if not m:
        raise RuntimeError("No AI model configured. Set one in Tools -> AI Settings.")
    if p != "gemini" and not bu:
        raise RuntimeError(
            f"No base URL set for provider '{p}'. "
            "Add it in Tools -> AI Settings -> Base URL."
        )

    # BUGFIX: AI providers (especially free-tier Gemini and OpenAI) return
    # 429 ("rate-limited / quota exceeded") or 503 ("service unavailable /
    # high demand") under transient load. The previous version surfaced
    # these as immediate, hard errors. We now retry with exponential
    # backoff (1s, 2s, 4s) and only surface the error if every attempt
    # fails. The user still gets a fast failure for 4xx codes that AREN'T
    # rate-limit / quota (401, 403, 404) — those won't recover from a wait.
    max_attempts = 3
    retryable_codes = {429, 500, 502, 503, 504}
    last_err: Exception | None = None
    import time as _time
    for attempt in range(1, max_attempts + 1):
        try:
            return _call_ai_once(p, m, bu, api_key, prompt, max_tokens)
        except RuntimeError as e:
            last_err = e
            msg = str(e)
            # Check if the error message contains a retryable HTTP code.
            code = None
            for c in retryable_codes:
                if (f" {c} " in msg) or (f" {c}:" in msg) or (f"error {c} " in msg):
                    code = c
                    break
            if code is None or attempt == max_attempts:
                # Wrap the original message with retry context so the user
                # understands WHY the error came back.
                if attempt > 1:
                    raise RuntimeError(
                        f"{msg} (after {attempt} attempts, gave up)"
                    ) from e
                raise
            backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s
            # Cap the backoff at 8s so we don't hang the UI forever.
            backoff = min(backoff, 8)
            _time.sleep(backoff)
    # Should never reach here, but be defensive.
    raise last_err or RuntimeError("AI request failed after retries")


def _call_ai_once(p, m, bu, api_key, prompt, max_tokens):
    """Single attempt at the AI call. Raises RuntimeError on failure."""
    # --- Google Gemini path ---
    if p == "gemini":
        url = f"{bu}/v1beta/models/{m}:generateContent?key={api_key}"
        body = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": max_tokens,
            },
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            if "candidates" not in raw or not raw["candidates"]:
                raise RuntimeError(
                    f"Gemini returned no candidates. "
                    f"Model '{m}' may not be enabled for your key, "
                    f"or the prompt was blocked. Full response: "
                    f"{json.dumps(raw)[:300]}"
                )
            return raw["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            try:
                msg = json.loads(err_body).get("error", {}).get("message", err_body[:300])
            except Exception:
                msg = err_body[:300]
            raise RuntimeError(
                f"Gemini API error {e.code} for model '{m}': {msg}"
            ) from e
        except urllib.error.URLError as e:
            # DNS failure, connection refused, TLS error, etc.
            raise RuntimeError(
                f"Could not reach Gemini at {bu}: {e.reason}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Gemini request failed: {e}") from e

    # --- OpenAI-compatible path (covers OpenAI, OpenRouter, Groq, Together,
    #     Ollama, LM Studio, NVIDIA NIM, etc.) ---
    if p != "gemini":
        url = _chat_completions_url(bu, exact=(p == "custom"))
        body = json.dumps({
            "model": m,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": max_tokens,
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        req = urllib.request.Request(
            url, data=body, headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            return raw["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            try:
                jerr = json.loads(err_body)
                if isinstance(jerr, dict) and "error" in jerr:
                    err = jerr["error"]
                    if isinstance(err, dict):
                        msg = err.get("message", err_body[:300])
                    else:
                        msg = str(err)
                else:
                    msg = err_body[:300]
            except Exception:
                msg = err_body[:300]
            raise RuntimeError(
                _format_ai_http_error(e.code, m, p, url, msg)
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Could not reach AI endpoint at {url}: {e.reason}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"AI request failed: {e}") from e

    raise RuntimeError(
        f"Unknown provider '{p}'. Use one of: {', '.join(DEFAULT_BASE_URLS)}."
    )


def _chat_completions_url(base_url: str, exact: bool = False) -> str:
    """Return the correct chat-completions URL for OpenAI-compatible APIs."""
    url = (base_url or "").strip().rstrip("/")
    if exact or url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1") or url.endswith("/openai/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def _format_ai_http_error(code: int, model: str, provider: str, url: str, msg: str) -> str:
    detail = f"AI API error {code} for model '{model}' on provider '{provider}': {msg}"
    if code == 404:
        return (
            f"{detail}. This usually means the model ID is not available on "
            f"that provider/base URL. Check the provider's model catalog, "
            f"then update Tools -> AI Settings -> Model."
        )
    return detail


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
    """Parse JSON from AI response text.

    Handles: bare JSON, markdown code blocks, text-with-embedded-JSON,
    single-quoted Python dicts, and Gemini's nested response format.
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

    # Try replacing single quotes with double quotes (common Gemini output)
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
    import re as _re
    match = _re.search(r'"rating"\s*:\s*\d+', text)
    if match:
        # Extract a minimal dict from the raw text
        rating_val = int(_re.search(r'\d+', match.group()).group())
        verdict_val = ""
        verdict_match = _re.search(r'"verdict"\s*:\s*"([^"]*)"', text)
        if verdict_match:
            verdict_val = verdict_match.group(1)
        return {"rating": rating_val, "verdict": verdict_val or "No verdict provided.", "pros": [], "cons": []}

    raise json.JSONDecodeError("Could not extract JSON from AI response", text, 0)


# --- Job rating -------------------------------------------------------------

def rate_job(
    title: str,
    company: str,
    country: str,
    description: str,
    sponsorship_score: int,
    remote_type: str,
    eu_blue_card: bool,
    has_relocation: bool,
    api_key: str,
    custom_prompt: Optional[str] = None,
) -> dict:
    """Call the configured AI to rate a job and assess eligibility.

    Injects the user's saved CV so the rating reflects their actual profile.
    Returns dict with: rating, verdict, pros, cons, error (if any).
    """
    if not api_key:
        return {"error": "No API key configured. Set it in Tools -> AI Settings."}

    system_prompt = custom_prompt or load_prompt()
    cv_text = load_cv()
    cv_section = (
        f"\n=== CANDIDATE CV (use this to personalise the eligibility assessment) ===\n"
        f"{cv_text[:3000]}\n"
        if cv_text else
        "\n(No CV on file -- rating based on job details only. Paste your CV in the AI Tailor tab for personalised results.)\n"
    )

    job_context = (
        f"Job Title: {title}\n"
        f"Company: {company}\n"
        f"Country: {country}\n"
        f"Sponsorship Score: {sponsorship_score}/100\n"
        f"Remote Type: {remote_type}\n"
        f"EU Blue Card: {'Yes' if eu_blue_card else 'No'}\n"
        f"Relocation Support: {'Yes' if has_relocation else 'No'}\n\n"
        f"Job Description:\n{(description or 'No description available.')[:3000]}\n"
        f"{cv_section}"
    )

    try:
        raw_text = _call_ai(
            api_key,
            f"{system_prompt}\n\nHere is the job to evaluate:\n\n{job_context}",
            max_tokens=512,
        )
        try:
            result = _parse_ai_json(raw_text)
        except json.JSONDecodeError as exc:
            return {
                "error": (
                    "Could not parse AI response as JSON. "
                    "Please try again with a simpler prompt or a different model."
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
    # BUGFIX: _call_ai() now raises RuntimeError on every error path
    # (HTTP, network, JSON, etc.). The previous `except urllib.error.HTTPError`
    # block was therefore dead code and the real RuntimeError was only
    # caught by the bare `except Exception` clause -- producing an
    # unnecessarily generic message. Catch RuntimeError explicitly so the
    # user sees the curated message from _call_ai().
    except RuntimeError as e:
        return {"error": str(e)}
    except json.JSONDecodeError as e:
        return {"error": f"Could not parse AI response as JSON: {e}"}
    except Exception as e:
        return {"error": str(e)}


# --- JD fetcher -------------------------------------------------------------

def fetch_jd_from_url(url: str) -> dict:
    """Fetch a job description from a URL. Returns {text, error}.

    Strips HTML tags to get plain text.
    """
    try:
        import re as _re
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SponsorScout/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        html = _re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=_re.DOTALL | _re.IGNORECASE)
        text = _re.sub(r"<[^>]+>", " ", html)
        text = _re.sub(r"[ \t]+", " ", text)
        text = _re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        return {"text": text[:8000], "error": None}
    except Exception as exc:
        return {"text": "", "error": str(exc)}


# --- CV tailoring -----------------------------------------------------------

def tailor_cv(
    cv_text: str,
    jd_text: str,
    api_key: str,
    custom_prompt: Optional[str] = None,
) -> dict:
    """Tailor the user's CV to a job description. Returns {text, error}."""
    if not api_key:
        return {"text": "", "error": "No API key. Set it in Tools -> AI Settings."}
    if not cv_text.strip():
        return {"text": "", "error": "No CV found. Paste your CV in the Tailor tab first."}
    if not jd_text.strip():
        return {"text": "", "error": "No job description. Fetch or paste the JD first."}

    system_prompt = custom_prompt or load_cv_prompt()
    prompt = (
        f"{system_prompt}\n\n"
        f"=== CANDIDATE CV ===\n{cv_text[:4000]}\n\n"
        f"=== JOB DESCRIPTION ===\n{jd_text[:4000]}"
    )
    try:
        text = _call_ai(api_key, prompt, max_tokens=2048)
        return {"text": _clean_ai_text(text), "error": None}
    # BUGFIX: same as rate_job() -- _call_ai now raises RuntimeError on
    # every error path, so catching urllib.error.HTTPError here is dead
    # code. Catch RuntimeError explicitly.
    except RuntimeError as e:
        return {"text": "", "error": str(e)}
    except Exception as e:
        return {"text": "", "error": str(e)}


# --- Cover letter writing ----------------------------------------------------

def write_cover_letter(
    cv_text: str,
    jd_text: str,
    api_key: str,
    custom_prompt: Optional[str] = None,
    base_letter: Optional[str] = None,
) -> dict:
    """Generate a tailored cover / motivation letter. Returns {text, error}.

    If a *base_letter* is provided (or saved on disk), the AI is asked to
    use it as a style / structure template so every generated letter
    matches the user's preferred tone and formatting.
    """
    if not api_key:
        return {"text": "", "error": "No API key. Set it in Tools -> AI Settings."}
    if not cv_text.strip():
        return {"text": "", "error": "No CV found. Paste your CV in the Tailor tab first."}
    if not jd_text.strip():
        return {"text": "", "error": "No job description. Fetch or paste the JD first."}

    system_prompt = custom_prompt or load_cl_prompt()

    # Prefer an explicit argument, fall back to the saved file on disk.
    saved_letter = (base_letter or "").strip() or load_base_cover_letter()
    template_section = ""
    if saved_letter:
        template_section = (
            f"\n=== EXISTING COVER LETTER TEMPLATE (use this as style/structure reference) ===\n"
            f"{saved_letter[:3000]}\n"
        )

    prompt = (
        f"{system_prompt}\n\n"
        f"=== CANDIDATE CV ===\n{cv_text[:3000]}\n\n"
        f"=== JOB DESCRIPTION ===\n{jd_text[:4000]}"
        f"{template_section}"
    )
    try:
        text = _call_ai(api_key, prompt, max_tokens=1024)
        return {"text": _clean_ai_text(text), "error": None}
    # BUGFIX: same as rate_job()/tailor_cv() -- catch RuntimeError, not the
    # dead urllib.error.HTTPError path. _call_ai() wraps all errors in
    # RuntimeError now.
    except RuntimeError as e:
        return {"text": "", "error": str(e)}
    except Exception as e:
        return {"text": "", "error": str(e)}
