"""Локальный HTTP API System Monitor для Android-эмулятора."""

from socketserver import TCPServer, ThreadingMixIn
from threading import Lock, Thread
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from flask import Flask, Response, jsonify

from .monitor import DiskUsage, SystemSnapshot

LOOPBACK = "127.0.0.1"
EMULATOR_HOST = "10.0.2.2"


class LiveStatus:
    def __init__(self) -> None:
        self._lock = Lock()
        self._value: tuple[SystemSnapshot, DiskUsage | None] | None = None

    def publish(self, snapshot: SystemSnapshot | None, disk: DiskUsage | None) -> None:
        with self._lock:
            self._value = (snapshot, disk) if snapshot is not None else None

    def read(self) -> tuple[SystemSnapshot, DiskUsage | None] | None:
        with self._lock:
            return self._value


def _status_payload(snapshot: SystemSnapshot, disk: DiskUsage | None) -> dict:
    cpu = snapshot.cpu
    memory = snapshot.memory
    return {
        "computerName": snapshot.computer_name,
        "timestamp": snapshot.timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "cpu": {
            "model": cpu.model,
            "logicalCores": cpu.logical_cores,
            "physicalCores": cpu.physical_cores,
            "usagePercent": snapshot.cpu_usage_percent,
        },
        "memory": {
            "totalBytes": memory.total_bytes if memory else None,
            "usedBytes": memory.used_bytes if memory else None,
            "availableBytes": memory.available_bytes if memory else None,
            "usagePercent": memory.usage_percent if memory else None,
        },
        "disk": {
            "name": disk.mountpoint,
            "totalBytes": disk.total_bytes,
            "usedBytes": disk.used_bytes,
            "freeBytes": disk.free_bytes,
            "usagePercent": disk.usage_percent,
        } if disk else None,
    }


def create_app(status: LiveStatus) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["TRUSTED_HOSTS"] = (LOOPBACK, EMULATOR_HOST, "localhost")

    @app.after_request
    def prevent_caching(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health() -> Response:
        return jsonify(status="ok")

    @app.get("/api/status")
    def current_status():
        current = status.read()
        if current is None:
            return jsonify(error="metrics_unavailable"), 503
        return jsonify(_status_payload(*current))

    return app


class _RequestHandler(WSGIRequestHandler):
    def setup(self) -> None:
        self.request.settimeout(2)
        super().setup()

    def log_request(self, code="-", size="-") -> None:
        return


class _LocalServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        # Для числового локального адреса обратный DNS не нужен.
        self.server_name, self.server_port = self.server_address
        self.setup_environ()


class LocalApi:
    def __init__(self) -> None:
        self.status = LiveStatus()
        self._app = create_app(self.status)
        self._server: WSGIServer | None = None
        self._thread: Thread | None = None

    @property
    def port(self) -> int | None:
        return self._server.server_port if self._server is not None else None

    def start(self, port: int) -> None:
        if port == self.port:
            return
        server = make_server(LOOPBACK, port, self._app, _LocalServer, _RequestHandler)
        thread = Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.05},
            name="System Monitor HTTP",
            daemon=True,
        )
        try:
            thread.start()
        except RuntimeError:
            server.server_close()
            raise
        self.stop()
        self._server = server
        self._thread = thread

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._thread.join()
            self._server = None
            self._thread = None
