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
    """Redirect the per-user data dir into a pytest tmp dir (pre-import).

    ``paths.USER_DATA_DIR`` is computed at import time, so the ``sponsorscout``
    modules are dropped from ``sys.modules`` and re-imported against the
    patched env var.

    The module set that existed before the purge is snapshotted and restored on
    teardown.  Without that restore the purge leaves *two* live copies of every
    module: the one other test modules imported at collection time, and the
    fresh one later function-level imports resolve through ``sys.modules``.
    A test that monkeypatches an attribute on a module it imported at the top
    of the file (e.g. ``seed_manager.user_ats_path``) would then see its patch
    silently bypassed by code doing ``from sponsorscout.application import
    seed_manager`` inside a function.
    """
    monkeypatch.setenv("SPONSORSCOUT_DATA_DIR", str(tmp_path / "userdata"))
    saved = {name: mod for name, mod in list(sys.modules.items())
             if name.startswith("sponsorscout")}
    # Force a re-import of paths so USER_DATA_DIR/SEEDS_DIR point at tmp.
    for name in saved:
        del sys.modules[name]
    try:
        import sponsorscout.paths as paths
        yield paths.ensure_user_data_dir()
    finally:
        for name in [m for m in list(sys.modules)
                     if m.startswith("sponsorscout")]:
            del sys.modules[name]
        sys.modules.update(saved)


@pytest.fixture()
def db_path(data_dir):
    from sponsorscout.db import database as db
    path = str(data_dir / "test.db")
    if os.path.exists(path):
        os.remove(path)
    db.initialize(path)
    return path
