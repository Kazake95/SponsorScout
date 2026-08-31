"""AI API configuration — persistence and provider defaults.

Stores the user's chosen AI provider, base URL, API key, model name, and
timeout in ``~/.sponsorscout/ai_config.json``.

Supports two built-in provider presets:

* **Google AI Studio** (Gemini) — uses the ``google-generativeai`` SDK.
* **NVIDIA NIM** (or any OpenAI-compatible endpoint) — uses the ``openai``
  SDK with a custom base URL.

The user can freely override any field (e.g. point to a local NVIDIA NIM
server, a different Gemini model, or a self-hosted vLLM / Ollama instance).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from sponsorscout.paths import USER_DATA_DIR, ensure_user_data_dir

logger = logging.getLogger(__name__)

_USER_DIR = USER_DATA_DIR
ensure_user_data_dir()

CONFIG_PATH = _USER_DIR / "ai_config.json"


# ── Provider presets ─────────────────────────────────────────────────────────

PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "Google AI Studio": {
        "base_url": "https://generativelanguage.googleapis.com",
        "model_name": "gemini-2.0-flash",
        "sdk": "google",
    },
    "NVIDIA NIM": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model_name": "meta/llama-3.1-8b-instruct",
        "sdk": "openai",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o-mini",
        "sdk": "openai",
    },
    "Custom (OpenAI-compatible)": {
        "base_url": "",
        "model_name": "",
        "sdk": "openai",
    },
}

PROVIDER_NAMES = list(PROVIDER_PRESETS.keys())


# ── Data class ───────────────────────────────────────────────────────────────

@dataclass
class AIConfig:
    """Runtime representation of the user's AI API settings."""

    provider: str = "Google AI Studio"
    base_url: str = "https://generativelanguage.googleapis.com"
    api_key: str = ""
    model_name: str = "gemini-2.0-flash"
    timeout: int = 120

    # Derived at runtime (not persisted)
    sdk: str = "google"

    def apply_preset(self) -> None:
        """Fill base_url/model_name/sdk from the built-in preset for the
        current provider, but only if the user hasn't manually overridden
        them (i.e. only on first load or when the provider changes).
        """
        preset = PROVIDER_PRESETS.get(self.provider, {})
        if not self.base_url and preset.get("base_url"):
            self.base_url = preset["base_url"]
        if not self.model_name and preset.get("model_name"):
            self.model_name = preset["model_name"]
        self.sdk = preset.get("sdk", "openai")

    @property
    def is_configured(self) -> bool:
        """Return True if the user has filled in enough to attempt an API call."""
        return bool(self.api_key.strip() and self.base_url.strip() and self.model_name.strip())


# ── Persistence ──────────────────────────────────────────────────────────────

def load_config() -> AIConfig:
    """Load the saved config from disk, or return defaults."""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg = AIConfig(
                provider=data.get("provider", "Google AI Studio"),
                base_url=data.get("base_url", ""),
                api_key=data.get("api_key", ""),
                model_name=data.get("model_name", ""),
                timeout=data.get("timeout", 120),
            )
            cfg.apply_preset()
            return cfg
        except Exception as exc:
            logger.warning("Failed to load AI config, using defaults: %s", exc)

    cfg = AIConfig()
    cfg.apply_preset()
    return cfg


def save_config(cfg: AIConfig) -> None:
    """Persist the config to disk."""
    data = {
        "provider": cfg.provider,
        "base_url": cfg.base_url,
        "api_key": cfg.api_key,
        "model_name": cfg.model_name,
        "timeout": cfg.timeout,
    }
    CONFIG_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("AI config saved to %s", CONFIG_PATH)


def reset_config() -> AIConfig:
    """Delete the config file and return fresh defaults."""
    if CONFIG_PATH.exists():
        try:
            CONFIG_PATH.unlink()
        except Exception as exc:
            logger.warning("Could not delete AI config: %s", exc)
    return load_config()