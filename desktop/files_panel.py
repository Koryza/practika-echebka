from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .confirmation import confirm_action
from .storage import Storage
from .workspace_files import FileEntry, RelativePath, WorkspaceError, WorkspaceFiles, explain_file_error

OPERATIONS = {
    "create_file": "Файл создан",
    "create_folder": "Папка создана",
    "copy": "Копирование завершено",
    "move": "Перемещение завершено",
    "rename": "Объект переименован",
    "delete": "Объект удалён",
    "toggle_read_only": "Атрибут изменён",
}
KIND_LABELS = {
    "file": "Файл",
    "directory": "Папка",
    "link": "Символическая ссылка",
    "other": "Специальный объект",
}


@dataclass(frozen=True)
class FileRequest:
    operation: str
    name: str = ""
    target: str = ""


@dataclass(frozen=True)
class FileView:
    root: Path | None
    directory: RelativePath
    entries: list[FileEntry]


class FileWorker(QObject):
    completed = Signal(object, str)

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self._db_path = db_path
        self._storage: Storage | None = None
        self._workspace: WorkspaceFiles | None = None
        self._directory: RelativePath = ()

    @Slot(object)
    def execute(self, request: FileRequest) -> None:
        message = ""
        view = None
        try:
            if self._storage is None:
                self._storage = Storage(self._db_path)
            if request.operation in OPERATIONS:
                message = self._mutate_and_log(request)
            else:
                self._navigate(request)
            view = self._view()
        except (OSError, WorkspaceError, DatabaseError) as error:
            detail = explain_file_error(error)
            message = f"{message} · {detail}" if message else detail
        self.completed.emit(view, message)

    def _navigate(self, request: FileRequest) -> None:
        if request.operation in {"restore", "root"}:
            root = (
                self._storage.setting("workspace_root")
                if request.operation == "restore"
                else request.name
            )
            if not root:
                return
            workspace = WorkspaceFiles(Path(root))
            workspace.list_directory(())
            if request.operation == "root":
                self._storage.save_setting("workspace_root", str(workspace.root))
            self._workspace = workspace
            self._directory = ()
        elif request.operation in {"enter", "up"}:
            target = (
                (*self._directory, request.name)
                if request.operation == "enter"
                else self._directory[:-1]
            )
            self._workspace.list_directory(target)
            self._directory = target

    def _view(self) -> FileView:
        if self._workspace is None:
            return FileView(None, (), [])
        try:
            entries = self._workspace.list_directory(self._directory)
        except (FileNotFoundError, NotADirectoryError):
            entries = self._workspace.list_directory(())
            self._directory = ()
        return FileView(self._workspace.root, self._directory, entries)

    def _mutate_and_log(self, request: FileRequest) -> str:
        operation = request.operation
        description = str(self._workspace.root.joinpath(*self._directory, request.name))
        if request.target:
            description += f" → {request.target}"
        try:
            self._mutate(request)
        except (OSError, WorkspaceError) as error:
            message = explain_file_error(error)
            outcome = "error"
            description += f" · {message}"
        else:
            message = OPERATIONS[operation]
            outcome = "success"
        try:
            self._storage.log_event("files", operation, description, outcome)
        except DatabaseError:
            message += " · Не удалось записать событие в журнал"
        return message

    def _mutate(self, request: FileRequest) -> None:
        workspace, directory = self._workspace, self._directory
        operation, name = request.operation, request.name
        if operation in {"copy", "move"}:
            try:
                destination = Path(request.target).relative_to(workspace.root).parts
            except ValueError as error:
                raise WorkspaceError("Выберите папку внутри рабочего каталога") from error
            if operation == "copy":
                workspace.copy(directory, name, destination)
            else:
                workspace.move(directory, name, destination, name)
        elif operation == "rename":
            workspace.move(directory, name, directory, request.target)
        elif operation in {"create_file", "create_folder"}:
            workspace.create(directory, name, folder=operation == "create_folder")
        elif operation == "delete":
            workspace.delete(directory, name)
        elif operation == "toggle_read_only":
            workspace.toggle_read_only(directory, name)


def _date(timestamp: float | None) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y %H:%M:%S") if timestamp is not None else "Недоступно"


