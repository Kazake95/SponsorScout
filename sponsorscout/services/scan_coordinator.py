"""Foreground scan coordinator.

SponsorScout never runs a persistent background scan loop. This small
coordinator exists so the UI and CLI can share scan progress and completion
handling; manual scans run in a one-shot worker thread to keep the desktop
UI responsive. The class used to be named ``BackgroundScanner`` and is
preserved here under its new, accurate name for backwards compatibility
with anyone importing it as such.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from sponsorscout.db.database import initialize, DB_PATH
from sponsorscout.services.registry_loader import load_seed_registry
from sponsorscout.core.scanner import scan_all

logger = logging.getLogger(__name__)


class ScanCoordinator:
    def __init__(
        self,
        db_path: Path = DB_PATH,
        on_progress: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[int], None]] = None,
    ):
        self.db_path = db_path
        self.on_progress = on_progress or (lambda msg: print(msg))
        self.on_complete = on_complete or (lambda n: None)
        self._scan_in_progress = threading.Lock()
        self._last_run: Optional[float] = None

    def set_on_progress(self, callback: Optional[Callable[[str], None]]) -> None:
        """Replace the progress callback used during scans."""
        if callback is None:
            return
        self.on_progress = callback

    def start(self):
        # Background/periodic scanning has been disabled in the UI and is now
        # a no-op here to guarantee the app never keeps a persistent scan loop
        # alive after the main window closes.
        self.on_progress("Automatic background scanning is disabled.")
        return

    def stop(self):
        """No background worker exists to stop."""
        return

    def pause(self):
        return

    def resume(self):
        return

    @property
    def is_running(self) -> bool:
        return False

    @property
    def is_scanning(self) -> bool:
        return self._scan_in_progress.locked()

    @property
    def last_run(self) -> Optional[float]:
        return self._last_run

    def run_now(self):
        """Run a scan in a one-shot worker thread.

        This keeps the app responsive without enabling a persistent background
        loop.
        """
        if not self._scan_in_progress.acquire(blocking=False):
            self.on_progress("Scan already in progress; skipping this request.")
            return
        t = threading.Thread(
            target=self._guarded_scan,
            name="SponsorScout-ImmediateScan",
            daemon=True,
        )
        t.start()

    def _guarded_scan(self):
        """Run _do_scan under the in-progress lock, always releasing it."""
        try:
            self._do_scan()
        finally:
            try:
                self._scan_in_progress.release()
            except RuntimeError:
                pass

    def _do_scan(self):
        self.on_progress("Scan starting…")
        found = []
        try:
            initialize(self.db_path)
            companies = load_seed_registry()
            total = len(companies)
            self.on_progress(f"Scanning {total} companies…")

            def _company_progress(msg, done, total_c):
                pct = int(done / total_c * 100) if total_c else 0
                self.on_progress(f"[{done}/{total_c}  {pct}%]  {msg}")

            found = scan_all(
                companies,
                db_path=self.db_path,
                parallel=False,
                on_progress=_company_progress,
            )
            self._last_run = time.time()
            self.on_progress(
                f"✅ Scan complete — {len(found)} jobs found across {total} companies."
            )
        except Exception as exc:
            logger.exception("Scan failed")
            self.on_progress(f"Scan error: {exc}")
        finally:
            self.on_complete(len(found))

# Backwards-compatible alias for the old class name.
BackgroundScanner = ScanCoordinator
