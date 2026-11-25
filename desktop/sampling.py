from pathlib import Path
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .alerts import AlertSettings, threshold_alerts
from .monitor import SystemMonitor, SystemSnapshot
from .settings import Settings
from .storage import Storage


class SampleWorker(QObject):
    sampled = Signal(object)
    failed = Signal()
    settings_loaded = Signal(object)
    storage_error = Signal(str)
    alert_settings_loaded = Signal(object)
    alert_settings_saved = Signal(object, str)
    alerts_created = Signal(object)
    alert_history_loaded = Signal(int, object, str)

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self._db_path = db_path
        self._monitor: SystemMonitor | None = None
        self._storage: Storage | None = None
        self._latest: SystemSnapshot | None = None
        self._saved: SystemSnapshot | None = None
        self._alert_settings = AlertSettings()

    @Slot()
    def initialize(self) -> None:
        self._record_timer = QTimer(self)
        self._record_timer.timeout.connect(self._record)
        try:
            storage = self._database()
            settings = storage.load_settings()
            self._alert_settings = storage.load_alert_settings()
        except (DatabaseError, OSError):
            settings = Settings()
            self.storage_error.emit("Не удалось загрузить настройки. Применены исходные значения")
        self.configure(settings)
        self.settings_loaded.emit(settings)
        self.alert_settings_loaded.emit(self._alert_settings)

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
            self._check_alerts(snapshot)

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
            self._database().save_metric(int(snapshot.timestamp.timestamp() * 1000), cpu, memory)
        except (DatabaseError, OSError):
            self.storage_error.emit("Не удалось сохранить замер в SQLite")
        else:
            self._saved = snapshot


    def _database(self) -> Storage:
        if self._storage is None:
            self._storage = Storage(self._db_path)
        return self._storage

    def _check_alerts(self, snapshot: SystemSnapshot) -> None:
        candidates = threshold_alerts(snapshot, self._alert_settings)
        if not candidates:
            return
        try:
            created = self._database().record_alerts(candidates, self._alert_settings.repeat_seconds)
        except (DatabaseError, OSError):
            self.storage_error.emit("Не удалось записать пороговые уведомления")
        else:
            if created:
                self.alerts_created.emit(created)

    @Slot(object)
    def save_alert_settings(self, settings: AlertSettings) -> None:
        try:
            self._database().save_alert_settings(settings)
        except (DatabaseError, OSError):
            self.alert_settings_saved.emit(None, "Не удалось сохранить пороги и интервал")
        else:
            self._alert_settings = settings
            self.alert_settings_saved.emit(settings, "Настройки уведомлений сохранены")

    @Slot(int, object)
    def load_alert_history(self, page: int, through_id: int | None) -> None:
        try:
            history = self._database().alerts(page, through_id)
        except (DatabaseError, OSError):
            self.alert_history_loaded.emit(page, None, "Не удалось загрузить историю уведомлений")
        else:
            self.alert_history_loaded.emit(page, history, "")
