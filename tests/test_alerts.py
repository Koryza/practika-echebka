import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

from desktop.alerts import Alert, AlertSettings, threshold_alerts
from desktop.monitor import CpuInfo, DiskUsage, MemoryUsage, SystemSnapshot
from desktop.settings import Settings
from desktop.storage import SCHEMA, Storage


class ThresholdTests(unittest.TestCase):
    def test_exceedance_is_strict_and_disks_are_independent(self):
        now = datetime(2026, 11, 25, 12, tzinfo=UTC)
        snapshot = SystemSnapshot(
            "Test",
            now,
            CpuInfo("M2", 8, 8),
            90.0,
            MemoryUsage(1000, 901, 99, 90.1),
            (
                DiskUsage("/", None, usage_percent=12),
                DiskUsage("/Volumes/A", None, usage_percent=91),
                DiskUsage("/Volumes/B", None, usage_percent=95),
                DiskUsage("/Volumes/Offline", None),
            ),
        )
        alerts = threshold_alerts(snapshot, AlertSettings())
        self.assertEqual(
            [(x.resource, x.target, x.measured) for x in alerts],
            [("memory", "", 90.1), ("disk", "/Volumes/A", 91), ("disk", "/Volumes/B", 95)],
        )
        cpu_alerts = threshold_alerts(replace(snapshot, cpu_usage_percent=99), AlertSettings())
        self.assertEqual(cpu_alerts[0], Alert(int(now.timestamp() * 1000), "cpu", "", 99, 90))

    def test_invalid_settings_and_missing_measurements(self):
        snapshot = SystemSnapshot("Test", datetime.now(UTC), CpuInfo(None, None, None), None, None, ())
        self.assertEqual(threshold_alerts(snapshot, AlertSettings()), [])
        for changed in (
            {"cpu_threshold": 101}, {"memory_threshold": -1}, {"disk_threshold": 90.5},
            {"repeat_seconds": 4}, {"repeat_seconds": 3601},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                AlertSettings(**changed)


class AlertStorageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "system-monitor.sqlite3"

    def test_recent_duplicates_suppressed_after_reopening_and_exact_boundary_allowed(self):
        storage = Storage(self.path)
        first = Alert(1_000_000, "disk", "/Volumes/A", 95, 90)
        other = replace(first, target="/Volumes/B")
        cpu = Alert(first.recorded_at, "cpu", "", 97, 90)
        self.assertEqual(storage.record_alerts([first, other, cpu], 60), [first, other, cpu])

        reopened = Storage(self.path)
        too_soon = replace(first, recorded_at=first.recorded_at + 59_999)
        self.assertEqual(reopened.record_alerts([too_soon], 60), [])
        next_alert = replace(first, recorded_at=first.recorded_at + 60_000)
        self.assertEqual(reopened.record_alerts([next_alert], 60), [next_alert])
        self.assertEqual(len(reopened.alerts(0).rows), 4)

    def test_two_writers_do_not_duplicate_the_same_alert(self):
        storages = [Storage(self.path), Storage(self.path)]
        barrier = Barrier(len(storages))
        alert = Alert(1_000_000, "cpu", "", 98, 90)

        def save(storage):
            barrier.wait(timeout=2)
            return storage.record_alerts([alert], 60)

        with ThreadPoolExecutor(max_workers=2) as workers:
            self.assertCountEqual(workers.map(save, storages), [[alert], []])

    def test_old_database_preserves_history_and_uses_default_thresholds(self):
        old_schema = SCHEMA.read_text().split("CREATE TABLE IF NOT EXISTS resource_alerts", 1)[0]
        with sqlite3.connect(self.path) as old:
            old.executescript(old_schema)
            old.execute("INSERT INTO resource_metrics (recorded_at, cpu_usage) VALUES (?, ?)", (10, 30))
            old.execute("INSERT INTO settings VALUES (?, ?)", ("api_port", "9090"))
        storage = Storage(self.path)
        self.assertEqual(storage.metrics(0).rows, [(10, 30, None)])
        self.assertEqual(storage.alerts(0).rows, [])
        self.assertEqual(storage.load_alert_settings(), AlertSettings())
        self.assertEqual(storage.load_settings().api_port, 9090)

        storage.save_alert_settings(AlertSettings(79, 83, 97, 45))
        storage.save_settings(Settings(api_port=8090))
        reopened = Storage(self.path)
        self.assertEqual(reopened.load_alert_settings(), AlertSettings(79, 83, 97, 45))
        self.assertEqual(reopened.load_settings().api_port, 8090)

    def test_failed_batch_does_not_save_partial_history(self):
        storage = Storage(self.path)
        valid = Alert(1_000_000, "cpu", "", 97, 90)
        invalid = replace(valid, resource="invalid")
        with self.assertRaises(sqlite3.IntegrityError):
            storage.record_alerts([valid, invalid], 60)
        self.assertEqual(storage.alerts(0).rows, [])
        self.assertEqual(storage.record_alerts([valid], 60), [valid])
