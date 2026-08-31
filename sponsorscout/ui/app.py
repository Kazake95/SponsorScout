"""SponsorScout main window (PySide6 restart).

Replaces the Tkinter-era monolith.  Each tab is an independent QWidget in
``sponsorscout.ui.tabs``; this file only builds the header, assembles the
5 tabs, and relays cross-tab signals (status bar, language switching,
data refreshed, scan requested) between them.
"""

from __future__ import annotations

import logging

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from sponsorscout.db import database as db
from sponsorscout.i18n import (
    _, get_available_locales, get_locale, get_locale_name, load_saved_locale,
    set_locale,
)
from sponsorscout.paths import DB_PATH
from sponsorscout.ui.style import build_qss
from sponsorscout.ui.tabs import (
    ApplicationsTab, DashboardTab, DataManagementTab, SearchTab, ToolsTab,
)

logger = logging.getLogger(__name__)


class SponsorScoutApp(QMainWindow):
    """Main window: navy header + 5-tab workspace (Dashboard / Search /
    Applications / Tools / Data Management)."""

    def __init__(self, db_path: str | None = None):
        super().__init__()
        load_saved_locale()
        self.db_path = db_path or str(DB_PATH)
        db.initialize(self.db_path)

        self.setWindowTitle(_("SponsorScout"))
        self.resize(1380, 840)
        self._logo_pixmap = None

        root = QWidget()
        root.setObjectName("AppBody")
        self.setCentralWidget(root)
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        root_lay.addWidget(self._build_header())
        root_lay.addWidget(self._build_tabs(), 1)

        self.setStyleSheet(build_qss())
        self._load_icon()

        # Initial data load
        self._refresh_all()
        QTimer.singleShot(500, self._check_first_run)

    # ── Header ──────────────────────────────────────────────────────────────
    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(10)

        self.logo_label = QLabel()
        self.logo_label.setFixedSize(28, 28)
        lay.addWidget(self.logo_label)

        title = QLabel(_("SponsorScout"))
        title.setObjectName("AppTitle")
        lay.addWidget(title)

        subtitle = QLabel(
            _("Verified sponsorship-focused jobs from official career pages "
              "and ATS boards"))
        subtitle.setObjectName("AppSubtitle")
        lay.addWidget(subtitle)

        lay.addStretch(1)

        # Language selector
        self.lang_combo = QComboBox()
        for code in get_available_locales():
            self.lang_combo.addItem(get_locale_name(code), code)
        idx = self.lang_combo.findData(get_locale())
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self._on_language_change)
        lay.addWidget(self.lang_combo)

        # Status label (right-aligned)
        self.status_label = QLabel(_("Ready"))
        self.status_label.setObjectName("StatusLabel")
        lay.addWidget(self.status_label)

        return header

    def _load_icon(self):
        icon_dir = Path(__file__).resolve().parent.parent / "data" / "icons"
        png = icon_dir / "sponsorscout_256.png"
        try:
            if png.exists():
                pix = QPixmap(str(png))
                if not pix.isNull():
                    self.logo_label.setPixmap(
                        pix.scaled(28, 28, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation))
                    self.setWindowIcon(QIcon(str(png)))
        except Exception as exc:  # noqa: BLE001 - icon is cosmetic
            logger.debug("Failed to load icon: %s", exc)

    # ── Tabs ────────────────────────────────────────────────────────────────
    def _build_tabs(self) -> QWidget:
        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        self.dashboard_tab = DashboardTab(self.db_path)
        self.search_tab = SearchTab(self.db_path)
        self.applications_tab = ApplicationsTab(self.db_path)
        self.tools_tab = ToolsTab(self.db_path)
        self.data_tab = DataManagementTab()

        tabs.addTab(self.dashboard_tab, _("Dashboard"))
        tabs.addTab(self.search_tab, _("Search"))
        tabs.addTab(self.applications_tab, _("Applications"))
        tabs.addTab(self.tools_tab, _("Tools"))
        tabs.addTab(self.data_tab, _("Data Management"))
        self.tabs = tabs

        # ── Cross-tab wiring ─────────────────────────────────────────────────
        self.dashboard_tab.refresh_requested.connect(self._refresh_all)
        self.dashboard_tab.rescan_requested.connect(self._rescan_from_dashboard)

        self.search_tab.application_saved.connect(
            lambda _url: self.applications_tab.load_applications())

        self.tools_tab.data_changed.connect(self._refresh_all)
        self.tools_tab.scan_finished.connect(self._on_scan_finished)
        self.tools_tab.status_message.connect(self._set_status)

        self.applications_tab.data_changed.connect(
            lambda: self.dashboard_tab.refresh())
        self.applications_tab.status_message.connect(self._set_status)

        self.data_tab.seeds_changed.connect(lambda: self._set_status(
            _("Seed files changed — they will be used on the next scan.")))

        return tabs

    # ── Actions ─────────────────────────────────────────────────────────────
    def _refresh_all(self):
        self.dashboard_tab.refresh()
        self.search_tab.populate_static_filters()
        self.search_tab.run_search()
        self.applications_tab.load_applications()
        self.tools_tab.refresh()

    def _on_scan_finished(self, summary: dict):
        status = summary.get("status", "error")
        if summary.get("cancelled"):
            self._set_status(_("Scan stopped."))
        else:
            self._set_status(
                _("Scan complete.") + "  " +
                _("{n} jobs ingested").format(n=summary.get("ingested", 0)))

    def _rescan_from_dashboard(self):
        """Dashboard 'Rescan Companies' → Tools quick scan."""
        self.tabs.setCurrentWidget(self.tools_tab)
        self.tools_tab.method_combo.setCurrentIndex(0)  # quick
        self.tools_tab.start_scan()

    def _set_status(self, msg: str):
        self.status_label.setText(msg)

    # ── Language switching ──────────────────────────────────────────────────
    def _on_language_change(self):
        code = self.lang_combo.currentData()
        if code and code != get_locale():
            set_locale(code)
            self.retranslate()
            self._set_status(_("Language: ") + get_locale_name(code))

    def retranslate(self):
        self.setWindowTitle(_("SponsorScout"))
        self.tabs.setTabText(0, _("Dashboard"))
        self.tabs.setTabText(1, _("Search"))
        self.tabs.setTabText(2, _("Applications"))
        self.tabs.setTabText(3, _("Tools"))
        self.tabs.setTabText(4, _("Data Management"))
        for tab in (self.dashboard_tab, self.search_tab):
            retranslate = getattr(tab, "retranslate", None)
            if callable(retranslate):
                retranslate()

    # ── First-run ───────────────────────────────────────────────────────────
    def _check_first_run(self):
        try:
            stats = db.get_dashboard_stats(self.db_path)
            if stats.get("companies", 0) == 0 and stats.get("verified_jobs", 0) == 0:
                answer = QMessageBox.question(
                    self, _("Welcome to SponsorScout"),
                    _("No data yet.\n\nRun the first scan now? It fetches jobs "
                      "from each company's official career page and ATS board "
                      "(1–3 minutes)."),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if answer == QMessageBox.Yes:
                    self._rescan_from_dashboard()
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to determine whether this is the first run: %s", exc)