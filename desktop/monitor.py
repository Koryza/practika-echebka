"""Сбор показателей macOS для настольного интерфейса и HTTP API."""

import socket
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import psutil


@dataclass(frozen=True)
class CpuInfo:
    model: str | None
    logical_cores: int | None
    physical_cores: int | None


@dataclass(frozen=True)
class MemoryUsage:
    total_bytes: int
    used_bytes: int
    available_bytes: int
    usage_percent: float


@dataclass(frozen=True)
class DiskUsage:
    mountpoint: str
    device: str | None
    total_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    usage_percent: float | None = None


@dataclass(frozen=True)
class SystemSnapshot:
    computer_name: str
    timestamp: datetime
    cpu: CpuInfo
    cpu_usage_percent: float | None
    memory: MemoryUsage | None
    disks: tuple[DiskUsage, ...]


def _cpu_model() -> str | None:
    try:
        result = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _cpu_count(*, logical: bool) -> int | None:
    try:
        return psutil.cpu_count(logical=logical)
    except (OSError, psutil.Error):
        return None


def _cpu_usage() -> float | None:
    try:
        # Положительный интервал даёт осмысленное значение уже при первом вызове.
        return psutil.cpu_percent(interval=0.1)
    except (OSError, psutil.Error):
        return None


def _memory_usage() -> MemoryUsage | None:
    try:
        memory = psutil.virtual_memory()
    except (OSError, psutil.Error):
        return None
    return MemoryUsage(
        total_bytes=memory.total,
        used_bytes=memory.total - memory.available,
        available_bytes=memory.available,
        usage_percent=memory.percent,
    )


def _disk_usage() -> tuple[DiskUsage, ...]:
    try:
        partitions = psutil.disk_partitions(all=False)
    except (OSError, psutil.Error):
        partitions = []

    devices = {partition.mountpoint: partition.device for partition in partitions}
    devices.setdefault("/", None)
    disks = []
    for mountpoint, device in sorted(devices.items()):
        try:
            usage = psutil.disk_usage(mountpoint)
        except (OSError, psutil.Error):
            disks.append(DiskUsage(mountpoint, device))
            continue
        disks.append(
            DiskUsage(
                mountpoint=mountpoint,
                device=device,
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                usage_percent=usage.percent,
            )
        )
    return tuple(disks)


class SystemMonitor:
    """Считывает постоянные свойства при создании и текущие при каждом замере."""

    def __init__(self) -> None:
        self._computer_name = socket.gethostname()
        self._cpu = CpuInfo(
            model=_cpu_model(),
            logical_cores=_cpu_count(logical=True),
            physical_cores=_cpu_count(logical=False),
        )

    def sample(self) -> SystemSnapshot:
        """Выполняет синхронный замер. В графическом приложении вызывать в фоне."""
        cpu_usage = _cpu_usage()
        memory = _memory_usage()
        disks = _disk_usage()
        return SystemSnapshot(
            computer_name=self._computer_name,
            timestamp=datetime.now(UTC),
            cpu=self._cpu,
            cpu_usage_percent=cpu_usage,
            memory=memory,
            disks=disks,
        )


if __name__ == "__main__":
    import json

    snapshot = SystemMonitor().sample()
    print(json.dumps(asdict(snapshot), default=datetime.isoformat, ensure_ascii=False, indent=2))
