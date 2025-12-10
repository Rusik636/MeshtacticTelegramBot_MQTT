"""
Сервис MQTT прокси.

Пересылает сообщения в другие MQTT брокеры.
Поддерживает несколько прокси-брокеров и параллельную обработку.
"""

import asyncio
import json
import logging
import ssl
from typing import List, Dict, Any, Optional
from aiomqtt import Client as MQTTClient
from aiomqtt.exceptions import MqttError

from src.config import MQTTProxyTargetConfig
from src.domain.message import MeshtasticMessage


logger = logging.getLogger(__name__)


class MQTTProxyTarget:
    """Один прокси-брокер - подключается и публикует сообщения."""

    def __init__(self, config: MQTTProxyTargetConfig, source_topic: str = ""):
        """
        Сохраняет конфигурацию и исходный топик для удаления префикса.

        Args:
            config: Конфигурация целевого брокера
            source_topic: Исходный топик подписки (например, "msh/#") для удаления префикса
        """
        self.config = config
        self.source_topic = source_topic
        self._client: MQTTClient | None = None
        self._connected = False

    async def connect(self) -> None:
        """Подключается к прокси-брокеру с поддержкой TLS."""
        if not self.config.enabled:
            logger.debug(f"Прокси цель отключена: name={self.config.name}")
            return

        try:
            logger.info(
                f"Подключение к целевому MQTT брокеру: name={self.config.name}, "
                f"host={self.config.host}, port={self.config.port}, tls={self.config.tls}"
            )

            client_id = self.config.client_id or f"meshtastic-proxy-{self.config.name}"

            # Настраиваем TLS, если требуется
            tls_context: Optional[ssl.SSLContext] = None
            if self.config.tls:
                tls_context = ssl.create_default_context()
                if self.config.tls_insecure:
                    # Отключаем проверку сертификата (только для
                    # самоподписанных)
                    tls_context.check_hostname = False
                    tls_context.verify_mode = ssl.CERT_NONE
                    logger.warning(
                        f"TLS проверка сертификата отключена для: name={self.config.name}. "
                        f"Используйте только для тестирования или самоподписанных сертификатов!"
                    )

            # В aiomqtt 2.0+ client_id передается через параметр identifier как
            # строка
            client_params = {
                "hostname": self.config.host,
                "port": self.config.port,
                "username": self.config.username,
                "password": self.config.password,
                "identifier": client_id,
            }

            # Добавляем TLS параметры, если требуется
            if tls_context:
                client_params["tls_context"] = tls_context

            self._client = MQTTClient(**client_params)

            await self._client.__aenter__()
            self._connected = True

            logger.info(
                f"Успешно подключен к целевому MQTT брокеру: name={self.config.name}"
            )
        except MqttError as e:
            logger.error(
                f"Ошибка подключения к целевому MQTT брокеру: name={self.config.name}, error={e}",
                exc_info=True,
            )
            self._connected = False
            raise

    async def disconnect(self) -> None:
        """Отключается от целевого MQTT брокера."""
        if self._client and self._connected:
            try:
                await self._client.__aexit__(None, None, None)
                logger.info(
                    f"Отключен от целевого MQTT брокера: name={self.config.name}"
                )
            except Exception as e:
                logger.error(
                    f"Ошибка при отключении от целевого MQTT брокера: name={self.config.name}, error={e}",
                    exc_info=True,
                )
            finally:
                self._client = None
                self._connected = False

    def _normalize_source_topic(self, topic: str) -> str:
        """
        Нормализует топик подписки для удаления префикса.

        Args:
            topic: Исходный топик подписки

        Returns:
            Нормализованный префикс (всегда заканчивается на "/")

        Примеры:
            "msh/#" -> "msh/"
            "msh/2/json/#" -> "msh/2/json/"
            "msh" -> "msh/"
        """
        # Убираем wildcards в конце (# и +)
        normalized = topic.rstrip("#+")
        # Убираем завершающие слэши
        normalized = normalized.rstrip("/")
        # Добавляем один завершающий слэш
        if normalized:
            return f"{normalized}/"
        return ""

    async def publish_message(self, message: MeshtasticMessage) -> None:
        """
        Публикует сообщение в прокси-брокер в сыром виде.

        Args:
            message: Сообщение для публикации
        """
        if not self.config.enabled:
            return

        if not self._connected:
            logger.warning(
                f"Попытка публикации в неподключенный брокер: name={self.config.name}"
            )
            return

        try:
            # Преобразуем топик в строку
            topic = (
                str(message.topic)
                if not isinstance(message.topic, str)
                else message.topic
            )

            # Удаляем префикс исходного топика (например, "msh/" из "msh/#")
            if self.source_topic:
                source_prefix = self._normalize_source_topic(self.source_topic)
                if source_prefix and topic.startswith(source_prefix):
                    # Удаляем префикс исходного топика
                    topic = topic[len(source_prefix) :]
                    # Убираем ведущий слэш, если он есть
                    topic = topic.lstrip("/")
                    logger.debug(
                        f"Удален префикс исходного топика: source_prefix={source_prefix}, "
                        f"remaining_topic={topic}"
                    )

            # Добавляем префикс прокси, если задан
            if self.config.topic_prefix:
                # Убираем завершающий слэш из префикса прокси, если есть
                proxy_prefix = self.config.topic_prefix.rstrip("/")
                if topic:
                    topic = f"{proxy_prefix}/{topic}"
                else:
                    topic = proxy_prefix
                logger.debug(
                    f"Добавлен префикс прокси: proxy_prefix={proxy_prefix}, final_topic={topic}"
                )

            # Публикуем исходный payload в сыром виде
            if message.raw_payload_bytes is not None:
                payload = message.raw_payload_bytes
                logger.debug(
                    f"Публикация raw bytes: name={self.config.name}, "
                    f"topic={topic}, size={len(payload)} bytes"
                )
            else:
                # Fallback - сериализуем JSON, если raw bytes нет
                logger.warning(
                    f"raw_payload_bytes отсутствует, используем JSON: "
                    f"name={self.config.name}, topic={topic}"
                )
                payload = json.dumps(message.raw_payload).encode("utf-8")

            await self._client.publish(topic, payload, qos=self.config.qos)

            logger.debug(
                f"Опубликовано сообщение в целевой брокер: name={self.config.name}, "
                f"topic={topic}, qos={self.config.qos}, payload_size={len(payload)} bytes"
            )
        except MqttError as e:
            logger.error(
                f"Ошибка при публикации в целевой брокер: name={self.config.name}, "
                f"topic={topic}, error={e}",
                exc_info=True,
            )
            # Не пробрасываем исключение, чтобы не прерывать обработку других
            # целей


