from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import QDate, QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .settings import SETTINGS_LIMITS, Settings
from .storage import HistoryPage, Storage

EVENT_CATEGORIES = {"files": "Файлы", "processes": "Процессы", "system": "Система"}
EVENT_OPERATIONS = {
    "create_file": "Создание файла",
    "create_folder": "Создание папки",
    "copy": "Копирование",
    "move": "Перемещение",
    "rename": "Переименование",
    "delete": "Удаление",
    "toggle_read_only": "Изменение атрибута",
    "launch": "Запуск",
    "terminate": "Завершение",
}


@dataclass(frozen=True)
class HistoryRequest:
    action: str
    table: str
    page: int = 0
    period: tuple[int, int] | None = None
    settings: Settings | None = None
    through_id: int | None = None


@dataclass(frozen=True)
class HistoryResult:
    page: HistoryPage | None = None
    settings: Settings | None = None
    message: str = ""


class HistoryWorker(QObject):
    completed = Signal(object, object)

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self._db_path = db_path
        self._storage: Storage | None = None

    @Slot(object)
    def execute(self, request: HistoryRequest) -> None:
        settings = None
        message = ""
        try:
            if self._storage is None:
                self._storage = Storage(self._db_path)
            if request.action == "initial":
                settings = self._storage.load_settings()
            elif request.action == "save":
                settings = request.settings
                self._storage.save_settings(settings)
                self.completed.emit(request, HistoryResult(settings=settings, message="Настройки сохранены"))
                return
            elif request.action == "clear":
                if request.table == "metrics":
                    self._storage.clear_metrics()
                    message = "История замеров очищена"
                else:
                    self._storage.clear_events()
                    message = "Журнал событий очищен"
            if request.table == "metrics":
                page = self._storage.metrics(request.page, request.period, request.through_id)
            else:
                page = self._storage.events(request.page, request.through_id)
        except (DatabaseError, OSError):
            message = f"{message} · Не удалось обновить таблицу" if message else "Не удалось выполнить запрос к SQLite"
            self.completed.emit(request, HistoryResult(message=message))
        else:
            self.completed.emit(request, HistoryResult(page, settings, message))


def _format_time(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000).strftime("%d.%m.%Y %H:%M:%S")


def _format_percent(value: float | None) -> str:
    return "Недоступно" if value is None else f"{value:.1f} %".replace(".", ",")


def _local_midnight(date: QDate) -> int:
    return int(datetime.combine(date.toPython(), time.min).timestamp()) * 1000


