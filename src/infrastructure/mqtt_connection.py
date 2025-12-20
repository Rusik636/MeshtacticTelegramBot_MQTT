"""
Менеджер подключения к MQTT брокеру.

Отвечает только за установку и управление подключением к MQTT.
"""

import logging
from typing import Optional

from aiomqtt import MQTTClient, MqttError  # type: ignore

from src.config import MQTTBrokerConfig

logger = logging.getLogger(__name__)


class MQTTConnectionManager:
    """
    Менеджер подключения к MQTT брокеру.
    
    Отвечает только за создание и управление подключением к MQTT.
    Не содержит бизнес-логику работы с сообщениями.
    """

    def __init__(self, config: MQTTBrokerConfig):
        """
        Создает менеджер подключения.

        Args:
            config: Конфигурация MQTT брокера
        """
        self.config = config
        self._client: Optional[MQTTClient] = None
        self._connected = False

    @property
    def client(self) -> Optional[MQTTClient]:
        """
        Возвращает экземпляр MQTT клиента.

        Returns:
            Экземпляр MQTTClient или None, если не подключен
        """
        return self._client

    @property
    def is_connected(self) -> bool:
        """
        Проверяет, подключен ли клиент.

        Returns:
            True, если клиент подключен
        """
        return self._connected and self._client is not None

    async def connect(self) -> None:
        """
        Подключается к MQTT брокеру.

        Raises:
            MqttError: Если не удалось подключиться
        """
        if self._connected:
            logger.warning("MQTT клиент уже подключен")
            return

        try:
            logger.info(
                f"Подключение к MQTT брокеру: host={self.config.host}, "
                f"port={self.config.port}, client_id={self.config.client_id}"
            )

            # В aiomqtt 2.0+ client_id передается через параметр identifier как строка
            self._client = MQTTClient(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                identifier=self.config.client_id,
                keepalive=self.config.keepalive,
            )

            await self._client.__aenter__()
            self._connected = True

            logger.info("Успешно подключен к MQTT брокеру")
        except MqttError as e:
            logger.error(f"Ошибка подключения к MQTT брокеру: {e}", exc_info=True)
            self._client = None
            self._connected = False
            raise

    async def disconnect(self) -> None:
        """Отключается от MQTT брокера."""
        if not self._client:
            return

        try:
            await self._client.__aexit__(None, None, None)
            logger.info("Отключен от MQTT брокера")
        except Exception as e:
            logger.error(
                f"Ошибка при отключении от MQTT брокера: {e}", exc_info=True
            )
        finally:
            self._client = None
            self._connected = False

