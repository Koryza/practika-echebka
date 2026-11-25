import unittest
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import patch

import psutil

from desktop.monitor import SystemMonitor


class SystemMonitorTests(unittest.TestCase):
    @patch("desktop.monitor.psutil.disk_partitions", return_value=[])
    @patch("desktop.monitor.psutil.cpu_percent", side_effect=[14.0, 30.0])
    @patch("desktop.monitor.psutil.cpu_count", side_effect=[8, 4])
    def test_samples_refresh_cpu_without_reloading_hardware(
        self, cpu_count, cpu_percent, disk_partitions
    ):
        with patch("desktop.monitor._cpu_model", return_value="Test CPU") as cpu_model:
            monitor = SystemMonitor()
            first = monitor.sample()
            second = monitor.sample()

        self.assertEqual(first.cpu.model, "Test CPU")
        self.assertEqual((first.cpu.logical_cores, first.cpu.physical_cores), (8, 4))
        self.assertEqual((first.cpu_usage_percent, second.cpu_usage_percent), (14.0, 30.0))
        self.assertIs(second.timestamp.tzinfo, UTC)
        self.assertIs(first.cpu, second.cpu)
        self.assertEqual(cpu_count.call_count, 2)
        cpu_model.assert_called_once()
        cpu_percent.assert_called_with(interval=0.1)

    def test_memory_usage_uses_available_memory(self):
        memory = SimpleNamespace(total=1000, available=400, used=450, percent=60.0)
        with patch("desktop.monitor.psutil.virtual_memory", return_value=memory):
            snapshot = SystemMonitor().sample()

        self.assertEqual(snapshot.memory.total_bytes, 1000)
        self.assertEqual(snapshot.memory.used_bytes, 600)
        self.assertEqual(snapshot.memory.available_bytes, 400)
        self.assertEqual(snapshot.memory.usage_percent, 60.0)

    def test_missing_disk_does_not_hide_other_disks(self):
        root = SimpleNamespace(mountpoint="/", device="/dev/root")
        removable = SimpleNamespace(mountpoint="/Volumes/Test", device="/dev/test")
        root_usage = SimpleNamespace(total=1000, used=400, free=600, percent=40.0)
        with (
            patch("desktop.monitor.psutil.disk_partitions", return_value=[removable, root]),
            patch(
                "desktop.monitor.psutil.disk_usage",
                side_effect=[root_usage, FileNotFoundError("Unmounted")],
            ) as disk_usage,
        ):
            snapshot = SystemMonitor().sample()

        self.assertEqual([disk.mountpoint for disk in snapshot.disks], ["/", "/Volumes/Test"])
        self.assertEqual(snapshot.disks[0].usage_percent, 40.0)
        self.assertIsNone(snapshot.disks[1].usage_percent)
        self.assertEqual(disk_usage.call_count, 2)

    def test_unavailable_sensors_are_reported_separately(self):
        with (
            patch("desktop.monitor.subprocess.run", side_effect=FileNotFoundError),
            patch("desktop.monitor.psutil.cpu_count", side_effect=[8, OSError()]),
            patch("desktop.monitor.psutil.cpu_percent", side_effect=psutil.AccessDenied),
            patch("desktop.monitor.psutil.virtual_memory", side_effect=OSError),
            patch("desktop.monitor.psutil.disk_partitions", side_effect=OSError),
            patch("desktop.monitor.psutil.disk_usage", side_effect=OSError),
        ):
            snapshot = SystemMonitor().sample()

        self.assertIsNone(snapshot.cpu.model)
        self.assertEqual(snapshot.cpu.logical_cores, 8)
        self.assertIsNone(snapshot.cpu.physical_cores)
        self.assertIsNone(snapshot.cpu_usage_percent)
        self.assertIsNone(snapshot.memory)
        self.assertEqual(snapshot.disks[0].mountpoint, "/")
        self.assertIsNone(snapshot.disks[0].usage_percent)
