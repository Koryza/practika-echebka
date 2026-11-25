from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Error as DatabaseError

import psutil
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .processes import ProcessEntry, ProcessError, ProcessManager, explain_process_error
from .storage import Storage

PROCESS_ERRORS = (OSError, ProcessError, psutil.Error)


@dataclass(frozen=True)
class ProcessRequest:
    operation: str
    executable: str = ""
    pid: int = 0


class ProcessWorker(QObject):
    completed = Signal(object, str, int)

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self._manager = ProcessManager()
        self._db_path = db_path
        self._storage: Storage | None = None

    @Slot()
    def start_reaping(self) -> None:
        self._reap_timer = QTimer(self)
        self._reap_timer.timeout.connect(self._manager.reap_finished)
        self._reap_timer.start(5000)

    @Slot(object)
    def execute(self, request: ProcessRequest) -> None:
        message, launched_pid = (
            self._change_process(request) if request.operation != "refresh" else ("", 0)
        )
        try:
            entries = self._manager.list_processes()
        except PROCESS_ERRORS as error:
            detail = explain_process_error(error)
            self.completed.emit(None, f"{message} · {detail}" if message else detail, 0)
        else:
            self.completed.emit(entries, message, launched_pid)

    def _change_process(self, request: ProcessRequest) -> tuple[str, int]:
        launched_pid = 0
        try:
            if request.operation == "terminate":
                description = f"PID {request.pid}"
                self._manager.terminate(request.pid)
                message = f"Процесс {request.pid} завершён"
            else:
                description = request.executable or "Тестовый процесс sleep"
                if request.executable:
                    pid = self._manager.launch(Path(request.executable))
                else:
                    pid = self._manager.launch_demo()
                launched_pid = pid
                description += f" · PID {pid}"
                message = f"Процесс запущен · PID {pid}"
        except PROCESS_ERRORS as error:
            message = explain_process_error(error)
            description += f" · {message}"
            status = "error"
        else:
            status = "success"

        try:
            if self._storage is None:
                self._storage = Storage(self._db_path)
            self._storage.log_event("processes", request.operation, description, status)
        except (DatabaseError, OSError):
            message += " · Не удалось записать событие в журнал"
        return message, launched_pid


class ProcessPanel(QWidget):
    requested = Signal(object)

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self.setObjectName("dashboard")
        self._entries: list[ProcessEntry] = []
        self._busy = False
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(10)
        heading = QLabel("Процессы Mac")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        actions = QHBoxLayout()
        self._refresh = QPushButton("Обновить")
        self._refresh.clicked.connect(lambda: self._request(ProcessRequest("refresh")))
        self._launch = QPushButton("Запустить файл…")
        self._launch.clicked.connect(self._choose_executable)
        self._demo = QPushButton("Запустить тестовый процесс")
        self._demo.clicked.connect(lambda: self._request(ProcessRequest("launch")))
        self._terminate = QPushButton("Завершить…")
        self._terminate.clicked.connect(self._confirm_termination)
        for button in (self._refresh, self._launch, self._demo, self._terminate):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["PID", "Название", "Память", "Запущен через"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 85)
        self._table.setColumnWidth(2, 110)
        self._table.setColumnWidth(3, 145)
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._sync_buttons)
        layout.addWidget(self._table, 1)

        self._status = QLabel("Завершение доступно для процессов, запущенных через System Monitor.")
        self._status.setObjectName("status")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._sync_buttons()

        self._thread = QThread(self)
        self._worker = ProcessWorker(db_path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start_reaping)
        self._thread.finished.connect(self._worker.deleteLater)
        self.requested.connect(self._worker.execute)
        self._worker.completed.connect(self._update)
        self._thread.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._loaded:
            self._request(ProcessRequest("refresh"))

    def _selected(self) -> ProcessEntry | None:
        rows = self._table.selectionModel().selectedRows()
        return self._entries[rows[0].row()] if rows else None

    @Slot()
    def _sync_buttons(self) -> None:
        available = not self._busy
        for button in (self._refresh, self._launch, self._demo):
            button.setEnabled(available)
        selected = self._selected()
        self._terminate.setEnabled(available and selected is not None and selected.owned)

    def _request(self, request: ProcessRequest) -> None:
        if not self._busy:
            self._busy = True
            self._status.setText("Выполняется…")
            self._sync_buttons()
            self.requested.emit(request)

    @Slot(object, str, int)
    def _update(self, entries: list[ProcessEntry] | None, message: str, launched_pid: int) -> None:
        self._busy = False
        if entries is not None:
            selected = self._selected()
            selected_pid = launched_pid or (selected.pid if selected is not None else None)
            selected_row = None
            self._table.clearSelection()
            self._entries = entries
            self._table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                memory = "Недоступно"
                if entry.memory_bytes is not None:
                    memory = f"{entry.memory_bytes / 1024**2:.1f} МиБ".replace(".", ",")
                cells = (
                    str(entry.pid),
                    entry.name or "Недоступно",
                    memory,
                    "System Monitor" if entry.owned else "—",
                )
                for column, text in enumerate(cells):
                    self._table.setItem(row, column, QTableWidgetItem(text))
                if entry.pid == selected_pid:
                    selected_row = row
            if selected_row is not None:
                self._table.selectRow(selected_row)
                if launched_pid:
                    self._table.scrollToItem(self._table.item(selected_row, 0))
            self._loaded = True
            message = message or f"Процессов в списке: {len(entries)}"
        self._status.setText(message)
        self._sync_buttons()

    @Slot()
    def _choose_executable(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Исполняемый файл", str(Path.home()))
        if path:
            self._request(ProcessRequest("launch", executable=path))

    @Slot()
    def _confirm_termination(self) -> None:
        entry = self._selected()
        if entry is None or not entry.owned:
            return
        dialog = QMessageBox(QMessageBox.Icon.Question, "Завершение процесса", "", parent=self)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(f"Завершить процесс «{entry.name or 'Без названия'}» (PID {entry.pid})?")
        terminate = dialog.addButton("Завершить", QMessageBox.ButtonRole.DestructiveRole)
        cancel = dialog.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        if dialog.clickedButton() == terminate:
            self._request(ProcessRequest("terminate", pid=entry.pid))

    @Slot()
    def stop(self) -> None:
        self._thread.quit()
        self._thread.wait()
