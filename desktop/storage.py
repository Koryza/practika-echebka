"""Общее хранилище настроек и событий System Monitor."""

import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time_ns

from .alerts import ALERT_LIMITS, Alert, AlertSettings
from .settings import SETTINGS_LIMITS, Settings

SCHEMA = Path(__file__).resolve().parents[1] / "database" / "schema.sql"

PAGE_SIZE = 100


@dataclass(frozen=True)
class HistoryPage:
    rows: list[tuple]
    has_next: bool
    through_id: int


class Storage:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = Path.home() / "Library" / "Application Support" / "System Monitor" / "system-monitor.sqlite3"
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(SCHEMA.read_text(encoding="utf-8"))

    def setting(self, key: str) -> str | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def save_setting(self, key: str, value: str) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def log_event(self, category: str, operation: str, description: str, status: str) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO events (created_at, category, operation, description, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (time_ns() // 1_000_000, category, operation, description, status),
            )

    def load_settings(self) -> Settings:
        return Settings(**self._load_numeric_settings(SETTINGS_LIMITS))

    def load_alert_settings(self) -> AlertSettings:
        return AlertSettings(**self._load_numeric_settings(ALERT_LIMITS))

    def _load_numeric_settings(self, limits: dict[str, tuple[int, int]]) -> dict[str, int]:
        with closing(sqlite3.connect(self.path)) as db:
            stored = dict(db.execute("SELECT key, value FROM settings"))
        values = {}
        for key, (minimum, maximum) in limits.items():
            try:
                value = int(stored.get(key, ""))
            except ValueError:
                continue
            if minimum <= value <= maximum:
                values[key] = value
        return values

    def save_settings(self, settings: Settings) -> None:
        self._save_numeric_settings(asdict(settings))

    def save_alert_settings(self, settings: AlertSettings) -> None:
        self._save_numeric_settings(asdict(settings))

    def _save_numeric_settings(self, values: dict[str, int]) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                ((key, str(value)) for key, value in values.items()),
            )

    def save_metric(self, recorded_at: int, cpu: float | None, memory: float | None) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO resource_metrics (recorded_at, cpu_usage, memory_usage) VALUES (?, ?, ?)",
                (recorded_at, cpu, memory),
            )

    def metrics(
        self,
        page: int,
        period: tuple[int, int] | None = None,
        through_id: int | None = None,
    ) -> HistoryPage:
        query = "SELECT recorded_at, cpu_usage, memory_usage FROM resource_metrics WHERE id <= ? "
        if period is not None:
            query += "AND recorded_at >= ? AND recorded_at < ? "
        query += "ORDER BY recorded_at DESC, id DESC LIMIT ? OFFSET ?"
        return self._page(
            query, "SELECT MAX(id) FROM resource_metrics", page, through_id, period or ()
        )

    def events(self, page: int, through_id: int | None = None) -> HistoryPage:
        return self._page(
            "SELECT created_at, category, operation, description, status FROM events "
            "WHERE id <= ? ORDER BY id DESC LIMIT ? OFFSET ?",
            "SELECT MAX(id) FROM events",
            page,
            through_id,
        )

    def record_alerts(self, alerts: list[Alert], repeat_seconds: int) -> list[Alert]:
        created = []
        with closing(sqlite3.connect(self.path)) as db, db:
            for alert in alerts:
                # Проверка паузы и вставка выполняются одним запросом в транзакции.
                cursor = db.execute(
                    "INSERT INTO resource_alerts (recorded_at, resource, target, measured, threshold) "
                    "SELECT ?, ?, ?, ?, ? WHERE NOT EXISTS ("
                    "SELECT 1 FROM resource_alerts WHERE resource = ? AND target = ? AND recorded_at > ?"
                    ")",
                    (
                        alert.recorded_at, alert.resource, alert.target, alert.measured, alert.threshold,
                        alert.resource, alert.target, alert.recorded_at - repeat_seconds * 1000,
                    ),
                )
                if cursor.rowcount == 1:
                    created.append(alert)
        return created

    def alerts(self, page: int, through_id: int | None = None) -> HistoryPage:
        return self._page(
            "SELECT recorded_at, resource, target, measured, threshold FROM resource_alerts "
            "WHERE id <= ? ORDER BY id DESC LIMIT ? OFFSET ?",
            "SELECT MAX(id) FROM resource_alerts",
            page,
            through_id,
        )

    def _page(
        self,
        query: str,
        max_id_query: str,
        page: int,
        through_id: int | None,
        parameters: tuple = (),
    ) -> HistoryPage:
        with closing(sqlite3.connect(self.path)) as db:
            if through_id is None:
                through_id = db.execute(max_id_query).fetchone()[0] or 0
            rows = db.execute(
                query, (through_id, *parameters, PAGE_SIZE + 1, page * PAGE_SIZE)
            ).fetchall()
        return HistoryPage(rows[:PAGE_SIZE], len(rows) > PAGE_SIZE, through_id)

    def clear_metrics(self) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM resource_metrics")

    def clear_events(self) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM events")
