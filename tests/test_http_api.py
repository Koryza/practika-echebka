import json
import socket
import unittest
from datetime import UTC, datetime
from unittest.mock import patch
from urllib.request import urlopen

from desktop.http_api import LOOPBACK, LiveStatus, LocalApi, create_app
from desktop.monitor import CpuInfo, DiskUsage, MemoryUsage, SystemSnapshot


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.status = LiveStatus()
        self.client = create_app(self.status).test_client()

    def test_health_and_status_before_first_sample(self):
        self.assertEqual(self.client.get("/api/health").get_json(), {"status": "ok"})
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"error": "metrics_unavailable"})
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_status_matches_snapshot_and_selected_disk(self):
        root = DiskUsage("/", "root", 1000, 300, 700, 30)
        selected = DiskUsage("/Volumes/Test", "test", 2000, 800, 1200, 40)
        snapshot = SystemSnapshot(
            "Test Mac",
            datetime(2026, 1, 2, 3, 4, 5, 123000, tzinfo=UTC),
            CpuInfo("Test CPU", 8, 4),
            22.5,
            MemoryUsage(1000, 600, 400, 60),
            (root, selected),
        )
        self.status.publish(snapshot, selected)
        response = self.client.get(
            "/api/status", headers={"Host": "10.0.2.2:8080"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "computerName": "Test Mac",
                "timestamp": "2026-01-02T03:04:05.123Z",
                "cpu": {
                    "model": "Test CPU",
                    "logicalCores": 8,
                    "physicalCores": 4,
                    "usagePercent": 22.5,
                },
                "memory": {"totalBytes": 1000, "usedBytes": 600, "availableBytes": 400, "usagePercent": 60},
                "disk": {
                    "name": "/Volumes/Test",
                    "totalBytes": 2000,
                    "usedBytes": 800,
                    "freeBytes": 1200,
                    "usagePercent": 40,
                },
            },
        )

    def test_unavailable_hardware_uses_json_null_and_sample_can_be_invalidated(self):
        snapshot = SystemSnapshot("Test Mac", datetime.now(UTC), CpuInfo(None, None, None), None, None, ())
        self.status.publish(snapshot, None)
        data = self.client.get("/api/status").get_json()
        self.assertIsNone(data["cpu"]["model"])
        self.assertIsNone(data["memory"]["usagePercent"])
        self.assertIsNone(data["disk"])
        self.status.publish(None, None)
        self.assertEqual(self.client.get("/api/status").status_code, 503)

    def test_api_has_read_only_routes_and_checks_host(self):
        self.assertEqual(self.client.post("/api/status").status_code, 405)
        self.assertEqual(self.client.get("/api/commands").status_code, 404)
        self.assertEqual(self.client.get("/api/health", headers={"Host": "example.test"}).status_code, 400)

    def test_socket_serves_requests_and_failed_rebind_keeps_service_running(self):
        api = LocalApi()
        self.addCleanup(api.stop)
        with patch("socket.getfqdn", side_effect=AssertionError("Unexpected reverse DNS")):
            api.start(0)
        port = api.port
        with socket.socket() as occupied:
            occupied.bind((LOOPBACK, 0))
            occupied.listen()
            with self.assertRaises(OSError):
                api.start(occupied.getsockname()[1])
        self.assertEqual(api.port, port)
        with urlopen(f"http://{LOOPBACK}:{port}/api/health", timeout=2) as response:
            self.assertEqual(json.load(response), {"status": "ok"})
        api.stop()
        with self.assertRaises(OSError):
            with socket.create_connection((LOOPBACK, port), timeout=1):
                pass
