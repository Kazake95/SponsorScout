"""Search tab: filter row + results table (ported from the tkinter Search tab).

Blue Card / Relocation are rendered as honest three-state values:
'Y' (confirmed), 'N' (explicitly excluded), '?' (unknown / no evidence).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QHeaderView,
    QHBoxLayout, QLineEdit, QMenu, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from sponsorscout.db import database as db
from sponsorscout.i18n import _

HEADERS = ["Title", "Company", "Country", "Location", "Sponsor",
           "Blue Card", "Reloc", "Remote", "Posted"]

URL_ROLE = Qt.UserRole + 1


def _verdict_cell(value: str) -> str:
    v = (value or "").strip().lower()
    if v == "y":
        return "Y"
    if v == "n":
        return "N"
    return "?"


class SearchTab(QWidget):
    application_saved = Signal(str)  # job url

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Filter row (same fields as the original UI) ──────────────────────
        filters = QHBoxLayout()
        filters.setSpacing(6)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(_("Job title"))
        self.company_edit = QLineEdit()
        self.company_edit.setPlaceholderText(_("Company"))
        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText(_("Location"))
        self.country_combo = QComboBox()
        self.remote_combo = QComboBox()
        self.sponsor_check = QCheckBox(_("Sponsor"))
        self.bluecard_check = QCheckBox(_("Blue Card"))
        self.reloc_check = QCheckBox(_("Reloc"))
        self.search_btn = QPushButton(_("Search"))
        self.search_btn.setObjectName("Primary")
        self.clear_btn = QPushButton(_("Clear"))

        for widget in (self.title_edit, self.company_edit, self.location_edit):
            filters.addWidget(widget)
        filters.addWidget(self.country_combo)
        filters.addWidget(self.remote_combo)
        filters.addWidget(self.sponsor_check)
        filters.addWidget(self.bluecard_check)
        filters.addWidget(self.reloc_check)
        filters.addWidget(self.search_btn)
        filters.addWidget(self.clear_btn)
        root.addLayout(filters)

        # ── Results table ────────────────────────────────────────────────────
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._open_selected)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(HEADERS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        root.addWidget(self.table, stretch=1)

        # wiring
        self.search_btn.clicked.connect(self.run_search)
        self.clear_btn.clicked.connect(self.clear_filters)
        self.title_edit.returnPressed.connect(self.run_search)
        self.company_edit.returnPressed.connect(self.run_search)
        self.location_edit.returnPressed.connect(self.run_search)

    # ── Data ─────────────────────────────────────────────────────────────────
    def populate_static_filters(self):
        """(Re)fill country / remote dropdowns from the DB."""
        for combo, values in (
            (self.country_combo, db.get_distinct_job_countries(self.db_path)),
            (self.remote_combo, db.get_distinct_remote_types(self.db_path)),
        ):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(_("All"))
            combo.addItems(values)
            if current:
                idx = combo.findText(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def run_search(self):
        rows = db.search_jobs(
            self.db_path,
            title=self.title_edit.text().strip(),
            company=self.company_edit.text().strip(),
            location=self.location_edit.text().strip(),
            country=self.country_combo.currentText(),
            remote_filter=self.remote_combo.currentText(),
            sponsorship_only=self.sponsor_check.isChecked(),
            eu_blue_card_only=self.bluecard_check.isChecked(),
            relocation_only=self.reloc_check.isChecked(),
        )
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [
                row["title"],
                row["company"],
                row["country"],
                row["location"],
                "Y" if (row["sponsorship_score"] or 0) >= 70 else "",
                _verdict_cell(row["eu_blue_card_verdict"]),
                _verdict_cell(row["relocation_support"]),
                row["remote_type"],
                (row["first_seen_at"] or "")[:10],
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val if val is not None else ""))
                item.setData(URL_ROLE, row["url"])
                if col in (4, 5, 6):
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, col, item)
        self.table.setSortingEnabled(True)

    def clear_filters(self):
        for edit in (self.title_edit, self.company_edit, self.location_edit):
            edit.clear()
        self.country_combo.setCurrentIndex(0)
        self.remote_combo.setCurrentIndex(0)
        for check in (self.sponsor_check, self.bluecard_check, self.reloc_check):
            check.setChecked(False)
        self.run_search()

    # ── Actions ──────────────────────────────────────────────────────────────
    def _selected_url(self):
        item = self.table.item(self.table.currentRow(), 0)
        return item.data(URL_ROLE) if item else None

    def _open_selected(self):
        url = self._selected_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _context_menu(self, pos):
        url = self._selected_url()
        if not url:
            return
        menu = QMenu(self)
        act_open = menu.addAction(_("Open in browser"))
        act_copy = menu.addAction(_("Copy URL"))
        act_save = menu.addAction(_("Save to Applications"))
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is act_open:
            self._open_selected()
        elif chosen is act_copy:
            QApplication.clipboard().setText(url)
        elif chosen is act_save:
            r = self.table.currentRow()
            db.upsert_application(
                self.db_path,
                job_url=url,
                company=self.table.item(r, 1).text(),
                title=self.table.item(r, 0).text(),
                status="saved",
            )
            QMessageBox.information(self, _("SponsorScout"),
                                    _("Job saved to Applications."))
            self.application_saved.emit(url)

    # ── i18n ─────────────────────────────────────────────────────────────────
    def retranslate(self):
        self.search_btn.setText(_("Search"))
        self.clear_btn.setText(_("Clear"))
        self.title_edit.setPlaceholderText(_("Job title"))
        self.company_edit.setPlaceholderText(_("Company"))
        self.location_edit.setPlaceholderText(_("Location"))
        self.sponsor_check.setText(_("Sponsor"))
        self.bluecard_check.setText(_("Blue Card"))
        self.reloc_check.setText(_("Reloc"))
        self.table.setHorizontalHeaderLabels(HEADERS)
