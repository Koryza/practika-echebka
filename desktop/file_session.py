"""Операции файловой вкладки и запись их результатов в SQLite."""

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Error as DatabaseError

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


class FileSession:
    """Хранит рабочую папку и выполняет запросы файловой вкладки."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path
        self._storage: Storage | None = None
        self._workspace: WorkspaceFiles | None = None
        self._directory: RelativePath = ()

    def execute(self, request: FileRequest) -> tuple[FileView | None, str]:
        message = ""
        view = None
        try:
            if self._storage is None:
                self._storage = Storage(self._db_path)
            if request.operation in OPERATIONS:
                message = self._mutate_and_log(request)
                view = self._view()
            else:
                view = self._navigate(request)
        except (OSError, WorkspaceError, DatabaseError) as error:
            detail = explain_file_error(error)
            message = f"{message} · {detail}" if message else detail
        return view, message

    def _navigate(self, request: FileRequest) -> FileView:
        if request.operation in {"restore", "root"}:
            root = (
                self._storage.setting("workspace_root")
                if request.operation == "restore"
                else request.name
            )
            if not root:
                return self._view()
            workspace = WorkspaceFiles(Path(root))
            entries = workspace.list_directory(())
            if request.operation == "root":
                self._storage.save_setting("workspace_root", str(workspace.root))
            self._workspace = workspace
            self._directory = ()
            return FileView(workspace.root, (), entries)
        if request.operation in {"enter", "up"}:
            target = (
                (*self._directory, request.name)
                if request.operation == "enter"
                else self._directory[:-1]
            )
            entries = self._workspace.list_directory(target)
            self._directory = target
            return FileView(self._workspace.root, target, entries)
        return self._view()

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
