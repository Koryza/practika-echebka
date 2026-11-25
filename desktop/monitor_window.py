from PySide6.QtCore import QObject, QPropertyAnimation, QSignalBlocker, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from .metric_chart import MetricChart
from .monitor import DiskUsage, SystemMonitor, SystemSnapshot

UPDATE_INTERVAL_MS = 2000

WINDOW_STYLE = """
QWidget#dashboard { background: #101721; }
QWidget { color: #edf2fa; font-size: 13px; }
QLabel#heading { font-size: 28px; font-weight: 700; }
QLabel#cardTitle { font-size: 15px; font-weight: 650; }
QLabel#metric { font-size: 28px; font-weight: 700; }
QLabel[role="details"], QLabel#status { color: #aab9ce; }
QFrame[role="card"] {
    background: #182230;
    border: 1px solid #29364a;
    border-radius: 12px;
}
QComboBox {
    background: #101721;
    color: #edf2fa;
    border: 1px solid #526783;
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 22px;
}
QComboBox:focus { border-color: #67dcad; }
QComboBox QAbstractItemView {
    background: #182230;
    color: #edf2fa;
    selection-background-color: #334966;
    selection-color: #ffffff;
}
QProgressBar {
    background: #2a3546;
    border: 0;
    border-radius: 5px;
}
QProgressBar::chunk { background: #67dcad; border-radius: 5px; }
"""


def _percent(value: float | None) -> str:
    return "Недоступно" if value is None else f"{value:.1f} %".replace(".", ",")


def _bytes(value: int | None) -> str:
    return "Недоступно" if value is None else f"{value / 1024**3:.1f} ГиБ".replace(".", ",")


