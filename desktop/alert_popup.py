from PySide6.QtCore import QPoint, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .alerts import RESOURCE_LABELS, Alert


class AlertPopup(QWidget):
    history_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Пороговое уведомление")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(340)

        card = QFrame()
        card.setObjectName("alertCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 10, 12, 13)
        layout.setSpacing(6)

        title = QLabel("Порог превышен")
        title.setObjectName("alertTitle")
        dismiss = QPushButton("×")
        dismiss.setObjectName("alertClose")
        dismiss.setAccessibleName("Закрыть уведомление")
        dismiss.setToolTip("Закрыть уведомление")
        dismiss.clicked.connect(self.dismiss)
        header = QHBoxLayout()
        header.addWidget(title, 1)
        header.addWidget(dismiss)
        layout.addLayout(header)

        self._reading = QLabel()
        self._reading.setObjectName("alertReading")
        self._reading.setTextFormat(Qt.TextFormat.PlainText)
        self._reading.setWordWrap(True)
        layout.addWidget(self._reading)

        history = QPushButton("Открыть историю")
        history.setObjectName("alertHistory")
        history.clicked.connect(self._open_history)
        layout.addWidget(history, alignment=Qt.AlignmentFlag.AlignLeft)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(10_000)
        self._timer.timeout.connect(self.dismiss)

    @Slot(object)
    def show_alerts(self, alerts: list[Alert]) -> None:
        if not alerts or not self.parentWidget().isVisible() or self.parentWidget().isMinimized():
            return

        latest = alerts[0]
        resource = RESOURCE_LABELS[latest.resource]
        if latest.target:
            target = self._reading.fontMetrics().elidedText(latest.target, Qt.TextElideMode.ElideMiddle, 210)
            resource += f" · {target}"
        measured = f"{latest.measured:.1f}".replace(".", ",")
        reading = f"{resource}\nТекущее значение {measured} % · порог {latest.threshold} %"
        if len(alerts) > 1:
            reading += f"\nДругих превышений в этом замере: {len(alerts) - 1}"
        self._reading.setText(reading)
        self.adjustSize()
        self.reposition()
        self.show()
        self._timer.start()

    def reposition(self) -> None:
        parent = self.parentWidget()
        screen = parent.screen().availableGeometry()
        corner = parent.mapToGlobal(QPoint(parent.width() - self.width() - 22, 62))
        self.move(
            max(screen.left(), min(corner.x(), screen.right() - self.width() + 1)),
            max(screen.top(), min(corner.y(), screen.bottom() - self.height() + 1)),
        )

    @Slot()
    def dismiss(self) -> None:
        self._timer.stop()
        self.hide()

    @Slot()
    def _open_history(self) -> None:
        self.dismiss()
        self.history_requested.emit()
