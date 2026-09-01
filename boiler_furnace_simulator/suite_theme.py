"""Open Nuclear Suite-compatible engineering-console theme."""

from PySide6 import QtGui, QtWidgets


SUITE_STYLESHEET = """
QWidget { background-color:#0b1117; color:#f2f6fa; font-family:"Segoe UI"; font-size:10pt; }
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget { background-color:#0b1117; }
QLabel#statusPanel { background-color:#101820; border:1px solid #435461;
  border-radius:4px; padding:8px; color:#f2f6fa; }
QPushButton { background-color:#205b7d; color:#fff; border:1px solid #3c86ae;
  border-radius:4px; min-height:27px; padding:4px 12px; }
QPushButton:hover { background-color:#2b7299; border-color:#62c7ff; }
QPushButton:pressed { background-color:#17445f; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background-color:#17232d; color:#fff;
  border:1px solid #526675; border-radius:3px; min-height:25px; padding:2px 6px; }
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover { border-color:#55c7ff; }
QSlider::groove:horizontal { height:6px; background:#263743; border:1px solid #526675; border-radius:3px; }
QSlider::sub-page:horizontal { background:#277cad; border-radius:3px; }
QSlider::handle:horizontal { background:#f2f6fa; border:2px solid #55c7ff;
  width:16px; margin:-6px 0; border-radius:8px; }
QSlider::handle:horizontal:hover { background:#ffffff; border-color:#8edcff; }
QComboBox QAbstractItemView { background-color:#17232d; color:#fff; selection-background-color:#277cad; }
QTableWidget { background-color:#0d151c; alternate-background-color:#15232d; color:#f2f6fa;
  gridline-color:#435461; border:1px solid #435461; selection-background-color:#205b7d; }
QHeaderView::section { background-color:#111c25; color:#fff; border:0;
  border-right:1px solid #435461; border-bottom:1px solid #435461; padding:5px; }
QScrollBar:vertical { background:#101820; width:14px; }
QScrollBar::handle:vertical { background:#526675; min-height:28px; border-radius:5px; }
QSplitter::handle { background-color:#3d4d59; }
QGroupBox { border:1px solid #435461; border-radius:5px; margin-top:11px;
  padding-top:8px; font-weight:700; color:#55c7ff; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; background-color:#0b1117; }
QTabWidget::pane { border:1px solid #435461; background:#0f171e; }
QTabBar::tab { background:#17232d; color:#dce7ee; border:1px solid #435461; padding:7px 12px; }
QTabBar::tab:selected { background:#205b7d; color:#fff; }
QToolTip { background-color:#17232d; color:#fff; border:1px solid #55c7ff; padding:5px; }
"""


def apply_suite_theme(application: QtWidgets.QApplication) -> None:
    application.setStyle("Fusion")
    application.setFont(QtGui.QFont("Segoe UI", 10))
    application.setStyleSheet(SUITE_STYLESHEET)
