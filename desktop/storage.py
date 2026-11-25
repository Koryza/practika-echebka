"""Общее хранилище настроек и событий System Monitor."""

import sqlite3
from contextlib import closing
from pathlib import Path
from time import time_ns

SCHEMA = Path(__file__).resolve().parents[1] / "database" / "schema.sql"


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
