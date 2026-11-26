from collections import deque
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .theme import CHART_GRID, CHART_LABEL


class MetricChart(QWidget):
    def __init__(self, color: str, accessible_name: str) -> None:
        super().__init__()
        self._color = QColor(color)
        self._points: deque[tuple[datetime, float | None]] = deque(maxlen=60)
        self.setAccessibleName(accessible_name)
        self.setMinimumHeight(144)

    def add_sample(self, timestamp: datetime, value: float | None) -> None:
        self._points.append((timestamp, value))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = QRectF(44, 12, self.width() - 56, self.height() - 38)
        grid = QColor(CHART_GRID)
        labels = QColor(CHART_LABEL)
        for percent in (0, 25, 50, 75, 100):
            y = plot.bottom() - plot.height() * percent / 100
            painter.setPen(grid)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(labels)
            painter.drawText(
                QRectF(0, y - 8, 37, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(percent),
            )

        if not any(value is not None for _, value in self._points):
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Нет данных для графика")
            return

        start = self._points[0][0]
        end = self._points[-1][0]
        duration = max((end - start).total_seconds(), 0.001)
        path = QPainterPath()
        markers = []
        has_previous = False
        for timestamp, value in self._points:
            if value is None:
                has_previous = False
                continue
            elapsed = (timestamp - start).total_seconds()
            x = plot.left() + plot.width() * min(max(elapsed / duration, 0), 1)
            y = plot.bottom() - plot.height() * value / 100
            point = QPointF(x, y)
            markers.append(point)
            if has_previous:
                path.lineTo(point)
            else:
                path.moveTo(point)
            has_previous = True

        trace = QPen(self._color, 2)
        trace.setCapStyle(Qt.PenCapStyle.RoundCap)
        trace.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(trace)
        painter.drawPath(path)
        painter.drawPoints(markers)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(markers[-1], 3, 3)
        painter.setPen(labels)
        time_axis = QRectF(plot.left(), plot.bottom() + 7, plot.width(), 19)
        painter.drawText(time_axis, Qt.AlignmentFlag.AlignLeft, start.astimezone().strftime("%H:%M:%S"))
        if start != end:
            painter.drawText(time_axis, Qt.AlignmentFlag.AlignRight, end.astimezone().strftime("%H:%M:%S"))
