from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, QSignalBlocker, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .files_panel import FilesPanel
from .history_panel import HistoryPanel
from .metric_chart import MetricChart
from .monitor import DiskUsage, SystemSnapshot
from .process_panel import ProcessPanel

from .sampling import SampleWorker
from .settings import Settings

WINDOW_STYLE = """
QMainWindow, QWidget#dashboard, QTabWidget, QDialog { background: #101721; }
QWidget { color: #edf2fa; font-size: 13px; }
QTabWidget::pane { border: 0; background: #101721; }
QTabWidget::tab-bar { alignment: left; }
QTabBar::tab { background: #182230; color: #aab9ce; padding: 9px 18px; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #67dcad; }
QPushButton {
    background: #263448;
    border: 1px solid #3e5069;
    border-radius: 5px;
    padding: 5px 8px;
}
QPushButton:hover { background: #334966; }
QLineEdit, QDateEdit, QSpinBox { background: #182230; color: #edf2fa; border: 1px solid #526783; padding: 4px; }
QPushButton:focus { border-color: #67dcad; }

QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #7085a0; border-radius: 3px; }
QCheckBox::indicator:checked { background: #67dcad; border-color: #67dcad; }
QCheckBox::indicator:disabled { border-color: #3e5069; }
QCheckBox::indicator:checked:disabled { background: #3e5069; }
QDateEdit:disabled { color: #8795a8; border-color: #29364a; }
QPushButton:disabled { background: #182230; color: #8795a8; }
QTableWidget { background: #182230; gridline-color: #29364a; selection-background-color: #334966; }
QCalendarWidget QWidget { background: #182230; }
QCalendarWidget QAbstractItemView { selection-background-color: #334966; }
QCalendarWidget QToolButton { color: #edf2fa; }
QHeaderView::section { background: #263448; color: #edf2fa; padding: 5px; border: 0; }
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


class MonitorWindow(QMainWindow):
    sample_requested = Signal()
    recording_configured = Signal(object)

    def __init__(self, db_path: Path | None = None) -> None:
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
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(dashboard, "Мониторинг")
        self._files = FilesPanel(db_path)
        tabs.addTab(self._files, "Файлы")
        self._processes = ProcessPanel(db_path)
        tabs.addTab(self._processes, "Процессы")
        self._history = HistoryPanel(db_path)
        tabs.addTab(self._history, "История и настройки")
        self._files.workspace_changed.connect(self._history.set_workspace)
        self._files.workspace_selected.connect(self._history.workspace_result)
        self._history.workspace_requested.connect(self._files.set_workspace_root)
        self._history.settings_saved.connect(self._apply_settings)
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
        self._timer.setInterval(Settings().refresh_seconds * 1000)
        self._timer.timeout.connect(self._request_sample)
        self._thread = QThread(self)
        self._worker = SampleWorker(db_path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.initialize)
        self._worker.settings_loaded.connect(self._apply_settings)
        self._worker.storage_error.connect(self._show_storage_error)
        self.recording_configured.connect(self._worker.configure)
        self._thread.finished.connect(self._worker.deleteLater)
        self.sample_requested.connect(self._worker.sample)
        self._worker.sampled.connect(self._show_sample)
        self._worker.failed.connect(self._show_sample_error)
        self._thread.start()
        self._request_sample()
        self._timer.start()

    @Slot(object)
    def _apply_settings(self, settings: Settings) -> None:
        interval = settings.refresh_seconds * 1000
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)
        self.recording_configured.emit(settings)

    @Slot(str)
    def _show_storage_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)

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

    @Slot()
    def stop_workers(self) -> None:
        self.stop_sampling()
        self._files.stop()
        self._processes.stop()
        self._history.stop()

    def closeEvent(self, event) -> None:
        self.stop_workers()
        super().closeEvent(event)
