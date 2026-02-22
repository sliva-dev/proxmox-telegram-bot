import os
import logging
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)


def get_env(key: str, required: bool = False, default: str = "") -> str:
    """Получает строку из окружения. Если required=True и значения нет, падает с ошибкой."""
    value = os.getenv(key, default).strip()
    if required and not value:
        raise ValueError(
            f"Критическая ошибка: не задана обязательная переменная {key} в .env"
        )
    return value


def get_env_int(key: str, default: int) -> int:
    """Безопасно переводит значение в число. При ошибке возвращает default."""
    value = os.getenv(key)
    if not value:
        return default
    try:
        return int(value.strip())
    except ValueError:
        logging.warning(
            f"Переменная {key} имеет некорректное числовое значение '{value}'. Используется default: {default}"
        )
        return default


def get_whitelist(key: str) -> tuple[int, ...]:
    """Безопасно парсит список ID, игнорируя ошибки конвертации отдельных элементов."""
    raw_value = os.getenv(key, "")
    whitelist = []
    for uid in raw_value.split(","):
        uid = uid.strip()
        if uid:
            try:
                whitelist.append(int(uid))
            except ValueError:
                logging.warning(f"Пропущен некорректный ID в {key}: '{uid}'")
    return tuple(whitelist)


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    whitelist: tuple[int, ...]


@dataclass(frozen=True)
class ProxmoxConfig:
    host: str
    user: str
    token_name: str
    token_value: str
    port: int


@dataclass(frozen=True)
class AlertsConfig:
    cpu_temp_threshold: int
    cpu_usage_threshold: int
    ram_usage_threshold: int
    check_interval: int


TELEGRAM = TelegramConfig(
    bot_token=get_env("BOT_TOKEN", required=True), whitelist=get_whitelist("WHITELIST")
)

_proxmox_host = get_env("HOST") or get_env("PROXMOX_HOST", default="localhost")
_proxmox_user = get_env("USER") or get_env("PROXMOX_USER", required=True)

if "@" not in _proxmox_user:
    _proxmox_user = f"{_proxmox_user}@pam"

PROXMOX = ProxmoxConfig(
    host=_proxmox_host,
    user=_proxmox_user,
    token_name=get_env("PROXMOX_TOKEN_NAME", required=True),
    token_value=get_env("PROXMOX_TOKEN_VALUE", required=True),
    port=get_env_int("PROXMOX_PORT", 8006),
)

ALERTS = AlertsConfig(
    cpu_temp_threshold=get_env_int("CPU_TEMP_THRESHOLD", 75),
    cpu_usage_threshold=get_env_int("CPU_USAGE_THRESHOLD", 80),
    ram_usage_threshold=get_env_int("RAM_USAGE_THRESHOLD", 80),
    check_interval=get_env_int("CHECK_INTERVAL", 300),
)
