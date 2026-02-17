"""Semantic color constants and stylesheet helpers."""

# ── Semantic colors ────────────────────────────────────────────────────
PROFIT_COLOR  = "#009600"
LOSS_COLOR    = "#C80000"
WARNING_COLOR = "#E68A00"
NEUTRAL_COLOR = "#333333"
BG_COLOR      = "#F5F5F5"
HEADER_BG     = "#E0E0E0"
CARD_BG       = "#FFFFFF"
BORDER_COLOR  = "#CCCCCC"

# ── Stylesheet ─────────────────────────────────────────────────────────

GLOBAL_STYLESHEET = """
QMainWindow {
    background-color: #F5F5F5;
}

QWidget#sidebar {
    background-color: #2B2B2B;
    min-width: 200px;
    max-width: 200px;
}

QListWidget#navList {
    background-color: #2B2B2B;
    color: #FFFFFF;
    border: none;
    font-size: 13px;
    padding: 5px;
}

QListWidget#navList::item {
    padding: 10px 15px;
    border-radius: 4px;
    margin: 2px 5px;
}

QListWidget#navList::item:selected {
    background-color: #0078D4;
    color: white;
}

QListWidget#navList::item:hover:!selected {
    background-color: #3C3C3C;
}

QGroupBox {
    font-weight: bold;
    border: 1px solid #CCCCCC;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 18px;
    background-color: #FFFFFF;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

QTableView {
    gridline-color: #E0E0E0;
    selection-background-color: #CCE5FF;
    selection-color: #000000;
    alternate-background-color: #F9F9F9;
    font-size: 12px;
}

QTableView QHeaderView::section {
    background-color: #E0E0E0;
    padding: 5px;
    border: 1px solid #CCCCCC;
    font-weight: bold;
    font-size: 12px;
}

QPushButton {
    padding: 6px 16px;
    border: 1px solid #ADADAD;
    border-radius: 3px;
    background-color: #E1E1E1;
    font-size: 12px;
    min-height: 22px;
}

QPushButton:hover {
    background-color: #D0D0D0;
    border-color: #0078D4;
}

QPushButton:pressed {
    background-color: #C0C0C0;
}

QPushButton#primaryBtn {
    background-color: #0078D4;
    color: white;
    border-color: #005A9E;
}

QPushButton#primaryBtn:hover {
    background-color: #006CBE;
}

QPushButton#dangerBtn {
    background-color: #C80000;
    color: white;
    border-color: #A00000;
}

QStatusBar {
    font-size: 11px;
    color: #666666;
}

QLabel#cardTitle {
    font-size: 11px;
    color: #666666;
    font-weight: normal;
}

QLabel#cardValue {
    font-size: 22px;
    font-weight: bold;
}

QLabel#profitLabel {
    color: #009600;
    font-weight: bold;
}

QLabel#lossLabel {
    color: #C80000;
    font-weight: bold;
}
"""


def profit_loss_color(value: float) -> str:
    """Return hex color based on positive/negative value."""
    if value > 0:
        return PROFIT_COLOR
    elif value < 0:
        return LOSS_COLOR
    return NEUTRAL_COLOR
