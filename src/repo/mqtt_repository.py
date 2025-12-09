"""
Интерфейс и реализация репозитория для работы с MQTT.

Использует паттерн Repository для абстракции работы с MQTT брокером.
"""
from abc import ABC, abstractmethod
from typing import Protocol, Optional, Dict, Any
import json
import structlog
from aiomqtt import Client as MQTTClient
from aiomqtt.exceptions import MqttError

from src.config import MQTTBrokerConfig


logger = structlog.get_logger()


class MQTTMessageHandler(Protocol):
    """Протокол для обработчика входящих MQTT сообщений."""
    
    async def handle_message(self, topic: str, payload: bytes) -> None:
        """
        Обрабатывает входящее MQTT сообщение.
        
        Args:
            topic: MQTT топик
            payload: Данные сообщения
        """
        ...


class MQTTRepository(ABC):
    """Абстрактный репозиторий для работы с MQTT."""
    
    @abstractmethod
    async def connect(self) -> None:
        """Подключается к MQTT брокеру."""
        ...
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Отключается от MQTT брокера."""
        ...
    
    @abstractmethod
    async def subscribe(self, topic: str, handler: MQTTMessageHandler) -> None:
        """
        Подписывается на топик.
        
        Args:
            topic: MQTT топик для подписки
            handler: Обработчик входящих сообщений
        """
        ...
    
    @abstractmethod
    async def publish(
        self,
        topic: str,
        payload: bytes | str | Dict[str, Any],
        qos: int = 1
    ) -> None:
        """
        Публикует сообщение в топик.
        
        Args:
            topic: MQTT топик
            payload: Данные для публикации
            qos: QoS уровень
        """
        ...


class AsyncMQTTRepository(MQTTRepository):
    """
    Реализация MQTT репозитория на основе aiomqtt.
    
    Использует асинхронный клиент для работы с MQTT брокером.
    """
    
    def __init__(self, config: MQTTBrokerConfig):
        """
        Инициализирует репозиторий.
        
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
                "Подключение к MQTT брокеру",
                host=self.config.host,
                port=self.config.port,
                client_id=self.config.client_id
            )
            
            self._client = MQTTClient(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                client_id=self.config.client_id,
                keepalive=self.config.keepalive,
            )
            
            await self._client.__aenter__()
            
            logger.info("Успешно подключен к MQTT брокеру")
        except MqttError as e:
            logger.error("Ошибка подключения к MQTT брокеру", error=str(e))
            raise
    
    async def disconnect(self) -> None:
        """Отключается от MQTT брокера."""
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
                logger.info("Отключен от MQTT брокера")
            except Exception as e:
                logger.error("Ошибка при отключении от MQTT брокера", error=str(e))
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
            raise RuntimeError("MQTT клиент не подключен. Вызовите connect() сначала.")
        
        self._handler = handler
        self._subscribed_topic = topic
        
        try:
            logger.info("Подписка на MQTT топик", topic=topic, qos=self.config.qos)
            await self._client.subscribe(topic, qos=self.config.qos)
            
            # Запускаем обработку сообщений в бесконечном цикле
            async for message in self._client.messages:
                try:
                    await self._handler.handle_message(message.topic.value, message.payload)
                except Exception as e:
                    logger.error(
                        "Ошибка при обработке MQTT сообщения",
                        topic=message.topic.value,
                        error=str(e)
                    )
        except MqttError as e:
            logger.error("Ошибка при подписке на MQTT топик", topic=topic, error=str(e))
            raise
    
    async def publish(
        self,
        topic: str,
        payload: bytes | str | Dict[str, Any],
        qos: int = 1
    ) -> None:
        """
        Публикует сообщение в топик.
        
        Args:
            topic: MQTT топик
            payload: Данные для публикации (bytes, str или dict)
            qos: QoS уровень
        """
        if not self._client:
            raise RuntimeError("MQTT клиент не подключен. Вызовите connect() сначала.")
        
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
                "Опубликовано MQTT сообщение",
                topic=topic,
                qos=qos,
                payload_size=len(payload_bytes)
            )
        except MqttError as e:
            logger.error("Ошибка при публикации MQTT сообщения", topic=topic, error=str(e))
            raise

