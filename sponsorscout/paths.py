from __future__ import annotations

import os
from pathlib import Path


APP_DIR_ENV = "SPONSORSCOUT_DATA_DIR"
DB_PATH_ENV = "SPONSORSCOUT_DB_PATH"


def get_user_data_dir() -> Path:
    """Return the single per-user directory for all mutable app data."""
    override = os.environ.get(APP_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".sponsorscout"


USER_DATA_DIR = get_user_data_dir()
DB_PATH = Path(os.environ.get(DB_PATH_ENV, "")).expanduser() if os.environ.get(DB_PATH_ENV) else USER_DATA_DIR / "sponsorscout.db"


def ensure_user_data_dir() -> Path:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return USER_DATA_DIR
