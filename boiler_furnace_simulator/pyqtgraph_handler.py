"""Reusable high-performance plotting helpers for the boiler simulator."""

from __future__ import annotations

import math

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets


class BoilerPlotHandler:
    """Construct and update PyQtGraph widgets without recreating plot items."""

    def __init__(self, dark: bool = False) -> None:
        self.dark = dark
        pg.setConfigOptions(
            antialias=False,
            background="#10151c" if dark else "#ffffff",
            foreground="#e6edf3" if dark else "#20252b",
        )

    def line_plot(self, title: str, x_label: str, y_label: str) -> pg.PlotWidget:
        plot = pg.PlotWidget(title=title)
        plot.setBackground("#10151c" if self.dark else "#ffffff")
        plot.setLabel("bottom", x_label)
        plot.setLabel("left", y_label)
        plot.showGrid(x=True, y=True, alpha=0.22)
        plot.addLegend(offset=(8, 8))
        plot.setMouseEnabled(x=True, y=True)
        return plot

    @staticmethod
    def add_line(plot: pg.PlotWidget, name: str, color: str, style=QtCore.Qt.SolidLine):
        return plot.plot([], [], pen=pg.mkPen(color, width=2, style=style), name=name)

    @staticmethod
    def update_line(item, x_values, y_values) -> None:
        points = [
            (x, y) for x, y in zip(x_values, y_values)
            if y is not None and not (isinstance(y, float) and math.isnan(y))
        ]
        if points:
            x, y = zip(*points)
            item.setData(x, y)
        else:
            item.setData([], [])


class EnergyBalancePlot(pg.PlotWidget):
    """Compact energy-flow view implemented entirely with PyQtGraph."""

    COLORS = ("#2f855a", "#d97706", "#718096", "#c53030", "#805ad5")

    def __init__(self, dark: bool = False) -> None:
        super().__init__(title="Boiler furnace energy balance")
        self.text_color = "#e6edf3" if dark else "#20252b"
        self.setBackground("#10151c" if dark else "#ffffff")
        self.setLabel("bottom", "Heat flow", units="kW")
        self.getAxis("left").setStyle(showValues=False)
        self.showGrid(x=True, y=False, alpha=0.2)
        self.setMouseEnabled(x=True, y=False)

    def set_balance(self, labels: list[str], values: list[float]) -> None:
        self.clear()
        y_values = list(range(len(values)))
        bars = pg.BarGraphItem(
            x0=0, y=y_values, width=values, height=0.62,
            brushes=[pg.mkBrush(color) for color in self.COLORS],
        )
        self.addItem(bars)
        for y, label, value in zip(y_values, labels, values):
            text = pg.TextItem(f"{label}  {value:.1f} kW", color=self.text_color, anchor=(0, 0.5))
            text.setPos(max(value * 0.02, 0.0), y)
            self.addItem(text)
        self.setYRange(-0.7, len(values) - 0.3, padding=0)
        self.setXRange(0, max(values + [1.0]) * 1.08, padding=0)


