"""Open Nuclear Suite-style launcher for the boiler simulator."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel

from boiler_furnace_simulator import BoilerApp, StartupSplash
from suite_theme import apply_suite_theme


class SuiteBoilerApp(BoilerApp):
    """Boiler model presented with sliders and nuclear-suite dark styling."""

    suite_style = True

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Boiler/Furnace Transient Simulator — Open Nuclear Suite style')
        self._normalize_suite_styles()

    def simulate_one_step(self):
        super().simulate_one_step()
        self._normalize_suite_styles()

    def _normalize_suite_styles(self):
        """Remove light-only inline fills so the shared dark theme can render."""
        light_fills = ('background:white', 'background:#d', 'background:#e', 'background:#f')
        for label in self.findChildren(QLabel):
            compact = label.styleSheet().replace(' ', '').lower()
            if any(fill in compact for fill in light_fills):
                label.setObjectName('statusPanel')
                label.setStyleSheet('')


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    apply_suite_theme(app)
    window = SuiteBoilerApp()
    splash = StartupSplash()
    splash.show()

    def reveal():
        splash.close()
        window.show()
        window.raise_()

    QTimer.singleShot(1200, reveal)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