class FilesPanel(QWidget):
    requested = Signal(object)
    workspace_changed = Signal(str)
    workspace_selected = Signal(str, str)

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self.setObjectName("dashboard")
        self._view = FileView(None, (), [])
        self._busy = False
        self._active_request = None
        self._pending_root = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(10)
        heading = QLabel("Файлы и папки")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        navigation = QHBoxLayout()
        self._root_button = QPushButton("Выбрать рабочую папку…")
        self._root_button.clicked.connect(self._choose_root)
        self._up_button = QPushButton("Вверх")
        self._up_button.clicked.connect(lambda: self._request(FileRequest("up")))
        self._refresh_button = QPushButton("Обновить")
        self._refresh_button.clicked.connect(lambda: self._request(FileRequest("refresh")))
        for button in (self._root_button, self._up_button, self._refresh_button):
            navigation.addWidget(button)
        navigation.addStretch()
        layout.addLayout(navigation)

        self._path = QLabel("Выбери рабочую папку, чтобы открыть список файлов.")
        self._path.setTextFormat(Qt.TextFormat.PlainText)
        self._path.setWordWrap(True)
        self._path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._path)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Имя", "Тип", "Размер", "Изменён"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(2, 105)
        self._table.setColumnWidth(3, 158)
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._selection_changed)
        self._table.cellDoubleClicked.connect(self._open_entry)
        layout.addWidget(self._table, 1)

        actions = QHBoxLayout()
        self._actions = {}
        for operation, label in (
            ("create_file", "Новый файл"),
            ("create_folder", "Новая папка"),
            ("copy", "Копировать…"),
            ("move", "Переместить…"),
            ("rename", "Переименовать…"),
            ("delete", "Удалить…"),
            ("toggle_read_only", "Только чтение"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, action=operation: self._action(action))
            self._actions[operation] = button
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        self._properties = QLabel("Выбери файл, чтобы посмотреть его свойства.")
        self._properties.setTextFormat(Qt.TextFormat.PlainText)
        self._properties.setWordWrap(True)
        self._properties.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._properties)
        self._status = QLabel()
        self._status.setObjectName("status")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._thread = QThread(self)
        self._worker = FileWorker(db_path)
        self._worker.moveToThread(self._thread)
        self._thread.finished.connect(self._worker.deleteLater)
        self.requested.connect(self._worker.execute)
        self._worker.completed.connect(self._update_view)
        self._thread.start()
        self._request(FileRequest("restore"))

    def _selected(self) -> FileEntry | None:
        selected = self._table.selectedItems()
        return self._view.entries[selected[0].row()] if selected else None

    def _sync_buttons(self) -> None:
        enabled = not self._busy
        self._root_button.setEnabled(enabled)
        self._up_button.setEnabled(enabled and bool(self._view.directory))
        has_workspace = enabled and self._view.root is not None
        self._refresh_button.setEnabled(has_workspace)
        self._table.setEnabled(enabled)
        entry = self._selected()
        for operation, button in self._actions.items():
            if operation in {"create_file", "create_folder"}:
                active = has_workspace
            elif operation == "toggle_read_only":
                active = enabled and entry is not None and entry.kind == "file"
            else:
                active = enabled and entry is not None and entry.kind in {"file", "directory"}
            button.setEnabled(active)

    @Slot()
    def _selection_changed(self) -> None:
        item = self._selected()
        if item is None or self._view.root is None:
            self._properties.setText("Выбери файл, чтобы посмотреть его свойства.")
        else:
            path = self._view.root.joinpath(*self._view.directory, item.name)
            extension = Path(item.name).suffix if item.kind == "file" else ""
            attribute = "только чтение" if item.read_only else "запись для владельца разрешена"
            self._properties.setText(
                f"{item.name} · Расширение {extension or '—'}\n{path}\n"
                f"Создан {_date(item.created_at)} · Изменён {_date(item.modified_at)} · {attribute}"
            )
        self._sync_buttons()

    @Slot(object, str)
    def _update_view(self, view: FileView | None, message: str) -> None:
        self._busy = False
        self._status.setText(message)
        previous_root = self._view.root
        if view is not None:
            self._table.clearSelection()
            self._table.setRowCount(0)
            self._view = view
            if view.root is not None:
                self._path.setText(f"Текущая папка · {view.root.joinpath(*view.directory)}")
            self._table.setRowCount(len(view.entries))
            for row, item in enumerate(view.entries):
                size = f"{item.size:,} байт".replace(",", " ") if item.kind == "file" else "—"
                values = (item.name, KIND_LABELS[item.kind], size, _date(item.modified_at))
                for column, value in enumerate(values):
                    self._table.setItem(row, column, QTableWidgetItem(value))
        self._selection_changed()
        if self._view.root != previous_root:
            self.workspace_changed.emit(str(self._view.root or ""))
        if self._active_request is not None and self._active_request.operation == "root":
            self.workspace_selected.emit(self._active_request.name, message)
        self._active_request = None
        if self._pending_root is not None:
            path = self._pending_root
            self._pending_root = None
            self.set_workspace_root(path)

    def _request(self, request: FileRequest) -> None:
        if not self._busy:
            self._busy = True
            self._active_request = request
            self._status.setText("Выполняется…")
            self._sync_buttons()
            self.requested.emit(request)

    def _choose_root(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Рабочая папка", str(self._view.root or Path.home()))
        if chosen:
            self.set_workspace_root(chosen)

    @Slot(str)
    def set_workspace_root(self, directory: str) -> None:
        if self._busy:
            self._pending_root = directory
        else:
            self._request(FileRequest("root", directory))

    @Slot(int, int)
    def _open_entry(self, row: int, column: int) -> None:
        item = self._view.entries[row]
        if item.kind == "directory":
            self._request(FileRequest("enter", item.name))

    def _action(self, operation: str) -> None:
        item = self._selected()
        name = item.name if item is not None else ""
        target = ""
        if operation in {"create_file", "create_folder", "rename"}:
            caption = {
                "create_file": "Имя нового файла",
                "create_folder": "Имя новой папки",
                "rename": "Новое имя",
            }[operation]
            value, accepted = QInputDialog.getText(
                self, caption, "Имя", text=name if operation == "rename" else ""
            )
            if not accepted:
                return
            if operation == "rename":
                if value == name:
                    return
                target = value
            else:
                name = value
        elif operation in {"copy", "move"}:
            caption = "Куда скопировать?" if operation == "copy" else "Куда переместить?"
            target = QFileDialog.getExistingDirectory(
                self, caption, str(self._view.root.joinpath(*self._view.directory))
            )
            if not target:
                return
        elif operation == "delete":
            suffix = " Папка будет удалена вместе с содержимым." if item.kind == "directory" else ""
            if not confirm_action(self, "Удаление", f"Удалить «{name}»?{suffix}", "Удалить"):
                return
        self._request(FileRequest(operation, name, target))

    @Slot()
    def stop(self) -> None:
        self._thread.quit()
        self._thread.wait()
