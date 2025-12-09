"""
Сервис MQTT прокси.

Отвечает за пересылку сообщений в другие MQTT брокеры.
Использует паттерн Strategy для поддержки множественных целей прокси.
"""
from typing import List, Dict, Any
import json
import structlog
from aiomqtt import Client as MQTTClient
from aiomqtt.exceptions import MqttError

from src.config import MQTTProxyTargetConfig
from src.domain.message import MeshtasticMessage


logger = structlog.get_logger()


class MQTTProxyTarget:
    """
    Представляет одну цель прокси (один целевой MQTT брокер).
    
    Инкапсулирует подключение и логику публикации для одного брокера.
    """
    
    def __init__(self, config: MQTTProxyTargetConfig):
        """
        Инициализирует цель прокси.
        
        Args:
            config: Конфигурация целевого брокера
        """
        self.config = config
        self._client: MQTTClient | None = None
        self._connected = False
    
    async def connect(self) -> None:
        """Подключается к целевому MQTT брокеру."""
        if not self.config.enabled:
            logger.debug("Прокси цель отключена", name=self.config.name)
            return
        
        try:
            logger.info(
                "Подключение к целевому MQTT брокеру",
                name=self.config.name,
                host=self.config.host,
                port=self.config.port
            )
            
            client_id = self.config.client_id or f"meshtastic-proxy-{self.config.name}"
            
            self._client = MQTTClient(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                client_id=client_id,
            )
            
            await self._client.__aenter__()
            self._connected = True
            
            logger.info("Успешно подключен к целевому MQTT брокеру", name=self.config.name)
        except MqttError as e:
            logger.error(
                "Ошибка подключения к целевому MQTT брокеру",
                name=self.config.name,
                error=str(e)
            )
            self._connected = False
            raise
    
    async def disconnect(self) -> None:
        """Отключается от целевого MQTT брокера."""
        if self._client and self._connected:
            try:
                await self._client.__aexit__(None, None, None)
                logger.info("Отключен от целевого MQTT брокера", name=self.config.name)
            except Exception as e:
                logger.error(
                    "Ошибка при отключении от целевого MQTT брокера",
                    name=self.config.name,
                    error=str(e)
                )
            finally:
                self._client = None
                self._connected = False
    
    async def publish_message(self, message: MeshtasticMessage) -> None:
        """
        Публикует сообщение в целевой брокер.
        
        Args:
            message: Сообщение для публикации
        """
        if not self.config.enabled:
            return
        
        if not self._connected:
            logger.warning(
                "Попытка публикации в неподключенный брокер",
                name=self.config.name
            )
            return
        
        try:
            # Формируем топик
            topic = message.topic
            if self.config.topic_prefix:
                # Если задан префикс, добавляем его
                if topic.startswith("/"):
                    topic = f"{self.config.topic_prefix}{topic}"
                else:
                    topic = f"{self.config.topic_prefix}/{topic}"
            
            # Публикуем исходный payload
            payload = json.dumps(message.raw_payload).encode("utf-8")
            
            await self._client.publish(topic, payload, qos=self.config.qos)
            
            logger.debug(
                "Опубликовано сообщение в целевой брокер",
                name=self.config.name,
                topic=topic,
                qos=self.config.qos
            )
        except MqttError as e:
            logger.error(
                "Ошибка при публикации в целевой брокер",
                name=self.config.name,
                topic=topic,
                error=str(e)
            )
            # Не пробрасываем исключение, чтобы не прерывать обработку других целей


class MQTTProxyService:
    """
    Сервис для проксирования MQTT сообщений в другие брокеры.
    
    Управляет множественными целями прокси и обеспечивает отказоустойчивость.
    """
    
    def __init__(self, targets: List[MQTTProxyTargetConfig]):
        """
        Инициализирует сервис прокси.
        
        Args:
            targets: Список конфигураций целевых брокеров
        """
        self._targets: List[MQTTProxyTarget] = [
            MQTTProxyTarget(config) for config in targets if config.enabled
        ]
        logger.info("Инициализирован MQTT Proxy Service", targets_count=len(self._targets))
    
    async def start(self) -> None:
        """Запускает сервис: подключается ко всем целевым брокерам."""
        for target in self._targets:
            try:
                await target.connect()
            except Exception as e:
                logger.error(
                    "Не удалось подключиться к целевому брокеру",
                    name=target.config.name,
                    error=str(e)
                )
                # Продолжаем работу с другими целями
    
    async def stop(self) -> None:
        """Останавливает сервис: отключается от всех целевых брокеров."""
        for target in self._targets:
            try:
                await target.disconnect()
            except Exception as e:
                logger.error(
                    "Ошибка при отключении от целевого брокера",
                    name=target.config.name,
                    error=str(e)
                )
    
    async def proxy_message(self, message: MeshtasticMessage) -> None:
        """
        Проксирует сообщение во все целевые брокеры.
        
        Args:
            message: Сообщение для проксирования
        """
        if not self._targets:
            return
        
        # Публикуем во все цели параллельно
        for target in self._targets:
            try:
                await target.publish_message(message)
            except Exception as e:
                logger.error(
                    "Ошибка при проксировании сообщения",
                    target_name=target.config.name,
                    error=str(e)
                )
                # Продолжаем с другими целями

