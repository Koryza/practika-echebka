"""Просмотр процессов macOS и управление дочерними процессами приложения."""

import errno
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import psutil

DEMO_EXECUTABLE = Path("/bin/sleep")
DEMO_DURATION_SECONDS = "120"


class ProcessError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessEntry:
    pid: int
    name: str | None
    memory_bytes: int | None
    owned: bool


class ProcessManager:
    def __init__(self) -> None:
        self._children: dict[int, subprocess.Popen] = {}

    def reap_finished(self) -> None:
        for pid, child in tuple(self._children.items()):
            if child.poll() is not None:
                del self._children[pid]

    def list_processes(self) -> list[ProcessEntry]:
        self.reap_finished()
        entries = []
        for process in psutil.process_iter(("pid", "name", "memory_info"), ad_value=None):
            data = process.info
            memory = data["memory_info"]
            pid = data["pid"]
            entries.append(
                ProcessEntry(
                    pid=pid,
                    name=data["name"],
                    memory_bytes=memory.rss if memory is not None else None,
                    owned=pid in self._children,
                )
            )
        return sorted(entries, key=lambda entry: entry.pid)

    def launch(self, executable: Path) -> int:
        if not executable.is_absolute() or not executable.is_file():
            raise ProcessError("Выберите существующий исполняемый файл")
        return self._launch([os.fspath(executable)], executable.parent)

    def launch_demo(self) -> int:
        return self._launch([os.fspath(DEMO_EXECUTABLE), DEMO_DURATION_SECONDS], None)

    def _launch(self, command: list[str], directory: Path | None) -> int:
        self.reap_finished()
        child = subprocess.Popen(
            command,
            cwd=directory,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._children[child.pid] = child
        return child.pid

    def terminate(self, pid: int) -> None:
        child = self._children.get(pid)
        if child is None:
            raise ProcessError("Завершать можно только процессы, запущенные через System Monitor")
        if child.poll() is not None:
            del self._children[pid]
            raise ProcessError("Процесс уже завершился")
        child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired as error:
            raise ProcessError("Процесс не завершился после запроса") from error
        del self._children[pid]


def explain_process_error(error: Exception) -> str:
    if isinstance(error, ProcessError):
        return str(error)
    if isinstance(error, FileNotFoundError):
        return "Исполняемый файл больше недоступен"
    if isinstance(error, (PermissionError, psutil.AccessDenied)):
        return "Недостаточно прав для операции или у файла нет разрешения на запуск"
    if isinstance(error, ProcessLookupError):
        return "Процесс уже завершился"
    if isinstance(error, OSError) and error.errno == errno.ENOEXEC:
        return "macOS не распознала формат исполняемого файла"
    return "Не удалось выполнить операцию с процессами"
