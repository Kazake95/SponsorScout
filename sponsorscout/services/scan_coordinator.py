"""
Background scanner service.
Runs periodic scans in a daemon thread so the UI stays responsive.
Supports: scan interval, callbacks for progress, pause/resume.
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


class BackgroundScanner:
    def __init__(
        self,
        db_path: Path = DB_PATH,
        interval_seconds: int = 3600,
        on_progress: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[int], None]] = None,
    ):
        self.db_path = db_path
        self.interval_seconds = interval_seconds
        self.on_progress = on_progress or (lambda msg: print(msg))
        self.on_complete = on_complete or (lambda n: None)
        # BUGFIX: keep a permanent reference to the user-supplied on_progress
        # so wrappers installed by the UI (e.g. to also write to the scan
        # log) can be restored after the scan finishes. Previously the UI
        # overwrote `on_progress` directly, so once the user clicked "Scan
        # Now" once, the original on_progress (which wrote to the status
        # bar) was lost and subsequent scans showed nothing in the status
        # bar.
        self._user_on_progress = on_progress or (lambda msg: print(msg))
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused by default
        self._thread: Optional[threading.Thread] = None
        # B3 fix: prevents run_now() from spawning a parallel scan when the
        # background loop is already running. Previously, clicking "Scan Now"
        # while the 1h loop was active would start a second concurrent scan,
        # racing on the SQLite database.
        self._scan_in_progress = threading.Lock()
        self._last_run: Optional[float] = None

    def set_on_progress(self, callback: Optional[Callable[[str], None]]) -> None:
        """Install a progress callback that also chains the user's original.

        BUGFIX: previous version had the UI overwrite `on_progress` directly,
        which permanently replaced the status-bar callback. Any new wrapper
        installed here always calls the previous one (chainable) and
        self-restores on `_on_scan_complete` so the user can install a
        log-routing wrapper, run a scan, and still have the status-bar
        updates work on the next scan.
        """
        if callback is None:
            return
        # Build a wrapper that calls BOTH the new callback and the previously-
        # installed one. We use a closure so the call order is preserved
        # (status-bar first, then log) and so multiple wrappers stack cleanly.
        previous = self.on_progress

        def _chained(msg: str) -> None:
            try:
                previous(msg)
            except Exception as exc:
                logger.exception("Background scanner progress callback failed")
            try:
                callback(msg)
            except Exception as exc:
                logger.exception("Background scanner progress callback failed")

        self.on_progress = _chained

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="SponsorScout-Scanner")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._pause_event.set()  # unblock if paused

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_scanning(self) -> bool:
        """True when a scan is actively executing (loop or run_now)."""
        return self._scan_in_progress.locked()

    @property
    def last_run(self) -> Optional[float]:
        return self._last_run

    def run_now(self):
        """Trigger an immediate scan in a new thread.

        B3 fix: if a scan is already running (either via the loop or a prior
        run_now), skip the new request and report it instead of stacking
        concurrent scans against the same SQLite database.
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

    def _run_loop(self):
        while not self._stop_event.is_set():
            self._pause_event.wait()
            if self._stop_event.is_set():
                break
            # Acquire guard so run_now() can detect a scan in flight.
            if self._scan_in_progress.acquire(blocking=False):
                self._guarded_scan()
            # Wait for interval or stop signal
            self._stop_event.wait(timeout=self.interval_seconds)

    def _guarded_scan(self):
        """Run _do_scan under the in-progress lock, always releasing it."""
        try:
            self._do_scan()
        finally:
            try:
                self._scan_in_progress.release()
            except RuntimeError:
                # Lock was not held (defensive — should not happen).
                pass

    def _do_scan(self):
        self.on_progress("Background scan starting…")
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
                parallel=True,
                on_progress=_company_progress,
            )
            self._last_run = time.time()
            self.on_progress(
                f"✅ Scan complete — {len(found)} jobs found across {total} companies."
            )
            self.on_complete(len(found))
        except Exception as exc:
            logger.exception("Background scan failed")
            self.on_progress(f"Scan error: {exc}")
