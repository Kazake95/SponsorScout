"""Qt-side scan orchestration.

Thin wrapper around ``scanning.pipeline.run_scan``: runs the campaign in a
worker thread and streams progress to the UI through Qt signals (safe to
emit from a non-Qt thread — Qt queues cross-thread signal deliveries).
"""

from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal


class ScanCoordinator(QObject):
    """Owns the background scan thread; the UI talks only to this object."""

    #: One line of scan log output (what the CLI scripts print).
    progress = Signal(str)
    #: Emitted once when the scan thread ends; carries the pipeline summary.
    finished = Signal(dict)

    def __init__(self, db_path: str | None = None):
        super().__init__()
        self.db_path = db_path
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Public API (main thread) ─────────────────────────────────────────────
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, method: str = "quick") -> bool:
        """Start a scan campaign ('quick' or 'full'). False if already running."""
        if self.is_running():
            return False
        self._cancel.clear()

        def worker():
            from sponsorscout.scanning import pipeline

            try:
                summary = pipeline.run_scan(
                    method=method,
                    db_path=self.db_path,
                    cancel_event=self._cancel,
                    progress=lambda m: self.progress.emit(str(m)),
                )
            except Exception as exc:  # defensive: never kill the thread silently
                summary = {
                    "run_id": "", "method": method, "status": "error",
                    "cancelled": False, "ingested": 0, "duplicates": 0,
                    "log_rows": 0, "artifacts": {},
                    "errors": [f"{type(exc).__name__}: {exc}"],
                }
            self.finished.emit(summary)

        self._thread = threading.Thread(target=worker, name="ScanWorker", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Cooperative stop: scanners check this between targets/companies."""
        self._cancel.set()
