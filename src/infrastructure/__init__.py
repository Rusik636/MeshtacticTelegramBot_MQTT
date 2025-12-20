"""
Инфраструктурный слой приложения.

Содержит абстракции для работы с внешними системами:
- DI-контейнер
- Файловое хранилище
- Подключения к внешним сервисам
"""

from src.infrastructure.di_container import DIContainer, Lifetime
from src.infrastructure.file_storage import FileStorage, LocalFileStorage
from src.infrastructure.telegram_connection import TelegramConnectionManager
from src.infrastructure.mqtt_connection import MQTTConnectionManager

__all__ = [
    "DIContainer",
    "Lifetime",
    "FileStorage",
    "LocalFileStorage",
    "TelegramConnectionManager",
    "MQTTConnectionManager",
]