def _label(text: str, name: str = "", *, details: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    if details:
        label.setProperty("role", "details")
        label.setWordWrap(True)
    return label


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("role", "card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 14, 18, 14)
    layout.setSpacing(8)
    return frame, layout


class SampleWorker(QObject):
    sampled = Signal(object)
    failed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._monitor: SystemMonitor | None = None

    @Slot()
    def sample(self) -> None:
        try:
            if self._monitor is None:
                self._monitor = SystemMonitor()
            snapshot = self._monitor.sample()
        except OSError:
            self.failed.emit()
        else:
            self.sampled.emit(snapshot)


class MonitorWindow(QMainWindow):
    sample_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("System Monitor")
        self.setMinimumSize(720, 560)
        self.resize(990, 660)
        self.setStyleSheet(WINDOW_STYLE)
        self._disks: dict[str, DiskUsage] = {}
        self._sampling = False
        self._has_sample = False

        dashboard = QWidget()
        dashboard.setObjectName("dashboard")
        self.setCentralWidget(dashboard)
        layout = QVBoxLayout(dashboard)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)
        layout.addWidget(_label("Мониторинг Mac", "heading"))
        self._status = _label("Получаем первый замер…", "status")
        layout.addWidget(self._status)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(14)
        cpu_card, cpu_layout = _card()
        cpu_layout.addWidget(_label("Загрузка процессора", "cardTitle"))
        self._cpu_value = _label("—", "metric")
        self._cpu_details = _label("Ожидание данных", details=True)
        self._cpu_chart = MetricChart("#7ea8ff", "График загрузки процессора в процентах")
        cpu_layout.addWidget(self._cpu_value)
        cpu_layout.addWidget(self._cpu_details)
        cpu_layout.addWidget(self._cpu_chart, 1)
        metric_row.addWidget(cpu_card, 1)

        memory_card, memory_layout = _card()
        memory_layout.addWidget(_label("Использование памяти", "cardTitle"))
        self._memory_value = _label("—", "metric")
        self._memory_details = _label("Ожидание данных", details=True)
        self._memory_chart = MetricChart("#dfabff", "График использования памяти в процентах")
        memory_layout.addWidget(self._memory_value)
        memory_layout.addWidget(self._memory_details)
        memory_layout.addWidget(self._memory_chart, 1)
        metric_row.addWidget(memory_card, 1)
        layout.addLayout(metric_row, 1)

        disk_card, disk_layout = _card()
        disk_layout.addWidget(_label("Накопители", "cardTitle"))
        self._disk_selector = QComboBox()
        self._disk_selector.setAccessibleName("Выбор накопителя")
        self._disk_selector.setMinimumContentsLength(18)
        self._disk_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._disk_selector.setEnabled(False)
        self._disk_selector.currentIndexChanged.connect(self._show_selected_disk)
        self._disk_value = _label("—", "metric")
        disk_header = QHBoxLayout()
        disk_header.addWidget(self._disk_selector, 1)
        disk_header.addWidget(self._disk_value)
        disk_layout.addLayout(disk_header)

        self._disk_bar = QProgressBar()
        self._disk_bar.setAccessibleName("Заполненность накопителя в процентах")
        self._disk_bar.setFixedHeight(10)
        self._disk_bar.setRange(0, 100)
        self._disk_bar.setTextVisible(False)
        self._disk_bar.setValue(0)
        disk_layout.addWidget(self._disk_bar)
        self._disk_details = _label("Ожидание данных", details=True)
        disk_layout.addWidget(self._disk_details)
        layout.addWidget(disk_card)
        self._disk_animation = QPropertyAnimation(self._disk_bar, b"value", self)
        self._disk_animation.setDuration(350)

        self._timer = QTimer(self)
        self._timer.setInterval(UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._request_sample)
        self._thread = QThread(self)
        self._worker = SampleWorker()
        self._worker.moveToThread(self._thread)
        self._thread.finished.connect(self._worker.deleteLater)
        self.sample_requested.connect(self._worker.sample)
        self._worker.sampled.connect(self._show_sample)
        self._worker.failed.connect(self._show_sample_error)
        self._thread.start()
        self._request_sample()
        self._timer.start()

    @Slot()
    def _request_sample(self) -> None:
        if not self._sampling:
            self._sampling = True
            self.sample_requested.emit()

    @Slot(object)
    def _show_sample(self, snapshot: SystemSnapshot) -> None:
        self._sampling = False
        self._has_sample = True
        time = snapshot.timestamp.astimezone().strftime("%H:%M:%S")
        self._status.setText(f"Последний замер в {time}")
        cpu = snapshot.cpu
        self._cpu_value.setText(_percent(snapshot.cpu_usage_percent))
        physical = cpu.physical_cores or "нет данных"
        logical = cpu.logical_cores or "нет данных"
        self._cpu_details.setText(
            f"{cpu.model or 'Модель недоступна'} · Ядра: {physical} физических, {logical} логических"
        )
        memory = snapshot.memory
        memory_percent = memory.usage_percent if memory is not None else None
        self._memory_value.setText(_percent(memory_percent))
        if memory is None:
            self._memory_details.setText("Сведения о памяти недоступны")
        else:
            self._memory_details.setText(
                f"Всего {_bytes(memory.total_bytes)} · Занято {_bytes(memory.used_bytes)}"
                f" · Доступно {_bytes(memory.available_bytes)}"
            )
        self._cpu_chart.add_sample(snapshot.timestamp, snapshot.cpu_usage_percent)
        self._memory_chart.add_sample(snapshot.timestamp, memory_percent)
        self._update_disks(snapshot.disks)

    @Slot()
    def _show_sample_error(self) -> None:
        self._sampling = False
        message = "Замер не получен"
        if self._has_sample:
            message += " · Показаны последние доступные данные"
        self._status.setText(message)

    def _update_disks(self, disks: tuple[DiskUsage, ...]) -> None:
        selected = self._disk_selector.currentData()
        updated = {disk.mountpoint: disk for disk in disks}
        previous_options = [(path, disk.device) for path, disk in self._disks.items()]
        new_options = [(path, disk.device) for path, disk in updated.items()]
        self._disks = updated
        if previous_options != new_options:
            with QSignalBlocker(self._disk_selector):
                self._disk_selector.clear()
                for path, device in new_options:
                    label = f"{path} · {device}" if device else path
                    self._disk_selector.addItem(label, path)
                preferred = selected or "/System/Volumes/Data"
                index = self._disk_selector.findData(preferred)
                self._disk_selector.setCurrentIndex(max(0, index))
                self._disk_selector.setEnabled(bool(disks))
        self._show_selected_disk()

    @Slot()
    def _show_selected_disk(self) -> None:
        disk = self._disks.get(self._disk_selector.currentData())
        percent = disk.usage_percent if disk is not None else None
        self._disk_value.setText(_percent(percent))
        if disk is None or percent is None:
            self._disk_details.setText("Сведения о накопителе недоступны")
            self._disk_animation.stop()
            self._disk_bar.setValue(0)
            self._disk_bar.hide()
            return

        self._disk_details.setText(
            f"Всего {_bytes(disk.total_bytes)} · Занято {_bytes(disk.used_bytes)}"
            f" · Свободно {_bytes(disk.free_bytes)}"
        )
        self._disk_bar.show()
        target = round(percent)
        if self._disk_animation.endValue() != target or self._disk_bar.value() != target:
            self._disk_animation.stop()
            self._disk_animation.setStartValue(self._disk_bar.value())
            self._disk_animation.setEndValue(target)
            self._disk_animation.start()

    @Slot()
    def stop_sampling(self) -> None:
        self._timer.stop()
        self._thread.quit()
        self._thread.wait()

    def closeEvent(self, event) -> None:
        self.stop_sampling()
        super().closeEvent(event)
