"""
Сервис MQTT прокси.

Отвечает за пересылку сообщений в другие MQTT брокеры.
Использует паттерн Strategy для поддержки множественных целей прокси.
Поддерживает параллельную обработку для повышения производительности.
"""
import asyncio
import json
import logging
from typing import List, Dict, Any
from aiomqtt import Client as MQTTClient
from aiomqtt.exceptions import MqttError

from src.config import MQTTProxyTargetConfig
from src.domain.message import MeshtasticMessage


logger = logging.getLogger(__name__)


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
            logger.debug(f"Прокси цель отключена: name={self.config.name}")
            return
        
        try:
            logger.info(
                f"Подключение к целевому MQTT брокеру: name={self.config.name}, "
                f"host={self.config.host}, port={self.config.port}"
            )
            
            client_id = self.config.client_id or f"meshtastic-proxy-{self.config.name}"
            
            # В aiomqtt 2.0+ client_id передается через параметр identifier как строка
            self._client = MQTTClient(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                identifier=client_id,
            )
            
            await self._client.__aenter__()
            self._connected = True
            
            logger.info(f"Успешно подключен к целевому MQTT брокеру: name={self.config.name}")
        except MqttError as e:
            logger.error(
                f"Ошибка подключения к целевому MQTT брокеру: name={self.config.name}, error={e}",
                exc_info=True
            )
            self._connected = False
            raise
    
    async def disconnect(self) -> None:
        """Отключается от целевого MQTT брокера."""
        if self._client and self._connected:
            try:
                await self._client.__aexit__(None, None, None)
                logger.info(f"Отключен от целевого MQTT брокера: name={self.config.name}")
            except Exception as e:
                logger.error(
                    f"Ошибка при отключении от целевого MQTT брокера: name={self.config.name}, error={e}",
                    exc_info=True
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
            logger.warning(f"Попытка публикации в неподключенный брокер: name={self.config.name}")
            return
        
        try:
            # Формируем топик (в aiomqtt 2.0+ topic может быть строкой или объектом)
            topic = str(message.topic) if not isinstance(message.topic, str) else message.topic
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
                f"Опубликовано сообщение в целевой брокер: name={self.config.name}, "
                f"topic={topic}, qos={self.config.qos}"
            )
        except MqttError as e:
            logger.error(
                f"Ошибка при публикации в целевой брокер: name={self.config.name}, "
                f"topic={topic}, error={e}",
                exc_info=True
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
        logger.info(f"Инициализирован MQTT Proxy Service: targets_count={len(self._targets)}")
    
    async def start(self) -> None:
        """
        Запускает сервис: подключается ко всем целевым брокерам параллельно.
        
        Все подключения выполняются одновременно для ускорения инициализации.
        """
        if not self._targets:
            return
        
        # Создаем задачи для параллельного подключения
        tasks = [target.connect() for target in self._targets]
        
        # Выполняем все подключения параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        for target, result in zip(self._targets, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Не удалось подключиться к целевому брокеру: name={target.config.name}, error={result}",
                    exc_info=True
                )
                # Продолжаем работу с другими целями
    
    async def stop(self) -> None:
        """
        Останавливает сервис: отключается от всех целевых брокеров параллельно.
        
        Все отключения выполняются одновременно для ускорения завершения работы.
        """
        if not self._targets:
            return
        
        # Создаем задачи для параллельного отключения
        tasks = [target.disconnect() for target in self._targets]
        
        # Выполняем все отключения параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        for target, result in zip(self._targets, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Ошибка при отключении от целевого брокера: name={target.config.name}, error={result}",
                    exc_info=True
                )
    
    async def proxy_message(self, message: MeshtasticMessage) -> None:
        """
        Проксирует сообщение во все целевые брокеры параллельно.
        
        Все публикации выполняются одновременно для максимальной производительности.
        Ошибки одного брокера не влияют на работу остальных.
        
        Args:
            message: Сообщение для проксирования
        """
        if not self._targets:
            return
        
        # Создаем задачи для параллельной публикации
        tasks = [
            target.publish_message(message)
            for target in self._targets
        ]
        
        # Выполняем все публикации параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем ошибки
        for target, result in zip(self._targets, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Ошибка при проксировании сообщения: target_name={target.config.name}, error={result}",
                    exc_info=True
                )
                # Продолжаем с другими целями (ошибки уже обработаны)

