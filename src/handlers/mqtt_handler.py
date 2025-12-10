"""
Обработчики входящих MQTT сообщений.

Разделены на отдельные классы:
- BaseMQTTMessageHandler - базовый класс
- ProxyMessageHandler - проксирование сообщений
- MainBrokerMessageHandler - парсинг и отправка в Telegram
- MQTTMessageHandlerImpl - объединяет оба обработчика
"""

import logging
from typing import List, Optional
from abc import ABC, abstractmethod

from src.domain.message import MeshtasticMessage
from src.repo.mqtt_repository import MQTTMessageHandler
from src.repo.telegram_repository import TelegramRepository
from src.service.message_service import MessageService
from src.service.mqtt_proxy_service import MQTTProxyService


logger = logging.getLogger(__name__)


class BaseMQTTMessageHandler(ABC):
    """Базовый класс для обработчиков MQTT сообщений."""

    async def handle_message(self, topic: str, payload: bytes) -> None:
        """
        Обрабатывает входящее сообщение с обработкой ошибок.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах
        """
        try:
            logger.info(
                f"Получено MQTT сообщение: topic={topic}, payload_size={len(payload)}"
            )
            await self._process_message(topic, payload)
        except Exception as e:
            logger.error(
                f"Критическая ошибка при обработке MQTT сообщения: topic={topic}, error={e}",
                exc_info=True,
            )

    @abstractmethod
    async def _process_message(self, topic: str, payload: bytes) -> None:
        """
        Реализуется в наследниках - здесь основная логика обработки.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах
        """
        pass


class ProxyMessageHandler(BaseMQTTMessageHandler):
    """Проксирует все сообщения в другие MQTT брокеры в сыром виде."""

    def __init__(self, proxy_service: MQTTProxyService):
        """
        Сохраняет ссылку на прокси-сервис.

        Args:
            proxy_service: Сервис MQTT прокси
        """
        self.proxy_service = proxy_service

    async def _process_message(self, topic: str, payload: bytes) -> None:
        """
        Отправляет сообщение в прокси-брокеры без парсинга.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах (сырой формат)
        """
        # Создаем минимальный объект сообщения только с исходными данными
        proxy_message = MeshtasticMessage(
            topic=topic,
            raw_payload={},  # Пустой, так как не парсим (для прокси не нужен)
            raw_payload_bytes=payload,  # Исходные данные в сыром виде
        )
        try:
            await self.proxy_service.proxy_message(proxy_message)
            logger.debug(
                f"Сообщение проксировано: topic={topic}, size={len(payload)} bytes"
            )
        except Exception as e:
            logger.error(
                f"Ошибка при проксировании сообщения: {e}",
                exc_info=True)


class MainBrokerMessageHandler(BaseMQTTMessageHandler):
    """Парсит сообщения и отправляет их в Telegram."""

    def __init__(
        self,
        telegram_repo: TelegramRepository,
        message_service: MessageService,
        notify_user_ids: Optional[List[int]] = None,
    ):
        """
        Сохраняет зависимости для парсинга и отправки в Telegram.

        Args:
            telegram_repo: Репозиторий для работы с Telegram
            message_service: Сервис обработки сообщений
            notify_user_ids: Список user_id для уведомлений (None = все разрешенные)
        """
        self.telegram_repo = telegram_repo
        self.message_service = message_service
        self.notify_user_ids = notify_user_ids
        self.payload_format = getattr(
            message_service, "payload_format", "json")

    async def _process_message(self, topic: str, payload: bytes) -> None:
        """
        Парсит сообщение и отправляет в Telegram, если это текстовое сообщение.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах
        """
        # Проверяем формат payload
        is_protobuf_topic = "/e/" in topic and "/json/" not in topic
        if self.payload_format == "json" and is_protobuf_topic:
            logger.debug(
                f"Пропущено protobuf сообщение для парсинга (payload_format=json): topic={topic}"
            )
            return
        if self.payload_format == "protobuf" and not is_protobuf_topic:
            logger.debug(
                f"Пропущено JSON сообщение для парсинга (payload_format=protobuf): topic={topic}"
            )
            return

        # Парсим сообщение
        message: MeshtasticMessage = self.message_service.parse_mqtt_message(
            topic, payload
        )

        # В Telegram отправляем только текстовые сообщения
        # nodeinfo и position используются для обновления кэша
        if message.message_type != "text":
            return

        # Форматируем для Telegram
        telegram_text = message.format_for_telegram(
            node_cache_service=self.message_service.node_cache_service
        )

        # Отправляем в групповой чат
        try:
            await self.telegram_repo.send_to_group(telegram_text)
        except Exception as e:
            logger.error(f"Ошибка при отправке в группу: {e}", exc_info=True)

        # Отправляем пользователям
        if self.notify_user_ids:
            for user_id in self.notify_user_ids:
                if self.telegram_repo.is_user_allowed(user_id):
                    try:
                        await self.telegram_repo.send_to_user(user_id, telegram_text)
                    except Exception as e:
                        logger.error(
                            f"Ошибка при отправке пользователю: user_id={user_id}, error={e}",
                            exc_info=True,
                        )

        logger.info(f"Успешно обработано MQTT сообщение: topic={topic}")


class MQTTMessageHandlerImpl(MQTTMessageHandler):
    """Объединяет проксирование и обработку для основного брокера."""

    def __init__(
        self,
        telegram_repo: TelegramRepository,
        proxy_service: MQTTProxyService,
        message_service: MessageService,
        notify_user_ids: Optional[List[int]] = None,
    ):
        """
        Создает оба обработчика - для прокси и для основного брокера.

        Args:
            telegram_repo: Репозиторий для работы с Telegram
            proxy_service: Сервис MQTT прокси
            message_service: Сервис обработки сообщений
            notify_user_ids: Список user_id для уведомлений (None = все разрешенные)
        """
        self.proxy_handler = ProxyMessageHandler(proxy_service)
        self.main_handler = MainBrokerMessageHandler(
            telegram_repo=telegram_repo,
            message_service=message_service,
            notify_user_ids=notify_user_ids,
        )

    async def handle_message(self, topic: str, payload: bytes) -> None:
        """
        Сначала проксирует сообщение, потом парсит и отправляет в Telegram.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах
        """
        # Проксируем все сообщения в сыром виде
        await self.proxy_handler.handle_message(topic, payload)

        # Парсим и отправляем в Telegram
        await self.main_handler.handle_message(topic, payload)
