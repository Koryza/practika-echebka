import sys

from PySide6.QtWidgets import QApplication

from .monitor_window import MonitorWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("System Monitor")
    window = MonitorWindow()
    app.aboutToQuit.connect(window.stop_workers)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
