"""Файловые операции относительно открытого рабочего каталога macOS."""

import ctypes
import errno
import os
import shutil
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

RelativePath = tuple[str, ...]
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
RENAME_EXCL = 0x00000004  # <sys/stdio.h> macOS


class WorkspaceError(ValueError):
    pass


@dataclass(frozen=True)
class FileEntry:
    name: str
    kind: str
    size: int
    modified_at: float
    created_at: float | None
    read_only: bool


def _check_name(name: str) -> None:
    if not name or name in {".", ".."} or any(char in name for char in "/\0:"):
        raise WorkspaceError("Укажите допустимое имя без разделителей пути")


def _kind(mode: int) -> str:
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISLNK(mode):
        return "link"
    return "other"


def _entry(name: str, info: os.stat_result) -> FileEntry:
    return FileEntry(
        name,
        _kind(info.st_mode),
        info.st_size,
        info.st_mtime,
        getattr(info, "st_birthtime", None),
        not bool(info.st_mode & stat.S_IWUSR),
    )


def _rename_exclusive(src_fd: int, source: str, dst_fd: int, target: str) -> None:
    rename = ctypes.CDLL(None, use_errno=True).renameatx_np
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(src_fd, os.fsencode(source), dst_fd, os.fsencode(target), RENAME_EXCL) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), target)


class WorkspaceFiles:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        with self._directory_from("/", self.root.parts[1:]) as directory:
            info = os.fstat(directory)
            self._root_identity = info.st_dev, info.st_ino

    @staticmethod
    @contextmanager
    def _directory_from(start: str | int, parts: RelativePath, forbidden=None):
        descriptor = os.dup(start) if isinstance(start, int) else os.open(start, DIRECTORY_FLAGS)
        try:
            for component in parts:
                _check_name(component)
                child = os.open(component, DIRECTORY_FLAGS, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
                if forbidden is not None:
                    info = os.fstat(descriptor)
                    if (info.st_dev, info.st_ino) == forbidden:
                        raise WorkspaceError("Нельзя скопировать папку в неё саму или в её подпапку")
            yield descriptor
        finally:
            os.close(descriptor)

    @contextmanager
    def _directory(self, parts: RelativePath, forbidden=None):
        with self._directory_from("/", self.root.parts[1:]) as root:
            info = os.fstat(root)
            if (info.st_dev, info.st_ino) != self._root_identity:
                raise WorkspaceError("Рабочая папка изменилась. Выберите её снова")
            with self._directory_from(root, parts, forbidden) as directory:
                yield directory

    def list_directory(self, parts: RelativePath) -> list[FileEntry]:
        with self._directory(parts) as directory:
            with os.scandir(directory) as entries:
                result = []
                for item in entries:
                    try:
                        info = item.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    result.append(_entry(item.name, info))
        return sorted(result, key=lambda item: (item.kind != "directory", item.name.casefold()))

    def create(self, directory: RelativePath, name: str, *, folder: bool) -> None:
        _check_name(name)
        with self._directory(directory) as descriptor:
            if folder:
                os.mkdir(name, dir_fd=descriptor)
            else:
                os.close(os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644, dir_fd=descriptor))

    @staticmethod
    def _mutable_info(descriptor: int, name: str) -> os.stat_result:
        _check_name(name)
        info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if _kind(info.st_mode) not in {"file", "directory"}:
            raise WorkspaceError("Операция доступна только для обычных файлов и папок")
        return info

    def move(
        self, directory: RelativePath, name: str, destination: RelativePath, target: str
    ) -> None:
        _check_name(target)
        with self._directory(directory) as src_fd, self._directory(destination) as dst_fd:
            self._mutable_info(src_fd, name)
            _rename_exclusive(src_fd, name, dst_fd, target)

    def copy(self, directory: RelativePath, name: str, destination: RelativePath) -> None:
        with self._directory(directory) as src_fd:
            source = self._mutable_info(src_fd, name)
            forbidden = (source.st_dev, source.st_ino) if stat.S_ISDIR(source.st_mode) else None
            with self._directory(destination, forbidden) as dst_fd:
                self._copy_entry(src_fd, dst_fd, name)

    def _copy_entry(self, src_fd: int, dst_fd: int, name: str) -> None:
        info = self._mutable_info(src_fd, name)
        if stat.S_ISDIR(info.st_mode):
            with self._directory_from(src_fd, (name,)) as child_source:
                os.mkdir(name, dir_fd=dst_fd)
                try:
                    with self._directory_from(dst_fd, (name,)) as child_target:
                        for item in os.listdir(child_source):
                            self._copy_entry(child_source, child_target, item)
                except (OSError, WorkspaceError):
                    shutil.rmtree(name, dir_fd=dst_fd)
                    raise
            return

        with os.fdopen(os.open(name, FILE_FLAGS, dir_fd=src_fd), "rb") as source:
            source_info = os.fstat(source.fileno())
            if not stat.S_ISREG(source_info.st_mode):
                raise WorkspaceError("Источник перестал быть обычным файлом")
            create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            target_fd = os.open(name, create_flags, 0o600, dir_fd=dst_fd)
            try:
                with os.fdopen(target_fd, "wb") as target:
                    shutil.copyfileobj(source, target)
                    os.fchmod(target.fileno(), source_info.st_mode & 0o777)
            except OSError:
                os.unlink(name, dir_fd=dst_fd)
                raise

    def delete(self, directory: RelativePath, name: str) -> None:
        with self._directory(directory) as descriptor:
            info = self._mutable_info(descriptor, name)
            if stat.S_ISDIR(info.st_mode):
                shutil.rmtree(name, dir_fd=descriptor)
            else:
                os.unlink(name, dir_fd=descriptor)

    def toggle_read_only(self, directory: RelativePath, name: str) -> None:
        _check_name(name)
        with self._directory(directory) as parent:
            descriptor = os.open(name, FILE_FLAGS, dir_fd=parent)
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise WorkspaceError("Атрибут доступен только для обычного файла без жёстких ссылок")
                os.fchmod(descriptor, stat.S_IMODE(info.st_mode) ^ stat.S_IWUSR)
            finally:
                os.close(descriptor)


def explain_file_error(error: Exception) -> str:
    if isinstance(error, WorkspaceError):
        return str(error)
    if isinstance(error, FileExistsError):
        return "Объект с таким именем уже существует"
    if isinstance(error, FileNotFoundError):
        return "Файл или папка больше недоступны"
    if isinstance(error, PermissionError):
        return "Недостаточно прав для операции"
    if isinstance(error, OSError):
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            return "Путь содержит ссылку или недоступную папку"
        if error.errno == errno.EXDEV:
            return "Перемещение между томами недоступно. Используйте копирование"
        if error.errno == errno.EINVAL:
            return "Недопустимый путь для операции"
        return f"Не удалось выполнить файловую операцию ({error.strerror})"
    return "Не удалось открыть базу данных или сохранить запись"