class SankeyDiagram(QtWidgets.QWidget):
    """Lightweight live Sankey diagram drawn with Qt rather than Matplotlib."""

    COLORS = ("#2f855a", "#d97706", "#718096", "#c53030", "#805ad5")

    def __init__(self, dark: bool = False) -> None:
        super().__init__()
        self.dark = dark
        self.labels: list[str] = []
        self.values: list[float] = []
        self.source = 0.0
        self.setMinimumHeight(310)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def set_balance(self, source: float, labels: list[str], values: list[float]) -> None:
        self.source = max(float(source), 1.0e-9)
        self.labels = list(labels)
        self.values = [max(float(value), 0.0) for value in values]
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor("#10151c" if self.dark else "#ffffff"))
        if not self.values:
            painter.setPen(QtGui.QColor("#c8d3dc" if self.dark else "#4a5568"))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Run or step to populate the Sankey diagram")
            return
        width, height = self.width(), self.height()
        foreground = QtGui.QColor("#e6edf3" if self.dark else "#20252b")
        source_x, source_width = 24.0, 132.0
        arrow_start = source_x + source_width + 22.0
        arrow_tip = max(arrow_start + 140.0, width - 225.0)
        label_x = arrow_tip + 14.0
        title_rect = QtCore.QRectF(0, 5, width, 30)
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(foreground)
        painter.drawText(title_rect, QtCore.Qt.AlignCenter, "Boiler furnace Sankey diagram")

        center_y = height * 0.56
        body_left = max(92.0, width * 0.13)
        body_right = min(width - 48.0, width * 0.91)
        x_first = body_left + 0.34 * (body_right - body_left)
        x_second = body_left + 0.64 * (body_right - body_left)
        useful = self.values[0] if self.values else 0.0
        losses = self.values[1:5] + [0.0] * max(0, 4 - len(self.values[1:5]))
        stack, wall, incomplete, moisture = losses[:4]
        total_height = min(150.0, height * 0.38)
        scale = total_height / self.source
        upper0 = center_y - total_height / 2.0
        lower0 = center_y + total_height / 2.0
        upper1 = upper0 + stack * scale
        lower1 = lower0 - wall * scale
        upper2 = upper1 + incomplete * scale
        lower2 = lower1 - moisture * scale
        final_center = (upper2 + lower2) / 2.0
        final_height = max(8.0, useful * scale)
        upper2 = final_center - final_height / 2.0
        lower2 = final_center + final_height / 2.0
        sankey_color = QtGui.QColor("#a04768")
        outline = QtGui.QColor("#202020" if not self.dark else "#e2c8d3")
        shoulder = 18.0
        output_head = min(58.0, (body_right - x_second) * 0.25)
        inlet_notch = min(72.0, (x_first - body_left) * 0.34)

        # Flow-conserving trunk: its upper and lower edges move inward after
        # each loss takeoff, leaving a final width proportional to useful heat.
        trunk = QtGui.QPainterPath()
        trunk.moveTo(body_left, upper0)
        trunk.lineTo(x_first - shoulder, upper0)
        trunk.cubicTo(x_first, upper0, x_first, upper1, x_first + shoulder, upper1)
        trunk.lineTo(x_second - shoulder, upper1)
        trunk.cubicTo(x_second, upper1, x_second, upper2, x_second + shoulder, upper2)
        trunk.lineTo(body_right - output_head, upper2)
        trunk.lineTo(body_right, final_center)
        trunk.lineTo(body_right - output_head, lower2)
        trunk.lineTo(x_second + shoulder, lower2)
        trunk.cubicTo(x_second, lower2, x_second, lower1, x_second - shoulder, lower1)
        trunk.lineTo(x_first + shoulder, lower1)
        trunk.cubicTo(x_first, lower1, x_first, lower0, x_first - shoulder, lower0)
        trunk.lineTo(body_left, lower0)
        trunk.lineTo(body_left + inlet_notch, center_y)
        trunk.closeSubpath()
        painter.setBrush(sankey_color)
        painter.setPen(QtGui.QPen(outline, 1.5))
        painter.drawPath(trunk)

        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#ffffff"))
        painter.drawText(
            QtCore.QRectF(body_left + inlet_notch + 6.0, center_y - 30.0, 145.0, 60.0),
            QtCore.Qt.AlignCenter, f"Fuel energy\n{self.source:.1f} kW",
        )
        painter.drawText(
            QtCore.QRectF(body_right - output_head - 150.0, final_center - 32.0, 145.0, 64.0),
            QtCore.Qt.AlignCenter, f"Useful boiler heat\n{useful:.1f} kW",
        )

        # Endpoints are derived from the rendered trunk, not fixed canvas
        # coordinates. This keeps arrowheads at the remote ends even when the
        # pane is short or resized.
        stack_tip = max(82.0, upper0 - 55.0)
        incomplete_tip = max(82.0, upper1 - 55.0)
        wall_tip = min(height - 48.0, lower0 + 55.0)
        moisture_tip = min(height - 48.0, lower1 + 55.0)
        branch_specs = (
            (self.labels[1], stack, x_first, upper0, -1, stack_tip),
            (self.labels[2], wall, x_first, lower0, 1, wall_tip),
            (self.labels[3], incomplete, x_second, upper1, -1, incomplete_tip),
            (self.labels[4], moisture, x_second, lower1, 1, moisture_tip),
        )
        for label, value, x, start_y, direction, tip_y in branch_specs:
            flow_width = value * scale
            painter.setPen(foreground)
            if value <= 1.0e-8:
                label_y = tip_y - 18.0 if direction < 0 else tip_y + 6.0
                painter.drawText(
                    QtCore.QRectF(x - 82.0, label_y, 164.0, 38.0),
                    QtCore.Qt.AlignCenter, f"{label}\n0.0 kW",
                )
                continue
            shown_width = max(2.0, flow_width)
            head_length = max(12.0, min(26.0, shown_width * 1.7))
            head_half_width = max(9.0, shown_width * 1.1)
            base_y = tip_y - direction * head_length
            branch = QtGui.QPainterPath()
            inside_y = start_y - direction * shown_width * 0.65
            branch.moveTo(x - shoulder, inside_y)
            branch.lineTo(x, inside_y)
            branch.cubicTo(x + shoulder, inside_y, x + shoulder, start_y + direction * 24.0, x + shoulder, start_y + direction * 40.0)
            branch.lineTo(x + shoulder, base_y)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(sankey_color, shown_width, QtCore.Qt.SolidLine, QtCore.Qt.FlatCap))
            painter.drawPath(branch)
            arrow_x = x + shoulder
            arrow = QtGui.QPolygonF([
                QtCore.QPointF(arrow_x, tip_y),
                QtCore.QPointF(arrow_x - head_half_width, base_y),
                QtCore.QPointF(arrow_x + head_half_width, base_y),
            ])
            painter.setBrush(sankey_color)
            painter.setPen(QtGui.QPen(outline, 1.0))
            painter.drawPolygon(arrow)
            painter.setPen(foreground)
            label_y = tip_y - 43.0 if direction < 0 else tip_y + 6.0
            painter.drawText(
                QtCore.QRectF(arrow_x - 88.0, label_y, 176.0, 40.0),
                QtCore.Qt.AlignCenter, f"{label}\n{value:.1f} kW",
            )
