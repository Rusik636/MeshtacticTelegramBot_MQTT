"""Репозитории и интерфейсы для работы с внешними системами."""

from .mqtt_repository import MQTTRepository, MQTTMessageHandler
from .telegram_repository import TelegramRepository

__all__ = ["MQTTRepository", "MQTTMessageHandler", "TelegramRepository"]

