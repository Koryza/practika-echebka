from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    refresh_seconds: int = 2
    record_seconds: int = 10
    api_port: int = 8080

    def __post_init__(self) -> None:
        for key, (minimum, maximum) in SETTINGS_LIMITS.items():
            value = getattr(self, key)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"Значение {key} должно быть от {minimum} до {maximum}")


SETTINGS_LIMITS = {
    "refresh_seconds": (1, 3600),
    "record_seconds": (1, 3600),
    "api_port": (1024, 65535),
}
