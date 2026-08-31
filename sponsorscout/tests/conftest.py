"""Shared pytest fixtures.

SPONSORSCOUT_DATA_DIR must be set BEFORE importing sponsorscout.paths,
because paths.USER_DATA_DIR is computed at import time.
"""
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """Redirect the per-user data dir into a pytest tmp dir (pre-import)."""
    monkeypatch.setenv("SPONSORSCOUT_DATA_DIR", str(tmp_path / "userdata"))
    # Force a re-import of paths so USER_DATA_DIR/SEEDS_DIR point at tmp.
    for mod in [m for m in list(sys.modules) if m.startswith("sponsorscout")]:
        del sys.modules[mod]
    import sponsorscout.paths as paths
    return paths.ensure_user_data_dir()


@pytest.fixture()
def db_path(data_dir):
    from sponsorscout.db import database as db
    path = str(data_dir / "test.db")
    if os.path.exists(path):
        os.remove(path)
    db.initialize(path)
    return path
