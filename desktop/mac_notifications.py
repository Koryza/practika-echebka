import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QObject, QElapsedTimer, QProcess, QTimer, Signal, Slot

from .alerts import RESOURCE_LABELS, Alert


class MacNotifications(QObject):
    status_changed = Signal(str)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._app = (
            Path.home() / "Library/Application Support/System Monitor"
            / "System Monitor Notifications.app"
        )
        self._pending: str | None = None
        self._testing = False
        self._request: TemporaryDirectory | None = None
        self._elapsed = QElapsedTimer()
        self._poll = QTimer(self)
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._check_result)

    @Slot(object)
    def send_alerts(self, alerts: list[Alert]) -> None:
        if not alerts or sys.platform != "darwin":
            return
        latest = alerts[0]
        resource = RESOURCE_LABELS[latest.resource]
        if latest.target:
            resource += f" · {latest.target}"
        measured = f"{latest.measured:.1f}".replace(".", ",")
        body = f"{resource} · сейчас {measured} % · порог {latest.threshold} %"
        if len(alerts) > 1:
            body += f"\nДругих превышений: {len(alerts) - 1}"
        if self._request is None:
            self._send("Порог превышен", body)
        else:
            self._pending = body

    @Slot()
    def send_test(self) -> None:
        if self._request is None:
            self._send("Проверка уведомлений", "System Monitor может отправлять уведомления macOS.", test=True)
        else:
            self.status_changed.emit("macOS ещё обрабатывает предыдущее уведомление.")

    def _send(self, title: str, body: str, *, test: bool = False) -> None:
        if sys.platform != "darwin":
            self.status_changed.emit("Системные уведомления доступны на macOS.")
            return
        if not (self._app / "Contents/MacOS/NotificationSender").is_file():
            self.status_changed.emit("Для системных уведомлений запусти tools/install-mac-notifier.sh.")
            return

        try:
            self._request = TemporaryDirectory(prefix="system-monitor-notification-")
        except OSError:
            self.status_changed.emit("Не удалось подготовить отправку уведомления macOS.")
            return
        started, _ = QProcess.startDetached(
            "/usr/bin/open",
            ["-g", "-j", "-n", "-a", str(self._app), "--args", title, body, str(self._result_path())],
        )
        if not started:
            self.stop()
            self.status_changed.emit("Не удалось запустить отправку уведомления macOS.")
            return

        self._testing = test
        self._elapsed.start()
        self._poll.start()
        if test:
            self.status_changed.emit("Ожидаем ответ macOS. Разреши уведомления, если появится запрос.")

    def _result_path(self) -> Path:
        return Path(self._request.name) / "result"

    @Slot()
    def _check_result(self) -> None:
        try:
            result = self._result_path().read_text(encoding="utf-8")
        except FileNotFoundError:
            if not self._elapsed.hasExpired(95_000):
                return
            result = "timeout"
        except OSError:
            result = "error"

        pending = self._pending
        self.stop()
        if result == "sent":
            self.status_changed.emit("Тестовое уведомление передано macOS." if self._testing else "")
            if pending is not None:
                self._send("Порог превышен", pending)
        elif result == "denied":
            self.status_changed.emit("Разреши System Monitor в системных настройках уведомлений.")
        elif result == "timeout":
            self.status_changed.emit("macOS не ответила. Проверь разрешение и отправь тестовое уведомление.")
        else:
            self.status_changed.emit("Не удалось отправить уведомление macOS.")

    @Slot()
    def stop(self) -> None:
        self._pending = None
        self._poll.stop()
        if self._request is not None:
            self._request.cleanup()
            self._request = None
