"""Application look & feel for the PySide6 UI.

Ports the original tkinter palette so the Qt app stays visually faithful
to the previous UI concept (dark navy header, light body, white cards,
blue accent) while letting QSS do the heavy lifting.
"""

HEADER_BG = "#1d2d44"
HEADER_FG = "#ffffff"
ACCENT = "#3a7bd5"
ACCENT_DARK = "#2f65ad"
BODY_BG = "#f0f2f5"
CARD_BG = "#ffffff"
TEXT_MAIN = "#2c3e50"
TEXT_MUTED = "#7f8c9b"
BORDER = "#d9dee5"
OK_GREEN = "#27ae60"
WARN_AMBER = "#f39c12"
BAD_RED = "#c0392b"

FONT_FAMILY = "Helvetica"  # matches the tkinter original


def build_qss() -> str:
    """Global stylesheet applied to the QApplication."""
    return f"""
QMainWindow, QWidget#AppBody {{ background-color: {BODY_BG}; }}
QFrame#Header {{ background-color: {HEADER_BG}; }}
QFrame#Header QLabel {{ color: {HEADER_FG}; }}
QFrame#Header QLabel#AppSubtitle {{ color: #b8c4d4; font-size: 11px; }}
QFrame#Header QLabel#AppTitle {{ font-size: 20px; font-weight: bold; }}
QLabel#StatusLabel {{ color: {TEXT_MUTED}; font-size: 11px; }}

QFrame#Card {{ background-color: {CARD_BG}; border: 1px solid {BORDER};
               border-radius: 6px; }}
QLabel#CardTitle {{ color: {TEXT_MUTED}; font-size: 11px; font-weight: bold; }}
QLabel#CardValue {{ color: {TEXT_MAIN}; font-size: 22px; font-weight: bold; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; background: {CARD_BG};
                    border-radius: 4px; }}
QTabBar::tab {{ background: #e6e9ee; color: {TEXT_MUTED}; padding: 8px 18px;
                margin-right: 2px; border: 1px solid {BORDER};
                border-bottom: none; border-top-left-radius: 4px;
                border-top-right-radius: 4px; font-weight: bold; }}
QTabBar::tab:selected {{ background: {CARD_BG}; color: {ACCENT}; }}
QTabBar::tab:hover {{ background: #dde3ea; }}

QPushButton {{ background-color: {CARD_BG}; color: {TEXT_MAIN};
               border: 1px solid {BORDER}; border-radius: 4px;
               padding: 6px 14px; font-weight: bold; }}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:disabled {{ color: #b0b7bf; border-color: {BORDER}; }}
QPushButton#Primary {{ background-color: {ACCENT}; color: white;
                       border: 1px solid {ACCENT_DARK}; }}
QPushButton#Primary:hover {{ background-color: {ACCENT_DARK}; }}
QPushButton#Danger {{ color: {BAD_RED}; }}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QDoubleSpinBox {{
    background-color: white; border: 1px solid {BORDER}; border-radius: 4px;
    padding: 4px 6px; color: {TEXT_MAIN}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: white;
    selection-background-color: {ACCENT}; }}

QTableWidget {{ background-color: {CARD_BG}; alternate-background-color: #f7f9fb;
                gridline-color: {BORDER}; color: {TEXT_MAIN};
                border: 1px solid {BORDER}; border-radius: 4px; }}
QTableWidget::item:selected {{ background-color: {ACCENT}; color: white; }}
QHeaderView::section {{ background-color: #eef1f5; color: {TEXT_MUTED};
    border: none; border-bottom: 1px solid {BORDER}; border-right: 1px solid {BORDER};
    padding: 6px; font-weight: bold; }}

QCheckBox {{ color: {TEXT_MAIN}; }}
QScrollBar:vertical {{ background: #f0f2f5; width: 11px; }}
QScrollBar::handle:vertical {{ background: #c3ccd6; border-radius: 5px;
                               min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar:horizontal {{ background: #f0f2f5; height: 11px; }}
QScrollBar::handle:horizontal {{ background: #c3ccd6; border-radius: 5px;
                                 min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}

QDialog {{ background-color: {BODY_BG}; }}
QLabel#FormError {{ color: {BAD_RED}; font-size: 11px; }}
QLabel#SectionHeader {{ color: {HEADER_BG}; font-size: 13px; font-weight: bold; }}
"""
