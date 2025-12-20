"""
Настройка DI-контейнера для приложения.

Регистрирует все зависимости и их жизненный цикл.
"""

import logging
from pathlib import Path

from src.infrastructure.di_container import DIContainer, Lifetime
from src.infrastructure.file_storage import LocalFileStorage, FileStorage
from src.infrastructure.telegram_connection import TelegramConnectionManager
from src.config import AppConfig

logger = logging.getLogger(__name__)


def setup_container(config: AppConfig) -> DIContainer:
    """
    Настраивает DI-контейнер со всеми зависимостями.

    Args:
        config: Конфигурация приложения

    Returns:
        Настроенный DI-контейнер
    """
    container = DIContainer()

    # Регистрируем инфраструктурные зависимости
    container.register_singleton("file_storage", LocalFileStorage(), FileStorage)
    container.register_singleton("telegram_connection", TelegramConnectionManager(config.telegram))

    # Регистрируем конфигурацию
    container.register_singleton("config", config)

    logger.info("DI-контейнер настроен")
    return container

