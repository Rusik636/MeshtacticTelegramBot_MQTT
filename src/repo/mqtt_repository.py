"""
Репозиторий для работы с MQTT брокером.

Абстрагирует работу с MQTT - подключение, подписка, публикация.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Protocol, Optional, Dict, Any
from aiomqtt import Client as MQTTClient
from aiomqtt.exceptions import MqttError

from src.config import MQTTBrokerConfig


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
    """Реализация MQTT репозитория через aiomqtt."""

    def __init__(self, config: MQTTBrokerConfig):
        """
        Сохраняет конфигурацию брокера.

        Args:
            config: Конфигурация MQTT брокера
        """
        self.config = config
        self._client: Optional[MQTTClient] = None
        self._handler: Optional[MQTTMessageHandler] = None
        self._subscribed_topic: Optional[str] = None

    async def connect(self) -> None:
        """Подключается к MQTT брокеру."""
        try:
            logger.info(
                f"Подключение к MQTT брокеру: host={self.config.host}, "
                f"port={self.config.port}, client_id={self.config.client_id}"
            )

            # В aiomqtt 2.0+ client_id передается через параметр identifier как
            # строка
            self._client = MQTTClient(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                identifier=self.config.client_id,
                keepalive=self.config.keepalive,
            )

            await self._client.__aenter__()

            logger.info("Успешно подключен к MQTT брокеру")
        except MqttError as e:
            logger.error(
                f"Ошибка подключения к MQTT брокеру: {e}",
                exc_info=True)
            raise

    async def disconnect(self) -> None:
        """Отключается от MQTT брокера."""
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
                logger.info("Отключен от MQTT брокера")
            except Exception as e:
                logger.error(
                    f"Ошибка при отключении от MQTT брокера: {e}",
                    exc_info=True)
            finally:
                self._client = None

    async def subscribe(self, topic: str, handler: MQTTMessageHandler) -> None:
        """
        Подписывается на топик.

        Args:
            topic: MQTT топик для подписки
            handler: Обработчик входящих сообщений
        """
        if not self._client:
            raise RuntimeError(
                "MQTT клиент не подключен. Вызовите connect() сначала.")

        self._handler = handler
        self._subscribed_topic = topic

        try:
            logger.info(
                f"Подписка на MQTT топик: topic={topic}, qos={self.config.qos}")
            await self._client.subscribe(topic, qos=self.config.qos)

            # Запускаем обработку сообщений в бесконечном цикле
            async for message in self._client.messages:
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
        if not self._client:
            raise RuntimeError(
                "MQTT клиент не подключен. Вызовите connect() сначала.")

        try:
            # Преобразуем payload в bytes
            if isinstance(payload, dict):
                payload_bytes = json.dumps(payload).encode("utf-8")
            elif isinstance(payload, str):
                payload_bytes = payload.encode("utf-8")
            else:
                payload_bytes = payload

            await self._client.publish(topic, payload_bytes, qos=qos)

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
