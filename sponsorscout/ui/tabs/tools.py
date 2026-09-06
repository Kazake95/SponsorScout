"""Tools tab: scanner control, scan history, data quality, freshness checks.

Ported from the tkinter Tools tab (scan control + streaming log, dedup,
stale-data cleanup, freshness verification) with the addition of the
per-run scan history view backed by the scan_runs / scan_log tables.
"""

import threading

from PySide6.QtCore import QStandardPaths, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from sponsorscout.application.scan_coordinator import ScanCoordinator
from sponsorscout.core.dedup import dedup_companies_in_db, dedup_jobs_in_db
from sponsorscout.db import database as db
from sponsorscout.i18n import _

HEADERS_RUNS = ["Run ID", "Method", "Started", "Status", "Jobs", "Dups",
                "Quarantined", "Errors"]
HEADERS_LOG = ["Seed", "Company", "Source", "Target Country", "Status",
               "Provider", "Jobs", "Quar.", "Dups", "Scope Rej.",
               "Error", "Diagnostics", "Duration (s)", "Seed URL"]


class ScanLogDialog(QDialog):
    """Per-company outcomes of one scan run (from the scan_log table)."""

    def __init__(self, db_path: str, run_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Scan log — {run_id}")
        self.resize(1280, 620)
        lay = QVBoxLayout(self)
        table = QTableWidget(0, len(HEADERS_LOG))
        table.setHorizontalHeaderLabels(HEADERS_LOG)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        tooltip_cols = {10, 11}  # Error / Diagnostics are long free-text cols
        for row in db.get_scan_log(db_path, run_id):
            r = table.rowCount()
            table.insertRow(r)
            for col, val in enumerate(row):
                text = str(val or "")
                item = QTableWidgetItem(text)
                if col in tooltip_cols and text:
                    item.setToolTip(text)
                table.setItem(r, col, item)
        table.resizeColumnsToContents()
        # Ensure very wide diagnostic columns don't dominate the window.
        extra = {2, 3, 13}  # Source / Target Country / Seed URL
        for col in list(range(len(HEADERS_LOG))):
            if header.sectionSize(col) > 420:
                header.resizeSection(col, 420)
            elif col not in extra and header.sectionSize(col) < 90:
                header.resizeSection(col, 90)
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
        row.setSpacing(8)
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
        self.download_log_btn = QPushButton(_("Download Scan Log"))
        self.download_log_btn.clicked.connect(self._export_run_log)
        row.addWidget(self.download_log_btn)
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
        self.clear_scan_btn = QPushButton(_("Clear Scan Data"))
        self.clear_scan_btn.clicked.connect(self._clear_scan_data)
        lay.addWidget(self.dedup_btn)
        lay.addWidget(self.stale_btn)
        lay.addWidget(self.clear_scan_btn)
        lay.addStretch(1)
        return box

    def _build_freshness_group(self):
        box = QGroupBox(_("Freshness Check"))
        lay = QHBoxLayout(box)
        lay.setSpacing(8)
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

    def _export_run_log(self):
        """Download the selected run's full scan analysis (summary + per-company
        log + event timeline) as a CSV file."""
        row = self.runs_table.currentRow()
        if row < 0:
            QMessageBox.information(self, _("SponsorScout"),
                                    _("Select a scan run first."))
            return
        run_id = self.runs_table.item(row, 0).text()
        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        default_path = (docs or ".")
        default_path += f"/sponsorscout_scan_log_{run_id}.csv"
        path, _filt = QFileDialog.getSaveFileName(
            self, _("Download Scan Log"), default_path,
            _("CSV files (*.csv);;All files (*.*)"))
        if not path:
            return
        try:
            content = db.export_scan_run_csv(self.db_path, run_id)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(content)
        except Exception as exc:
            QMessageBox.critical(self, _("Error"),
                                 _("Could not save scan log:\n{error}")
                                 .format(error=str(exc)))
            return
        # Verify and report what the file actually contains.
        from pathlib import Path
        p = Path(path)
        n_log = len(db.get_scan_log(self.db_path, run_id))
        n_events = len(db.get_scan_events(self.db_path, run_id))
        if not p.is_file() or p.stat().st_size <= 0:
            QMessageBox.critical(
                self, _("Error"),
                _("The file appears empty:\n{path}").format(path=path))
            return
        answer = QMessageBox.information(
            self, _("Scan log downloaded"),
            _("Scan log ({bytes} bytes, {rows} company row(s), {events} "
              "event(s)) saved to:\n{path}")
            .format(bytes=p.stat().st_size, rows=n_log, events=n_events,
                    path=path),
            QMessageBox.Ok | QMessageBox.Open,
            QMessageBox.Ok)
        if answer == QMessageBox.Open:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

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

    def _clear_scan_data(self):
        """Wipe ALL scanned data (jobs, scan history, scan logs) from the DB.

        Seed CSVs (the source of truth) and the companies registry are never
        touched, so the user can start a completely fresh scan run.
        """
        try:
            conn = db.get_connection(self.db_path)
            try:
                jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                runs = conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
                logs = conn.execute("SELECT COUNT(*) FROM scan_log").fetchone()[0]
                if jobs == 0 and runs == 0 and logs == 0:
                    QMessageBox.information(
                        self, _("Clear Scan Data"),
                        _("The database already contains no scanned data."))
                    return
                answer = QMessageBox.question(
                    self, _("Clear Scan Data"),
                    _("This will permanently delete {jobs} scanned job(s), "
                      "{runs} scan run(s) and {logs} scan log row(s) from the "
                      "database.\nSeed CSVs and saved applications are NOT "
                      "affected. Continue?").format(
                          jobs=jobs, runs=runs, logs=logs),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer != QMessageBox.Yes:
                    return
                conn.execute("DELETE FROM jobs")
                conn.execute("DELETE FROM scan_runs")
                conn.execute("DELETE FROM scan_log")
                conn.execute("DELETE FROM scan_events")
                try:
                    conn.execute("DELETE FROM jobs_fts")
                except Exception:
                    pass  # FTS table may not exist in very old DBs
                conn.commit()
                conn.execute("VACUUM")
            finally:
                conn.close()
            QMessageBox.information(
                self, _("Scan data cleared"),
                _("Removed {jobs} job(s), {runs} scan run(s) and {logs} scan "
                  "log row(s). Seed CSVs were not touched.").format(
                      jobs=jobs, runs=runs, logs=logs))
            self.data_changed.emit()
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), str(exc))

    def _clear_stale_data(self):
        try:
            conn = db.get_connection(self.db_path)
            try:
                cur = conn.execute("DELETE FROM jobs WHERE is_expired=1")
                deleted = cur.rowcount
                # Commit BEFORE VACUUM: Python's sqlite3 auto-starts a
                # transaction on the DELETE, and VACUUM cannot run inside one
                # ("cannot VACUUM from within a transaction"). Committing first
                # persists the delete and lets VACUUM run cleanly.
                conn.commit()
                if deleted > 0:
                    conn.execute("VACUUM")
            finally:
                conn.close()
            if deleted > 0:
                QMessageBox.information(
                    self, _("Stale data cleared"),
                    _("Removed {n} expired job(s) from the database.")
                    .format(n=deleted))
            else:
                QMessageBox.information(
                    self, _("Stale data cleared"),
                    _("No expired jobs to remove — the database is already "
                      "clean."))
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