"""Qt-side scan orchestration.

Thin wrapper around ``scanning.pipeline.run_scan``: runs the campaign in a
worker thread and streams progress to the UI through Qt signals (safe to
emit from a non-Qt thread — Qt queues cross-thread signal deliveries).
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal


class ScanCoordinator(QObject):
    """Owns the background scan thread; the UI talks only to this object."""

    #: One chunk of scan log output (what the CLI scripts print).  Chunks are
    #: newline-joined batches, not single lines — see ``_PROGRESS_*`` below.
    progress = Signal(str)
    #: Emitted once when the scan thread ends; carries the pipeline summary.
    finished = Signal(dict)

    # Progress batching.  The scanners emit a line per company, per page and
    # per 100 detail checks; forwarding every line as its own queued Qt signal
    # floods the GUI thread (and the log widget) on long scans, which is what
    # made the window feel frozen.  Instead the worker joins lines into a
    # single chunk, rate-limited to PROGRESS_FLUSH_SEC / PROGRESS_FLUSH_LINES.
    PROGRESS_FLUSH_SEC = 0.15
    PROGRESS_FLUSH_LINES = 40

    def __init__(self, db_path: str | None = None):
        super().__init__()
        self.db_path = db_path
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Public API (main thread) ─────────────────────────────────────────────
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, method: str = "full") -> bool:
        """Start a scan campaign. False if a scan is already running.

        The app uses a single scan mode (``"full"``): ATS boards + career
        pages + per-job detail-page enrichment, so every job is extracted
        with full detail.  ``"quick"`` remains available to the dev CLI
        (ATS/career crawl without the detail-page enrichment pass).
        """
        if self.is_running():
            return False
        self._cancel.clear()

        def worker():
            from sponsorscout.scanning import pipeline

            # Rate-limited progress pump (see constants above).
            pending: list[str] = []
            lock = threading.Lock()
            last = [0.0]

            def flush_progress():
                with lock:
                    chunk = "\n".join(pending)
                    pending.clear()
                    last[0] = time.monotonic()
                if chunk:
                    self.progress.emit(chunk)

            def on_progress(message):
                with lock:
                    pending.append(str(message))
                    due = (len(pending) >= self.PROGRESS_FLUSH_LINES
                           or (time.monotonic() - last[0]) >= self.PROGRESS_FLUSH_SEC)
                if due:
                    flush_progress()

            try:
                summary = pipeline.run_scan(
                    method=method,
                    db_path=self.db_path,
                    cancel_event=self._cancel,
                    progress=on_progress,
                )
            except Exception as exc:  # defensive: never kill the thread silently
                summary = {
                    "run_id": "", "method": method, "status": "error",
                    "cancelled": False, "ingested": 0, "duplicates": 0,
                    "log_rows": 0, "artifacts": {},
                    "errors": [f"{type(exc).__name__}: {exc}"],
                }
            flush_progress()
            self.finished.emit(summary)

        self._thread = threading.Thread(target=worker, name="ScanWorker", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Cooperative stop: scanners check this between targets/companies."""
        self._cancel.set()
