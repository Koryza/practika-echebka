from collections import deque
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class MetricChart(QWidget):
    def __init__(self, color: str, accessible_name: str) -> None:
        super().__init__()
        self._color = QColor(color)
        self._points: deque[tuple[datetime, float | None]] = deque(maxlen=60)
        self.setAccessibleName(accessible_name)
        self.setMinimumHeight(172)

    def add_sample(self, timestamp: datetime, value: float | None) -> None:
        self._points.append((timestamp, value))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = QRectF(44, 12, self.width() - 56, self.height() - 38)
        for percent in (0, 25, 50, 75, 100):
            y = plot.bottom() - plot.height() * percent / 100
            painter.setPen(QColor("#2a3546"))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#9eaec6"))
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

        painter.setPen(QPen(self._color, 2))
        painter.drawPath(path)
        painter.drawPoints(markers)
        painter.setPen(QColor("#9eaec6"))
        time_axis = QRectF(plot.left(), plot.bottom() + 7, plot.width(), 19)
        painter.drawText(time_axis, Qt.AlignmentFlag.AlignLeft, start.astimezone().strftime("%H:%M:%S"))
        if start != end:
            painter.drawText(time_axis, Qt.AlignmentFlag.AlignRight, end.astimezone().strftime("%H:%M:%S"))