class MQTTProxyService:
    """Управляет несколькими прокси-брокерами и пересылает в них сообщения."""

    def __init__(self, targets: List[MQTTProxyTargetConfig], source_topic: str = ""):
        """
        Создает список прокси-целей из конфигурации.

        Args:
            targets: Список конфигураций целевых брокеров
            source_topic: Исходный топик подписки (например, "msh/#") для удаления префикса
        """
        self.source_topic = source_topic
        self._targets: List[MQTTProxyTarget] = [
            MQTTProxyTarget(config, source_topic=source_topic)
            for config in targets
            if config.enabled
        ]
        logger.info(
            f"Инициализирован MQTT Proxy Service: targets_count={len(self._targets)}, source_topic={source_topic}"
        )

    async def start(self) -> None:
        """Подключается ко всем прокси-брокерам параллельно."""
        if not self._targets:
            return

        # Подключаемся ко всем брокерам параллельно
        tasks = [target.connect() for target in self._targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Логируем ошибки подключения
        for target, result in zip(self._targets, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Не удалось подключиться к прокси-брокеру: name={target.config.name}, error={result}",
                    exc_info=True,
                )

    async def stop(self) -> None:
        """Отключается от всех прокси-брокеров параллельно."""
        if not self._targets:
            return

        # Отключаемся от всех брокеров параллельно
        tasks = [target.disconnect() for target in self._targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Логируем ошибки отключения
        for target, result in zip(self._targets, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Ошибка при отключении от прокси-брокера: name={target.config.name}, error={result}",
                    exc_info=True,
                )

    async def proxy_message(self, message: MeshtasticMessage) -> None:
        """
        Публикует сообщение во все прокси-брокеры параллельно.

        Args:
            message: Сообщение для проксирования
        """
        if not self._targets:
            return

        # Публикуем во все брокеры одновременно
        tasks = [target.publish_message(message) for target in self._targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Логируем ошибки
        for target, result in zip(self._targets, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Ошибка при проксировании: target={target.config.name}, error={result}",
                    exc_info=True,
                )
