"""Tests for sponsorscout.paths, specifically the bundled-Playwright
auto-detection used by the Windows/Linux packaged builds.

build_exe.ps1 / build_deb.sh bundle Chromium into a ``_playwright`` folder
next to the executable. On Linux the .deb's launcher script exports
PLAYWRIGHT_BROWSERS_PATH directly, but on Windows installer.iss relies on a
HKCU\\Environment registry write that doesn't propagate to the first
post-install launch. ``_configure_bundled_playwright_browsers_path`` makes
the app find the bundled Chromium itself regardless of that timing issue.
"""
from __future__ import annotations

import sys

import sponsorscout.paths as paths_module


def test_does_nothing_when_not_frozen(monkeypatch):
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    paths_module._configure_bundled_playwright_browsers_path()

    assert "PLAYWRIGHT_BROWSERS_PATH" not in __import__("os").environ


def test_does_nothing_when_env_var_already_set(monkeypatch, tmp_path):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/custom/path")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    bundled = tmp_path / "SponsorScout" / "_playwright"
    bundled.mkdir(parents=True)
    fake_exe = tmp_path / "SponsorScout" / "SponsorScout.exe"
    fake_exe.write_text("")
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    paths_module._configure_bundled_playwright_browsers_path()

    # Explicit override is preserved, not clobbered by the bundled path.
    assert __import__("os").environ["PLAYWRIGHT_BROWSERS_PATH"] == "/custom/path"


def test_sets_env_var_when_frozen_with_bundled_chromium(monkeypatch, tmp_path):
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    app_dir = tmp_path / "SponsorScout"
    bundled = app_dir / "_playwright"
    bundled.mkdir(parents=True)
    fake_exe = app_dir / "SponsorScout.exe"
    fake_exe.write_text("")
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    paths_module._configure_bundled_playwright_browsers_path()

    import os
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(bundled)


def test_does_nothing_when_frozen_but_no_bundled_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    app_dir = tmp_path / "SponsorScout"
    app_dir.mkdir(parents=True)
    fake_exe = app_dir / "SponsorScout.exe"
    fake_exe.write_text("")
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    # No "_playwright" directory created.

    paths_module._configure_bundled_playwright_browsers_path()

    import os
    assert "PLAYWRIGHT_BROWSERS_PATH" not in os.environ