class HistoryPanel(QWidget):
    requested = Signal(object)
    settings_saved = Signal(object)
    workspace_requested = Signal(str)

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self.setObjectName("dashboard")
        self._busy = False
        self._loaded = False
        self._page = 0
        self._has_next = False
        self._applied_period = None
        self._through_id = None
        self._workspace = ""
        self._pending_workspace: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(10)
        heading = QLabel("История и настройки")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        controls = QHBoxLayout()
        self._kind = QComboBox()
        self._kind.addItem("Замеры", "metrics")
        self._kind.addItem("Журнал событий", "events")
        self._kind.setAccessibleName("Показывать данные")
        self._kind.currentIndexChanged.connect(self._change_table)
        self._period_enabled = QCheckBox("За период")
        self._period_enabled.toggled.connect(self._sync_controls)
        self._from = QDateEdit(QDate.currentDate().addDays(-7))
        self._through = QDateEdit(QDate.currentDate())
        for field, label in ((self._from, "Начало периода"), (self._through, "Конец периода")):
            field.setAccessibleName(label)
            field.setCalendarPopup(True)
            field.setDisplayFormat("dd.MM.yyyy")
        self._refresh = QPushButton("Обновить")
        self._refresh.clicked.connect(lambda: self._query("list"))
        self._clear = QPushButton("Очистить…")
        self._clear.clicked.connect(self._confirm_clear)
        for widget in (self._kind, self._period_enabled, self._from, self._through, self._refresh, self._clear):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)

        self._table = QTableWidget()
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table, 1)

        pagination = QHBoxLayout()
        self._previous = QPushButton("Назад")
        self._previous.clicked.connect(lambda: self._change_page(-1))
        self._next = QPushButton("Вперёд")
        self._next.clicked.connect(lambda: self._change_page(1))
        self._page_label = QLabel("Страница 1")
        pagination.addWidget(self._previous)
        pagination.addWidget(self._page_label)
        pagination.addWidget(self._next)
        pagination.addStretch()
        layout.addLayout(pagination)

        settings_grid = QGridLayout()
        self._fields = {}
        for column, (key, label) in enumerate(
            (
                ("refresh_seconds", "Обновление показателей"),
                ("record_seconds", "Запись замеров"),
                ("api_port", "Порт HTTP API"),
            )
        ):
            field = QSpinBox()
            field.setRange(*SETTINGS_LIMITS[key])
            if key != "api_port":
                field.setSuffix(" с")
            field.setAccessibleName(label)
            self._fields[key] = field
            settings_grid.addWidget(QLabel(label), 0, column)
            settings_grid.addWidget(field, 1, column)
        self._save = QPushButton("Сохранить настройки")
        self._save.clicked.connect(self._save_settings)
        settings_grid.addWidget(self._save, 1, 3)
        self._api_status = QLabel("HTTP API запускается…")
        self._api_status.setObjectName("status")
        self._api_status.setWordWrap(True)
        self._api_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        settings_grid.addWidget(self._api_status, 2, 0, 1, 4)
        layout.addLayout(settings_grid)

        folder_row = QHBoxLayout()
        self._choose = QPushButton("Выбрать рабочую папку…")
        self._choose.clicked.connect(self._choose_workspace)
        self._folder_name = QLabel("Рабочая папка не выбрана")
        self._folder_name.setTextFormat(Qt.TextFormat.PlainText)
        self._folder_name.setWordWrap(True)
        folder_row.addWidget(self._choose)
        folder_row.addWidget(self._folder_name, 1)
        layout.addLayout(folder_row)

        self._status = QLabel()
        self._status.setObjectName("status")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._set_settings(Settings())
        self._sync_controls()

        self._thread = QThread(self)
        self._worker = HistoryWorker(db_path)
        self._worker.moveToThread(self._thread)
        self._thread.finished.connect(self._worker.deleteLater)
        self.requested.connect(self._worker.execute)
        self._worker.completed.connect(self._show_result)
        self._thread.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._loaded:
            self._query("initial")

    @Slot()
    def _sync_controls(self) -> None:
        available = not self._busy
        metrics = self._kind.currentData() == "metrics"
        for widget in (self._kind, self._refresh, self._clear, *self._fields.values()):
            widget.setEnabled(available)
        self._save.setEnabled(available and self._loaded)
        self._period_enabled.setEnabled(available and metrics)
        use_period = available and metrics and self._period_enabled.isChecked()
        self._from.setEnabled(use_period)
        self._through.setEnabled(use_period)
        self._previous.setEnabled(available and self._page > 0)
        self._next.setEnabled(available and self._has_next)
        self._choose.setEnabled(self._pending_workspace is None)

    @Slot()
    def _change_table(self) -> None:
        self._query("list" if self._loaded else "initial")

    def _change_page(self, offset: int) -> None:
        request = HistoryRequest(
            "list", self._kind.currentData(), self._page + offset,
            self._applied_period, through_id=self._through_id,
        )
        self._send(request)

    def _query(self, action: str) -> None:
        kind = self._kind.currentData()
        period = None
        if kind == "metrics" and self._period_enabled.isChecked() and action != "clear":
            start = self._from.date()
            end = self._through.date()
            if start > end:
                self._status.setText("Начало периода должно быть раньше конца или совпадать с ним")
                return
            period = _local_midnight(start), _local_midnight(end.addDays(1))
        if action == "clear" and kind == "metrics":
            self._period_enabled.setChecked(False)
        self._send(HistoryRequest(action, kind, period=period))

    def _send(self, request: HistoryRequest) -> None:
        if self._busy:
            return
        self._busy = True
        self._status.setText("Выполняется…")
        self._sync_controls()
        self.requested.emit(request)

    @Slot()
    def _save_settings(self) -> None:
        settings = Settings(**{key: field.value() for key, field in self._fields.items()})
        self._send(HistoryRequest("save", self._kind.currentData(), settings=settings))

    def set_api_status(self, message: str) -> None:
        self._api_status.setText(message)

    def _set_settings(self, settings: Settings) -> None:
        for key, field in self._fields.items():
            field.setValue(getattr(settings, key))

    @Slot()
    def _confirm_clear(self) -> None:
        metrics = self._kind.currentData() == "metrics"
        target = "всю историю замеров" if metrics else "весь журнал событий"
        dialog = QMessageBox(QMessageBox.Icon.Warning, "Подтверждение очистки", "", parent=self)
        dialog.setText(f"Очистить {target}?")
        clear = dialog.addButton("Очистить", QMessageBox.ButtonRole.DestructiveRole)
        cancel = dialog.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        if dialog.clickedButton() == clear:
            self._query("clear")

    @Slot(object, object)
    def _show_result(self, request: HistoryRequest, result: HistoryResult) -> None:
        self._busy = False
        if result.settings is not None:
            self._set_settings(result.settings)
            if request.action == "save":
                self.settings_saved.emit(result.settings)
        if result.page is not None:
            self._loaded = True
            self._page = request.page
            self._has_next = result.page.has_next
            self._applied_period = request.period
            self._through_id = result.page.through_id
            self._page_label.setText(f"Страница {self._page + 1}")
            self._populate(request.table, result.page)
        message = result.message
        if not message and result.page is not None and not result.page.rows:
            message = "Записей нет"
        self._status.setText(message)
        self._sync_controls()

    def _populate(self, kind: str, page: HistoryPage) -> None:
        metrics = kind == "metrics"
        headers = (
            ["Время замера", "ЦП", "Память"]
            if metrics
            else ["Время", "Раздел", "Действие", "Описание", "Результат"]
        )
        self._table.clear()
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(len(page.rows))
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0 if metrics else 3, QHeaderView.ResizeMode.Stretch)
        for row, record in enumerate(page.rows):
            timestamp, *values = record
            if metrics:
                text = [_format_percent(value) for value in values]
            else:
                category, operation, description, status = values
                text = [
                    EVENT_CATEGORIES.get(category, category),
                    EVENT_OPERATIONS.get(operation, operation),
                    description,
                    "Успех" if status == "success" else "Ошибка",
                ]
            for column, value in enumerate((_format_time(timestamp), *text)):
                item = QTableWidgetItem(value)
                if not metrics and column == 3:
                    item.setToolTip(value)
                self._table.setItem(row, column, item)

    @Slot()
    def _choose_workspace(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Рабочая папка", self._workspace or str(Path.home())
        )
        if directory:
            self._pending_workspace = directory
            self._status.setText("Открываем рабочую папку…")
            self._sync_controls()
            self.workspace_requested.emit(directory)

    @Slot(str)
    def set_workspace(self, directory: str) -> None:
        self._workspace = directory
        self._folder_name.setText(directory or "Рабочая папка не выбрана")

    @Slot(str, str)
    def workspace_result(self, directory: str, error: str) -> None:
        if self._pending_workspace == directory:
            self._pending_workspace = None
            self._status.setText(error or "Рабочая папка сохранена")
            self._sync_controls()

    @Slot()
    def stop(self) -> None:
        self._thread.quit()
        self._thread.wait()
