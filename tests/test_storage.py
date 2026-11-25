import sqlite3
import tempfile
import unittest
from pathlib import Path

from desktop.settings import Settings
from desktop.storage import PAGE_SIZE, Storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "storage.sqlite3"
        self.storage = Storage(self.path)

    def test_metrics_are_persisted_and_filtered_by_half_open_period(self):
        self.storage.save_metric(1000, 1, None)
        self.storage.save_metric(2000, None, 25)
        self.storage.save_metric(3000, 2, 30)
        self.storage.save_metric(4000, 3, 40)
        reopened = Storage(self.path)
        self.assertEqual(
            reopened.metrics(0, (2000, 4000)).rows,
            [(3000, 2, 30), (2000, None, 25)],
        )
        self.assertEqual(len(reopened.metrics(0).rows), 4)

    def test_pages_stay_consistent_after_new_metrics_are_saved(self):
        for index in range(PAGE_SIZE + 1):
            self.storage.save_metric(1000, index % 101, 30)
        first = self.storage.metrics(0)
        self.storage.save_metric(2000, 99, 30)
        last = self.storage.metrics(1, through_id=first.through_id)
        self.assertEqual(self.storage.metrics(0).rows[0], (2000, 99, 30))
        self.assertEqual(len(first.rows), PAGE_SIZE)
        self.assertTrue(first.has_next)
        self.assertEqual(last.rows, [(1000, 0, 30)])
        self.assertFalse(last.has_next)
        self.assertEqual(first.rows[-1][1], 1)

    def test_settings_persist_without_overwriting_the_workspace(self):
        self.storage.save_setting("workspace_root", "/tmp/workspace")
        settings = Settings(refresh_seconds=3, record_seconds=7, api_port=9000)
        self.storage.save_settings(settings)
        reopened = Storage(self.path)
        self.assertEqual(reopened.load_settings(), settings)
        self.assertEqual(reopened.setting("workspace_root"), "/tmp/workspace")

    def test_invalid_settings_are_rejected_and_older_data_has_defaults(self):
        for invalid in (0, 3601, 1.5):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                Settings(refresh_seconds=invalid)
        self.storage.save_setting("refresh_seconds", "bad-value")
        self.storage.save_setting("record_seconds", "5")
        self.storage.save_setting("api_port", "70000")
        self.assertEqual(self.storage.load_settings(), Settings(record_seconds=5))

    def test_clearing_metrics_or_events_leaves_other_data_intact(self):
        description = "Папка 'Документы'"
        self.storage.log_event("files", "rename", description, "success")
        self.storage.save_metric(1000, 60, 70)
        self.storage.save_setting("workspace_root", "/tmp/files")
        self.storage.clear_metrics()
        self.assertEqual(self.storage.metrics(0).rows, [])
        self.assertEqual(self.storage.events(0).rows[0][3], description)
        self.storage.save_metric(2000, 70, 80)
        self.storage.clear_events()
        self.assertEqual(self.storage.events(0).rows, [])
        self.assertEqual(self.storage.metrics(0).rows, [(2000, 70, 80)])
        self.assertEqual(self.storage.setting("workspace_root"), "/tmp/files")

    def test_metric_constraints_reject_invalid_values(self):
        for cpu, memory in ((101, 40), (None, None), (-1, 1)):
            with self.subTest(cpu=cpu, memory=memory), self.assertRaises(sqlite3.IntegrityError):
                self.storage.save_metric(1000, cpu, memory)
