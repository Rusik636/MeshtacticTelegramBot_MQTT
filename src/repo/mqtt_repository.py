"""
Репозиторий для работы с MQTT брокером.

Абстрагирует работу с MQTT - подписка, публикация.
Отвечает только за работу с данными, не за подключение.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Protocol, Optional, Dict, Any, TYPE_CHECKING
from aiomqtt import Client as MQTTClient
from aiomqtt.exceptions import MqttError

from src.config import MQTTBrokerConfig

if TYPE_CHECKING:
    from src.infrastructure.mqtt_connection import MQTTConnectionManager

logger = logging.getLogger(__name__)


class MQTTMessageHandler(Protocol):
    """Протокол для обработчика MQTT сообщений."""

    async def handle_message(self, topic: str, payload: bytes) -> None:
        """Обрабатывает входящее сообщение."""
        ...


class MQTTRepository(ABC):
    """Абстрактный репозиторий для работы с MQTT."""

    @abstractmethod
    async def connect(self) -> None:
        """Подключается к брокеру."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Отключается от брокера."""
        ...

    @abstractmethod
    async def subscribe(self, topic: str, handler: MQTTMessageHandler) -> None:
        """Подписывается на топик и передает сообщения обработчику."""
        ...

    @abstractmethod
    async def publish(
        self, topic: str, payload: bytes | str | Dict[str, Any], qos: int = 1
    ) -> None:
        """Публикует сообщение в топик."""
        ...


class AsyncMQTTRepository(MQTTRepository):
    """
    Реализация MQTT репозитория через aiomqtt.
    
    Отвечает только за работу с данными (подписка, публикация).
    Подключение управляется через MQTTConnectionManager.
    """

    def __init__(
        self,
        config: MQTTBrokerConfig,
        connection_manager: Optional["MQTTConnectionManager"] = None,
    ):
        """
        Создает репозиторий.

        Args:
            config: Конфигурация MQTT брокера
            connection_manager: Менеджер подключения (опционально, создастся автоматически)
        """
        self.config = config
        
        # Используем переданный менеджер или создаем новый
        if connection_manager is None:
            from src.infrastructure.mqtt_connection import MQTTConnectionManager
            connection_manager = MQTTConnectionManager(config)
        self.connection_manager = connection_manager
        
        self._handler: Optional[MQTTMessageHandler] = None
        self._subscribed_topic: Optional[str] = None

    @property
    def _client(self) -> Optional[MQTTClient]:
        """
        Возвращает MQTT клиент через менеджер подключения.

        Returns:
            Экземпляр MQTTClient или None, если не подключен
        """
        return self.connection_manager.client

    async def connect(self) -> None:
        """Подключается к MQTT брокеру через менеджер подключения."""
        await self.connection_manager.connect()

    async def disconnect(self) -> None:
        """Отключается от MQTT брокера через менеджер подключения."""
        await self.connection_manager.disconnect()

    async def subscribe(self, topic: str, handler: MQTTMessageHandler) -> None:
        """
        Подписывается на топик.

        Args:
            topic: MQTT топик для подписки
            handler: Обработчик входящих сообщений
        """
        client = self._client
        if not client:
            raise RuntimeError("MQTT клиент не подключен. Вызовите connect() сначала.")

        self._handler = handler
        self._subscribed_topic = topic

        try:
            logger.info(f"Подписка на MQTT топик: topic={topic}, qos={self.config.qos}")
            await client.subscribe(topic, qos=self.config.qos)

            # Запускаем обработку сообщений в бесконечном цикле
            async for message in client.messages:
                try:
                    # В aiomqtt 2.0+ topic - это строка напрямую
                    topic_str = str(message.topic)
                    await self._handler.handle_message(topic_str, message.payload)
                except Exception as e:
                    topic_str = str(message.topic)
                    logger.error(
                        f"Ошибка при обработке MQTT сообщения: topic={topic_str}, error={e}",
                        exc_info=True,
                    )
        except MqttError as e:
            logger.error(
                f"Ошибка при подписке на MQTT топик: topic={topic}, error={e}",
                exc_info=True,
            )
            raise

    async def publish(
        self, topic: str, payload: bytes | str | Dict[str, Any], qos: int = 1
    ) -> None:
        """
        Публикует сообщение в топик.

        Args:
            topic: MQTT топик
            payload: Данные для публикации (bytes, str или dict)
            qos: QoS уровень
        """
        client = self._client
        if not client:
            raise RuntimeError("MQTT клиент не подключен. Вызовите connect() сначала.")

        try:
            # Преобразуем payload в bytes
            if isinstance(payload, dict):
                payload_bytes = json.dumps(payload).encode("utf-8")
            elif isinstance(payload, str):
                payload_bytes = payload.encode("utf-8")
            else:
                payload_bytes = payload

            await client.publish(topic, payload_bytes, qos=qos)

            logger.debug(
                f"Опубликовано MQTT сообщение: topic={topic}, qos={qos}, "
                f"payload_size={len(payload_bytes)}"
            )
        except MqttError as e:
            logger.error(
                f"Ошибка при публикации MQTT сообщения: topic={topic}, error={e}",
                exc_info=True,
            )
            raise
