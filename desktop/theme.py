CHART_GRID = "#dce6e8"
CHART_LABEL = "#4e626c"
CPU_LINE = "#247a72"
MEMORY_LINE = "#636dab"

WINDOW_STYLE = """
QMainWindow, QWidget#dashboard, QTabWidget, QDialog { background: #f3f6f7; }
QWidget { color: #20343d; font-size: 13px; }
QTabWidget::pane { border: 0; background: #f3f6f7; }
QTabWidget::tab-bar { alignment: left; left: 23px; top: 9px; }
QTabBar { background: #f3f6f7; }
QTabBar::tab {
    background: transparent;
    color: #4e626c;
    padding: 9px 13px;
    margin: 2px 3px 11px 0;
    border: 1px solid transparent;
    border-radius: 9px;
    font-weight: 600;
}
QTabBar::tab:hover { background: #e9efef; }
QTabBar::tab:selected { color: #1f5d55; background: #dfede9; border-color: #d3e4df; }
QTabBar::tab:focus { border-color: #4c867f; }
QPushButton {
    background: #ffffff;
    border: 1px solid #cad8da;
    border-radius: 8px;
    padding: 6px 11px;
}
QPushButton:hover { background: #eaf3f0; border-color: #a8c8c2; }
QPushButton:pressed { background: #dcece8; }
QPushButton:disabled { background: #edf1f2; color: #657680; border-color: #dae3e5; }
QLineEdit, QDateEdit, QSpinBox, QComboBox {
    background: #ffffff;
    border: 1px solid #cad8da;
    border-radius: 8px;
    padding: 5px 8px;
    min-height: 21px;
    selection-background-color: #286d64;
    selection-color: #ffffff;
}
QLineEdit:disabled, QDateEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    background: #edf1f2;
    color: #657680;
    border-color: #dae3e5;
}
QPushButton:focus, QLineEdit:focus, QDateEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #4c867f;
}
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f4f8f8;
    gridline-color: #e2e9eb;
    border: 1px solid #d5e0e2;
    border-radius: 8px;
    selection-background-color: #dcece8;
    selection-color: #213d36;
}
QHeaderView::section {
    background: #eaf0f2;
    color: #354e59;
    padding: 7px 8px;
    border: 0;
    border-bottom: 1px solid #d5e0e2;
    font-weight: 600;
}
QCalendarWidget QWidget { background: #ffffff; }
QCalendarWidget QAbstractItemView, QComboBox QAbstractItemView {
    background: #ffffff;
    selection-background-color: #dcece8;
    selection-color: #213d36;
}
QLabel#heading { font-size: 30px; font-weight: 700; }
QLabel#cardTitle { font-size: 15px; font-weight: 650; }
QLabel#metric { font-size: 34px; font-weight: 700; }
QLabel#diskMetric { font-size: 26px; font-weight: 700; }
QLabel[role="details"], QLabel#status, QStatusBar { color: #4e626c; }
QFrame[role="card"] {
    background: #ffffff;
    border: 1px solid #d9e3e5;
    border-radius: 14px;
}
QProgressBar { background: #e6eeed; border: 0; border-radius: 4px; }
QProgressBar::chunk { background: #4a8c81; border-radius: 4px; }
QFrame#alertCard {
    background: #fffcf6;
    border: 1px solid #d7bb85;
    border-radius: 13px;
}
QLabel#alertTitle { color: #573c1d; font-size: 16px; font-weight: 700; }
QLabel#alertReading { color: #5e4b31; }
QPushButton#alertHistory { background: #f6e9d1; border-color: #e4cea6; color: #553b1c; }
QPushButton#alertHistory:hover { background: #f0dfbd; }
QPushButton#alertClose { background: transparent; border-color: transparent; font-size: 18px; padding: 0 6px; }
QPushButton#alertClose:hover { background: #f6e9d1; }
QPushButton#alertClose:focus, QPushButton#alertHistory:focus { border-color: #967440; }
"""
