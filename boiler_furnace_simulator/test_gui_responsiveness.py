"""Regression checks for the PyQtGraph migration and demo navigation."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from pyqtgraph import PlotWidget

from boiler_furnace_simulator import BoilerApp, SliderRow
from suite_main import SuiteBoilerApp


class BoilerGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = BoilerApp()

    def tearDown(self):
        self.window.timer.stop()
        self.window.close()

    def test_live_trends_use_pyqtgraph(self):
        self.assertTrue(all(isinstance(plot, PlotWidget) for plot in self.window.trend_plots))

    def test_all_demo_types_preserve_selected_tab(self):
        self.window.tabs.setCurrentIndex(5)
        for index in range(self.window.demo_popup.count()):
            self.window.demo_popup.setCurrentIndex(index)
            self.window.start_demo_cb()
            self.window.apply_demo_stage(self.window.demo_sequence[0][0])
            self.assertEqual(self.window.tabs.currentIndex(), 5)
            self.window.stop_demo_cb()

    def test_feedwater_command_is_mass_flow(self):
        labels = [
            label.text() for label in self.window.steam_box.findChildren(type(self.window.status))
        ]
        self.assertTrue(any("Feedwater mass-flow rate" in label for label in labels))
        self.window.interface_popup.setCurrentIndex(0)
        self.assertFalse(self.window.rows['fwcmd'].isHidden())

    def test_energy_tab_contains_sankey_and_bar_chart(self):
        self.assertIsNotNone(self.window.sankey_diagram)
        self.assertIsNotNone(self.window.energy_plot)

    def test_suite_variant_uses_slider_rows(self):
        suite_window = SuiteBoilerApp()
        try:
            self.assertIsInstance(suite_window.rows['fwcmd'], SliderRow)
        finally:
            suite_window.timer.stop()
            suite_window.close()

    def test_stop_demo_pauses_run(self):
        self.window.start_demo_cb()
        self.window.stop_demo_cb()
        self.assertFalse(self.window.running)
        self.assertFalse(self.window.timer.isActive())


if __name__ == "__main__":
    unittest.main()
