"""Проверка порогов System Monitor по одному снимку оборудования."""

from dataclasses import dataclass

from .monitor import SystemSnapshot

ALERT_LIMITS = {
    "cpu_threshold": (0, 100),
    "memory_threshold": (0, 100),
    "disk_threshold": (0, 100),
    "repeat_seconds": (5, 3600),
}

RESOURCE_LABELS = {"cpu": "Процессор", "memory": "Память", "disk": "Накопитель"}


@dataclass(frozen=True)
class AlertSettings:
    cpu_threshold: int = 90
    memory_threshold: int = 90
    disk_threshold: int = 90
    repeat_seconds: int = 60

    def __post_init__(self) -> None:
        for key, (minimum, maximum) in ALERT_LIMITS.items():
            value = getattr(self, key)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"Значение {key} должно быть от {minimum} до {maximum}")


@dataclass(frozen=True)
class Alert:
    recorded_at: int
    resource: str
    target: str
    measured: float
    threshold: int


def threshold_alerts(snapshot: SystemSnapshot, settings: AlertSettings) -> list[Alert]:
    """Возвращает отдельное превышение для каждого доступного ресурса."""
    timestamp = int(snapshot.timestamp.timestamp() * 1000)
    memory = snapshot.memory.usage_percent if snapshot.memory is not None else None
    values = [
        ("cpu", "", snapshot.cpu_usage_percent, settings.cpu_threshold),
        ("memory", "", memory, settings.memory_threshold),
    ]
    values.extend(
        ("disk", disk.mountpoint, disk.usage_percent, settings.disk_threshold)
        for disk in snapshot.disks
    )
    return [
        Alert(timestamp, resource, target, measured, threshold)
        for resource, target, measured, threshold in values
        if measured is not None and threshold < measured <= 100
    ]
