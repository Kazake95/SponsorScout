"""Tools tab: scanner control, scan history, data quality, freshness checks.

Ported from the tkinter Tools tab (scan control + streaming log, dedup,
stale-data cleanup, freshness verification) with the addition of the
per-run scan history view backed by the scan_runs / scan_log tables.
"""

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from sponsorscout.application.scan_coordinator import ScanCoordinator
from sponsorscout.core.dedup import dedup_companies_in_db, dedup_jobs_in_db
from sponsorscout.db import database as db
from sponsorscout.i18n import _

HEADERS_RUNS = ["Run ID", "Method", "Started", "Status", "Jobs", "Dups",
                "Quarantined", "Errors"]
HEADERS_LOG = ["Seed", "Company", "Status", "Provider", "Jobs", "Quar.",
               "Dups", "Scope Rej.", "Error"]


class ScanLogDialog(QDialog):
    """Per-company outcomes of one scan run (from the scan_log table)."""

    def __init__(self, db_path: str, run_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Scan log — {run_id}")
        self.resize(900, 500)
        lay = QVBoxLayout(self)
        table = QTableWidget(0, len(HEADERS_LOG))
        table.setHorizontalHeaderLabels(HEADERS_LOG)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for row in db.get_scan_log(db_path, run_id):
            r = table.rowCount()
            table.insertRow(r)
            for col, val in enumerate(row):
                table.setItem(r, col, QTableWidgetItem(str(val or "")))
        lay.addWidget(table)


class ToolsTab(QWidget):
    """Scanner control + data-quality tools (mirrors the original Tools tab)."""

    scan_finished = Signal(dict)
    data_changed = Signal()        # jobs/companies data may have changed
    status_message = Signal(str)
    _freshness_done = Signal(str)  # marshals worker results to the UI thread

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.coordinator = ScanCoordinator(db_path=db_path)
        self.coordinator.progress.connect(self._on_scan_progress)
        self.coordinator.finished.connect(self._on_scan_finished)
        self._freshness_done.connect(self._on_freshness_done)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Scanner group ────────────────────────────────────────────────────
        root.addWidget(self._build_scanner_group())
        # ── Scan history group ───────────────────────────────────────────────
        root.addWidget(self._build_history_group(), stretch=1)
        # ── Data quality group ───────────────────────────────────────────────
        root.addWidget(self._build_quality_group())
        # ── Freshness check group ────────────────────────────────────────────
        root.addWidget(self._build_freshness_group())
        root.addStretch(1)

# ── Group builders ───────────────────────────────────────────────────────
    def _build_scanner_group(self):
        scanner = QGroupBox(_("Scanner"))
        lay = QVBoxLayout(scanner)
        row = QHBoxLayout()
        self.method_label = QLabel(_("Method"))
        self.method_combo = QComboBox()
        self.method_combo.addItem(_("Quick (API-first)"), "quick")
        self.method_combo.addItem(_("Full (browser crawl)"), "full")
        self.scan_btn = QPushButton(_("Scan Now"))
        self.scan_btn.setObjectName("Primary")
        self.scan_btn.clicked.connect(self.start_scan)
        self.stop_btn = QPushButton(_("Stop"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.coordinator.stop)
        self.scan_status = QLabel(_("Idle"))
        for w in (self.method_label, self.method_combo, self.scan_btn,
                  self.stop_btn, self.scan_status):
            row.addWidget(w)
        row.addStretch(1)
        lay.addLayout(row)
        self.scan_log = QPlainTextEdit()
        self.scan_log.setReadOnly(True)
        self.scan_log.setMaximumHeight(180)
        self.scan_log.setPlaceholderText(_("Scan output appears here…"))
        lay.addWidget(self.scan_log)
        return scanner

    def _build_history_group(self):
        box = QGroupBox(_("Scan History"))
        lay = QVBoxLayout(box)
        self.runs_table = QTableWidget(0, len(HEADERS_RUNS))
        self.runs_table.setHorizontalHeaderLabels(HEADERS_RUNS)
        self.runs_table.verticalHeader().setVisible(False)
        self.runs_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.runs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.runs_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.runs_table.setAlternatingRowColors(True)
        self.runs_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        lay.addWidget(self.runs_table)
        row = QHBoxLayout()
        self.view_log_btn = QPushButton(_("View Per-Company Log"))
        self.view_log_btn.clicked.connect(self._view_run_log)
        row.addWidget(self.view_log_btn)
        row.addStretch(1)
        lay.addLayout(row)
        return box

    def _build_quality_group(self):
        box = QGroupBox(_("Data Quality"))
        lay = QHBoxLayout(box)
        self.dedup_btn = QPushButton(_("Run Dedup"))
        self.dedup_btn.clicked.connect(self._run_dedup)
        self.stale_btn = QPushButton(_("Clear Stale Data"))
        self.stale_btn.clicked.connect(self._clear_stale_data)
        lay.addWidget(self.dedup_btn)
        lay.addWidget(self.stale_btn)
        lay.addStretch(1)
        return box

    def _build_freshness_group(self):
        box = QGroupBox(_("Freshness Check"))
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel(_("Check up to")))
        self.verify_n = QSpinBox()
        self.verify_n.setRange(5, 200)
        self.verify_n.setValue(25)
        self.verify_n.setToolTip(
            _("Maximum number of active jobs to re-verify per run."))
        lay.addWidget(self.verify_n)
        lay.addWidget(QLabel(_("jobs")))
        self.fresh_btn = QPushButton(_("Run"))
        self.fresh_btn.clicked.connect(self._run_freshness)
        lay.addWidget(self.fresh_btn)
        self.fresh_status = QLabel(_("Idle"))
        lay.addWidget(self.fresh_status)
        lay.addStretch(1)
        return box

# ── Scanner control ──────────────────────────────────────────────────────
    def start_scan(self):
        if self.coordinator.is_running():
            QMessageBox.information(self, _("SponsorScout"),
                                    _("A scan is already running."))
            return
        method = self.method_combo.currentData()
        self.scan_log.clear()
        self.scan_status.setText(_("Running…"))
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_message.emit(_("Scan started"))
        self.coordinator.start(method)

    def _on_scan_progress(self, line: str):
        self.scan_log.appendPlainText(line)

    def _on_scan_finished(self, summary: dict):
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        status = summary.get("status", "error")
        if summary.get("cancelled"):
            status = "cancelled"
        self.scan_status.setText(status)
        for err in summary.get("errors") or []:
            self.scan_log.appendPlainText(f"ERROR: {err}")
        self.scan_log.appendPlainText(
            f"--- {status}: ingested={summary.get('ingested', 0)}, "
            f"duplicates={summary.get('duplicates', 0)}, "
            f"quarantined={summary.get('quarantined', 0)} ---")
        self.refresh()
        self.data_changed.emit()
        self.scan_finished.emit(summary)
        self.status_message.emit(_("Scan finished: ") + status)

    def _view_run_log(self):
        row = self.runs_table.currentRow()
        if row < 0:
            QMessageBox.information(self, _("SponsorScout"),
                                    _("Select a scan run first."))
            return
        run_id = self.runs_table.item(row, 0).text()
        ScanLogDialog(self.db_path, run_id, self).exec()

    def refresh(self):
        rows = db.list_scan_runs(self.db_path, limit=25)
        self.runs_table.setRowCount(0)
        for r in rows:
            (run_id, method, started, _fin, status, _err, _ok, _empty,
             n_err, jobs, quarantined, dups, _ats, _career) = r[:14]
            row_idx = self.runs_table.rowCount()
            self.runs_table.insertRow(row_idx)
            values = (run_id, method, (started or "")[:19], status,
                      jobs, dups, quarantined, n_err)
            for col, val in enumerate(values):
                self.runs_table.setItem(
                    row_idx, col, QTableWidgetItem(str(val if val is not None else "")))

    # ── Data-quality actions (ported from the original Tools tab) ───────────
    def _run_dedup(self):
        try:
            conn = db.get_connection(self.db_path)
            try:
                jd = dedup_jobs_in_db(conn)
                cd = dedup_companies_in_db(conn)
            finally:
                conn.close()
            QMessageBox.information(
                self, _("Dedup complete"),
                _("Removed {jobs} duplicate job(s) and {companies} duplicate "
                  "company entry(ies).").format(jobs=jd, companies=cd))
            self.data_changed.emit()
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), str(exc))

    def _clear_stale_data(self):
        try:
            conn = db.get_connection(self.db_path)
            try:
                cur = conn.execute("DELETE FROM jobs WHERE is_expired=1")
                deleted = cur.rowcount
                conn.execute("VACUUM")
            finally:
                conn.close()
            QMessageBox.information(
                self, _("Stale data cleared"),
                _("Removed {n} expired job(s) from the "
                  "database.").format(n=deleted))
            self.data_changed.emit()
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), str(exc))

    # ── Freshness verification (worker thread + signal marshalling) ────────
    def _run_freshness(self):
        n = self.verify_n.value()
        self.status_message.emit(_("Verifying up to {n} jobs…").format(n=n))
        self.fresh_status.setText(_("Running…"))
        self.fresh_btn.setEnabled(False)
        threading.Thread(target=self._freshness_worker,
                         args=(n,), daemon=True).start()

    def _freshness_worker(self, n: int):
        """Background thread; results marshalled via _freshness_done."""
        try:
            from sponsorscout.core.persistence import upsert_job
            from sponsorscout.core.verification_service import verify_job
            conn = db.get_connection(self.db_path)
            try:
                rows = conn.execute("""
                    SELECT url FROM jobs
                    WHERE verified_active=1 AND is_expired=0
                      AND (last_verified_at IS NULL OR
                           last_verified_at < datetime('now','-7 days'))
                    ORDER BY last_verified_at ASC LIMIT ?""",
                    (n,)).fetchall()
                expired = checked = 0
                for row in rows:
                    jr = conn.execute(
                        "SELECT * FROM jobs WHERE url=?",
                        (row["url"],)).fetchone()
                    if not jr:
                        continue
                    result = verify_job(dict(jr))
                    upsert_job(conn, result)
                    if result.get("is_expired"):
                        expired += 1
                    checked += 1
            finally:
                conn.close()
            self._freshness_done.emit(
                _("Checked {checked} — expired {expired}.").format(
                    checked=checked, expired=expired))
        except Exception as exc:
            self._freshness_done.emit(f"{_('Error')}: {exc}")

    def _on_freshness_done(self, msg: str):
        self.fresh_status.setText(msg)
        self.fresh_btn.setEnabled(True)
        self.status_message.emit(_("Freshness check done."))
        self.data_changed.emit()