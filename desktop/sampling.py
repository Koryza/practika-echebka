from pathlib import Path
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .monitor import SystemMonitor, SystemSnapshot
from .settings import Settings
from .storage import Storage


class SampleWorker(QObject):
    sampled = Signal(object)
    failed = Signal()
    settings_loaded = Signal(object)
    storage_error = Signal(str)

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self._db_path = db_path
        self._monitor: SystemMonitor | None = None
        self._storage: Storage | None = None
        self._latest: SystemSnapshot | None = None
        self._saved: SystemSnapshot | None = None

    @Slot()
    def initialize(self) -> None:
        self._record_timer = QTimer(self)
        self._record_timer.timeout.connect(self._record)
        try:
            self._storage = Storage(self._db_path)
            settings = self._storage.load_settings()
        except (DatabaseError, OSError):
            settings = Settings()
            self.storage_error.emit("Не удалось загрузить настройки. Применены исходные значения")
        self.configure(settings)
        self.settings_loaded.emit(settings)

    @Slot(object)
    def configure(self, settings: Settings) -> None:
        interval = settings.record_seconds * 1000
        if self._record_timer.interval() != interval:
            self._record_timer.start(interval)

    @Slot()
    def sample(self) -> None:
        try:
            if self._monitor is None:
                self._monitor = SystemMonitor()
            snapshot = self._monitor.sample()
        except OSError:
            self.failed.emit()
        else:
            self._latest = snapshot
            self.sampled.emit(snapshot)

    @Slot()
    def _record(self) -> None:
        snapshot = self._latest
        if snapshot is None or snapshot is self._saved:
            return
        cpu = snapshot.cpu_usage_percent
        memory = snapshot.memory.usage_percent if snapshot.memory is not None else None
        if cpu is None and memory is None:
            return
        try:
            if self._storage is None:
                self._storage = Storage(self._db_path)
            self._storage.save_metric(int(snapshot.timestamp.timestamp() * 1000), cpu, memory)
        except (DatabaseError, OSError):
            self.storage_error.emit("Не удалось сохранить замер в SQLite")
        else:
            self._saved = snapshot
