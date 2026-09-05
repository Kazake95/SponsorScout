"""SponsorScout — verified visa-sponsorship job discovery.

Entry point for the desktop GUI. Bootstraps localization, applies database
schema migrations, then launches the PySide6 main window and its event loop.

Runtime data lives in the per-user application data directory
(%APPDATA%\\SponsorScout on Windows, ~/.sponsorscout elsewhere).  Override
with the ``SPONSORSCOUT_DATA_DIR`` or ``SPONSORSCOUT_DB_PATH`` environment
variables if needed.
"""

import logging
import sys
from pathlib import Path

# Ensure the project root is importable when this file is executed directly
# (e.g. ``python3 sponsorscout/main.py``), since Python only adds the script's
# own directory to sys.path in that case — not the parent that contains the
# ``sponsorscout`` package.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from sponsorscout.i18n import load_saved_locale  # noqa: E402
from sponsorscout.ui.style import build_light_palette, build_qss  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    """Bootstrap and launch SponsorScout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("SponsorScout starting up")

    # Load the persisted language preference before building the UI so every
    # widget labels itself in the correct locale from the first frame.
    load_saved_locale()

    app = QApplication(sys.argv or ["sponsorscout"])
    # Fusion renders the QSS paddings/borders predictably across Windows
    # styles (and avoids the combo/spinbox text-overlap artifacts), while
    # the explicit light palette keeps every label legible even when the
    # OS is in dark mode — Qt >= 6.5 would otherwise inject the system
    # dark palette into this light-only stylesheet.
    app.setStyle("Fusion")
    app.setPalette(build_light_palette())
    app.setStyleSheet(build_qss())
    app.setApplicationName("SponsorScout")

    from sponsorscout.ui.app import SponsorScoutApp  # deferred: needs QApplication

    window = SponsorScoutApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()