from datetime import datetime

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .alerts import ALERT_LIMITS, RESOURCE_LABELS, Alert, AlertSettings
from .storage import HistoryPage


class AlertsPanel(QWidget):
    test_notification_requested = Signal()
    settings_requested = Signal(object)
    history_requested = Signal(int, object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dashboard")
        self._saving = False
        self._settings_loaded = False
        self._loading = False
        self._page = 0
        self._history: HistoryPage | None = None
        self._refresh_pending = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 16)
        heading = QLabel("Пороговые уведомления")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        controls = QGridLayout()
        self._fields: dict[str, QSpinBox] = {}
        for column, (key, title) in enumerate(
            (
                ("cpu_threshold", "Процессор"),
                ("memory_threshold", "Память"),
                ("disk_threshold", "Каждый накопитель"),
                ("repeat_seconds", "Пауза повтора"),
            )
        ):
            field = QSpinBox()
            field.setRange(*ALERT_LIMITS[key])
            field.setSuffix(" с" if key == "repeat_seconds" else " %")
            field.setAccessibleName(title)
            self._fields[key] = field
            label = QLabel(title)
            label.setBuddy(field)
            controls.addWidget(label, 0, column)
            controls.addWidget(field, 1, column)
        layout.addLayout(controls)

        self._settings_status = QLabel()
        self._settings_status.setObjectName("status")
        self._settings_status.setWordWrap(True)
        self._save = QPushButton("Сохранить пороги")
        self._save.clicked.connect(self._save_settings)
        save_row = QHBoxLayout()
        save_row.addWidget(self._save)
        save_row.addWidget(self._settings_status, 1)
        layout.addLayout(save_row)
        self._display_settings(AlertSettings())

        hint = QLabel("Повтор учитывается отдельно для ЦП, памяти и каждого тома.")
        hint.setProperty("role", "details")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        test = QPushButton("Проверить уведомления macOS")
        test.clicked.connect(self.test_notification_requested)
        self._notification_status = QLabel()
        self._notification_status.setObjectName("status")
        self._notification_status.setWordWrap(True)
        notification_row = QHBoxLayout()
        notification_row.addWidget(test)
        notification_row.addWidget(self._notification_status, 1)
        layout.addLayout(notification_row)

        self._table = QTableWidget(0, 5)
        self._table.setAlternatingRowColors(True)
        self._table.setHorizontalHeaderLabels(["Время", "Ресурс", "Том", "Замер", "Порог"])
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, 1)

        navigation = QHBoxLayout()
        self._refresh = QPushButton("Обновить историю")
        self._refresh.clicked.connect(lambda: self._request_history(0))
        self._previous = QPushButton("Назад")
        self._previous.clicked.connect(lambda: self._turn_page(-1))
        self._next = QPushButton("Вперёд")
        self._next.clicked.connect(lambda: self._turn_page(1))
        self._page_label = QLabel("Страница 1")
        self._history_status = QLabel()
        self._history_status.setObjectName("status")
        self._history_status.setWordWrap(True)
        for widget in (self._refresh, self._previous, self._page_label, self._next):
            navigation.addWidget(widget)
        navigation.addWidget(self._history_status, 1)
        layout.addLayout(navigation)
        self._sync_buttons()

    @Slot(str)
    def set_notification_status(self, message: str) -> None:
        self._notification_status.setText(message)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._page == 0:
            self._request_history(0)

    def _sync_buttons(self) -> None:
        self._save.setEnabled(self._settings_loaded and not self._saving)
        for field in self._fields.values():
            field.setEnabled(self._settings_loaded and not self._saving)
        self._refresh.setEnabled(not self._loading)
        self._previous.setEnabled(not self._loading and self._page > 0)
        self._next.setEnabled(not self._loading and self._history is not None and self._history.has_next)

    def _display_settings(self, settings: AlertSettings) -> None:
        for key, field in self._fields.items():
            field.setValue(getattr(settings, key))

    @Slot(object)
    def set_settings(self, settings: AlertSettings) -> None:
        self._settings_loaded = True
        self._display_settings(settings)
        self._sync_buttons()

    @Slot()
    def _save_settings(self) -> None:
        settings = AlertSettings(**{key: field.value() for key, field in self._fields.items()})
        self._saving = True
        self._settings_status.setText("Сохраняем…")
        self._sync_buttons()
        self.settings_requested.emit(settings)

    @Slot(object, str)
    def settings_result(self, settings: AlertSettings | None, message: str) -> None:
        self._saving = False
        self._settings_status.setText(message)
        if settings is not None:
            self._display_settings(settings)
        self._sync_buttons()

    @Slot(object)
    def new_alerts(self, _alerts: list[Alert]) -> None:
        if self.isVisible() and self._page == 0:
            if self._loading:
                self._refresh_pending = True
            else:
                self._request_history(0)

    def _turn_page(self, offset: int) -> None:
        if self._history is not None:
            self._request_history(self._page + offset, self._history.through_id)

    def _request_history(self, page: int, through_id: int | None = None) -> None:
        if self._loading:
            return
        self._loading = True
        self._sync_buttons()
        self.history_requested.emit(page, through_id)

    @Slot(int, object, str)
    def show_history(self, page: int, history: HistoryPage | None, error: str) -> None:
        self._loading = False
        if history is not None:
            self._page, self._history = page, history
            self._page_label.setText(f"Страница {page + 1}")
            self._table.setRowCount(len(history.rows))
            for row, (timestamp, resource, target, measured, threshold) in enumerate(history.rows):
                values = (
                    datetime.fromtimestamp(timestamp / 1000).strftime("%d.%m.%Y %H:%M:%S"),
                    RESOURCE_LABELS[resource],
                    target or "—",
                    f"{measured:.1f} %".replace(".", ","),
                    f"{threshold} %",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column in (3, 4):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self._table.setItem(row, column, item)
        empty = history is not None and not history.rows
        self._history_status.setText(error or ("Уведомлений пока нет" if empty else ""))
        self._sync_buttons()
        pending, self._refresh_pending = self._refresh_pending, False
        if pending and self._page == 0:
            self._request_history(0)
