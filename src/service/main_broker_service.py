"""
Сервис для работы с основным MQTT брокером.

Подключается к брокеру, подписывается на топики и получает сообщения.
"""

import logging
from typing import Optional, TYPE_CHECKING

from src.repo.mqtt_repository import AsyncMQTTRepository, MQTTMessageHandler
from src.config import MQTTBrokerConfig

if TYPE_CHECKING:
    from src.infrastructure.mqtt_connection import MQTTConnectionManager

logger = logging.getLogger(__name__)


class MainBrokerService:
    """Управляет подключением к основному MQTT брокеру и подпиской на топики."""

    def __init__(
        self,
        config: MQTTBrokerConfig,
        mqtt_repo: Optional[AsyncMQTTRepository] = None,
        connection_manager: Optional["MQTTConnectionManager"] = None,
    ):
        """
        Создает сервис для работы с основным брокером.

        Args:
            config: Конфигурация основного MQTT брокера
            mqtt_repo: Репозиторий MQTT (опционально, создастся автоматически)
            connection_manager: Менеджер подключения (опционально, создастся автоматически)
        """
        self.config = config
        
        # Используем переданный репозиторий или создаем новый
        if mqtt_repo is None:
            mqtt_repo = AsyncMQTTRepository(config, connection_manager=connection_manager)
        self.mqtt_repo = mqtt_repo
        
        self._connected = False

    async def start(self) -> None:
        """Подключается к основному MQTT брокеру."""
        if self._connected:
            logger.warning("Основной MQTT брокер уже подключен")
            return

        try:
            await self.mqtt_repo.connect()
            self._connected = True
            logger.info("Основной MQTT брокер подключен")
        except Exception as e:
            logger.error(
                f"Ошибка подключения к основному MQTT брокеру: {e}", exc_info=True
            )
            raise

    async def stop(self) -> None:
        """Отключается от основного MQTT брокера."""
        if not self._connected:
            return

        try:
            await self.mqtt_repo.disconnect()
            self._connected = False
            logger.info("Основной MQTT брокер отключен")
        except Exception as e:
            logger.error(
                f"Ошибка отключения от основного MQTT брокера: {e}", exc_info=True
            )

    async def subscribe(self, handler: MQTTMessageHandler) -> None:
        """
        Подписывается на топик и передает сообщения обработчику.

        Args:
            handler: Обработчик входящих MQTT сообщений
        """
        if not self._connected:
            raise RuntimeError("Основной MQTT брокер не подключен")

        await self.mqtt_repo.subscribe(self.config.topic, handler)

    @property
    def is_connected(self) -> bool:
        """Проверка подключения к брокеру."""
        return self._connected

    @property
    def topic(self) -> str:
        """Топик, на который подписан."""
        return self.config.topic
