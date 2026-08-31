"""Unified AI API gateway — calls Google AI Studio or OpenAI-compatible endpoints.

This module provides a single ``call_ai()`` entry point that dispatches to
the appropriate SDK based on the user's ``AIConfig``:

* **google** SDK — for Google AI Studio (Gemini).
* **openai** SDK — for NVIDIA NIM, OpenAI, or any OpenAI-compatible server.

The callers (from ``ui/app.py``) never need to know which SDK is in use;
they just pass a prompt string and get back the raw text response.

Designed to be called from a background thread (the UI thread must not
block on network I/O).
"""
from __future__ import annotations

import logging
from typing import Optional

from sponsorscout.services.ai_config import AIConfig, load_config

logger = logging.getLogger(__name__)


# ── Public API ───────────────────────────────────────────────────────────────

def call_ai(
    prompt: str,
    *,
    config: Optional[AIConfig] = None,
    system_instruction: Optional[str] = None,
) -> str:
    """Send *prompt* to the configured AI backend and return the response text.

    Parameters
    ----------
    prompt : str
        The full user prompt (may include system instructions baked in).
    config : AIConfig, optional
        API configuration. If ``None``, loads from disk.
    system_instruction : str, optional
        Extra system-level instruction prepended by the SDK when supported.
        Ignored for OpenAI-style endpoints (they receive it as the first
        user message instead).

    Returns
    -------
    str
        The model's text reply.

    Raises
    ------
    RuntimeError
        If the config is incomplete, the SDK is missing, or the API call
        fails after retries.
    """
    if config is None:
        config = load_config()

    if not config.is_configured:
        raise RuntimeError(
            "AI API is not configured. Open the AI Settings tab and fill in "
            "your API key, base URL, and model name."
        )

    sdk = config.sdk
    if sdk == "google":
        return _call_google(prompt, config, system_instruction=system_instruction)
    elif sdk == "openai":
        return _call_openai(prompt, config, system_instruction=system_instruction)
    else:
        raise RuntimeError(f"Unknown SDK type: {sdk!r}")


def test_connection(config: Optional[AIConfig] = None) -> str:
    """Send a trivial prompt to verify the API key and endpoint are valid.

    Returns a short success message or raises ``RuntimeError`` on failure.
    """
    if config is None:
        config = load_config()
    if not config.is_configured:
        raise RuntimeError("AI API is not configured yet.")

    logger.info("Testing AI connection to %s / %s", config.base_url, config.model_name)
    reply = call_ai(
        "Reply with exactly: CONNECTION_OK",
        config=config,
    )
    short = reply.strip()[:200]
    return f"Connection OK — model replied: {short!r}"


# ── Google AI Studio (gemini) ───────────────────────────────────────────────

def _call_google(
    prompt: str,
    config: AIConfig,
    *,
    system_instruction: Optional[str] = None,
) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError(
            "The 'google-generativeai' package is not installed.\n"
            "Run:  pip install google-generativeai"
        )

    genai.configure(api_key=config.api_key)

    model = genai.GenerativeModel(
        model_name=config.model_name,
        system_instruction=system_instruction or None,
    )

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=8192,
                temperature=0.4,
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Google AI Studio API call failed: {exc}") from exc

    # The response object may have candidates; extract the text safely.
    text = _extract_google_text(response)
    if not text:
        raise RuntimeError(
            "Google AI Studio returned an empty response. "
            "Check your API key and model name."
        )
    return text


def _extract_google_text(response) -> str:
    """Safely extract text from a Gemini GenerateContentResponse."""
    # Try the standard .text property first.
    try:
        txt = response.text
        if txt:
            return txt
    except (AttributeError, ValueError):
        pass

    # Fallback: iterate candidates.
    try:
        parts = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    parts.append(part.text)
        if parts:
            return "\n".join(parts)
    except (AttributeError, IndexError, TypeError):
        pass

    # Last resort: stringify the response.
    return str(response)[:4096]


# ── OpenAI-compatible (NVIDIA NIM, OpenAI, vLLM, Ollama, etc.) ─────────────

def _call_openai(
    prompt: str,
    config: AIConfig,
    *,
    system_instruction: Optional[str] = None,
) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "The 'openai' package is not installed.\n"
            "Run:  pip install openai"
        )

    client = OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout,
    )

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=config.model_name,
            messages=messages,
            max_tokens=8192,
            temperature=0.4,
        )
    except Exception as exc:
        raise RuntimeError(f"OpenAI-compatible API call failed: {exc}") from exc

    text = response.choices[0].message.content if response.choices else ""
    if not text:
        raise RuntimeError(
            "The API returned an empty response. "
            "Check your API key, base URL, and model name."
        )
    return text