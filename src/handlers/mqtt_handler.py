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
from src.service.message_grouping_service import MessageGroupingService
from src.config import TelegramConfig


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
            logger.error(f"Ошибка при проксировании сообщения: {e}", exc_info=True)


class MainBrokerMessageHandler(BaseMQTTMessageHandler):
    """Парсит сообщения и отправляет их в Telegram."""

    def __init__(
        self,
        telegram_repo: TelegramRepository,
        message_service: MessageService,
        telegram_config: TelegramConfig,
        notify_user_ids: Optional[List[int]] = None,
        grouping_service: Optional[MessageGroupingService] = None,
    ):
        """
        Сохраняет зависимости для парсинга и отправки в Telegram.

        Args:
            telegram_repo: Репозиторий для работы с Telegram
            message_service: Сервис обработки сообщений
            telegram_config: Конфигурация Telegram
            notify_user_ids: Список user_id для уведомлений (None = все разрешенные)
            grouping_service: Сервис группировки сообщений (опционально)
        """
        self.telegram_repo = telegram_repo
        self.message_service = message_service
        self.telegram_config = telegram_config
        self.notify_user_ids = notify_user_ids
        self.payload_format = getattr(message_service, "payload_format", "json")
        self.grouping_service = grouping_service
        self._sent_message_ids: Dict[str, int] = {}  # message_id -> telegram_message_id

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

        # Извлекаем ноду-получателя из топика (например, msh/2/json/!12345678)
        receiver_node_id = None
        topic_parts = topic.split("/")
        if len(topic_parts) >= 4:
            potential_node_id = topic_parts[-1]
            if potential_node_id.startswith("!"):
                receiver_node_id = potential_node_id

        # Обработка группировки сообщений
        if (
            self.grouping_service
            and self.telegram_config.message_grouping_enabled
            and message.message_id
        ):
            # Добавляем ноду-получателя в группу
            node_added = self.grouping_service.add_received_node(
                message_id=message.message_id,
                message=message,
                receiver_node_id=receiver_node_id,
                node_cache_service=self.message_service.node_cache_service,
            )

            group = self.grouping_service.get_group(message.message_id)
            if group:
                # Проверяем, есть ли уже telegram_message_id
                if group.telegram_message_id is None:
                    # Первое сообщение - отправляем новое
                    received_by_nodes = [
                        {
                            "node_id": node.node_id,
                            "node_name": node.node_name,
                            "node_short": node.node_short,
                            "received_at": node.received_at,
                            "rssi": node.rssi,
                            "snr": node.snr,
                            "hops_away": node.hops_away,
                            "sender_node": node.sender_node,
                            "sender_node_name": node.sender_node_name,
                        }
                        for node in group.get_unique_nodes()
                    ]

                    telegram_text = message.format_for_telegram_with_grouping(
                        received_by_nodes=received_by_nodes,
                        show_receive_time=self.telegram_config.show_receive_time,
                        node_cache_service=self.message_service.node_cache_service,
                    )

                    try:
                        telegram_message_id = await self.telegram_repo.send_to_group(
                            telegram_text
                        )
                        if telegram_message_id:
                            group.telegram_message_id = telegram_message_id
                            self._sent_message_ids[message.message_id] = telegram_message_id
                            logger.info(
                                f"Отправлено новое группированное сообщение: message_id={message.message_id}, telegram_message_id={telegram_message_id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Ошибка при отправке группированного сообщения: {e}",
                            exc_info=True,
                        )
                elif node_added and self.grouping_service.is_grouping_active(
                    message.message_id
                ):
                    # Обновляем существующее сообщение
                    received_by_nodes = [
                        {
                            "node_id": node.node_id,
                            "node_name": node.node_name,
                            "node_short": node.node_short,
                            "received_at": node.received_at,
                            "rssi": node.rssi,
                            "snr": node.snr,
                            "hops_away": node.hops_away,
                            "sender_node": node.sender_node,
                            "sender_node_name": node.sender_node_name,
                        }
                        for node in group.get_unique_nodes()
                    ]

                    telegram_text = message.format_for_telegram_with_grouping(
                        received_by_nodes=received_by_nodes,
                        show_receive_time=self.telegram_config.show_receive_time,
                        node_cache_service=self.message_service.node_cache_service,
                    )

                    try:
                        await self.telegram_repo.edit_group_message(
                            group.telegram_message_id, telegram_text
                        )
                        logger.info(
                            f"Обновлено группированное сообщение: message_id={message.message_id}, telegram_message_id={group.telegram_message_id}, нод: {len(received_by_nodes)}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Ошибка при редактировании группированного сообщения: {e}",
                            exc_info=True,
                        )
                else:
                    logger.debug(
                        f"Пропущено обновление сообщения: message_id={message.message_id}, node_added={node_added}, grouping_active={self.grouping_service.is_grouping_active(message.message_id)}"
                    )

            # Очищаем истекшие группы
            self.grouping_service.cleanup_expired_groups()
        else:
            # Обычная отправка без группировки
            telegram_text = message.format_for_telegram(
                node_cache_service=self.message_service.node_cache_service
            )

            # Отправляем в групповой чат
            try:
                await self.telegram_repo.send_to_group(telegram_text)
            except Exception as e:
                logger.error(f"Ошибка при отправке в группу: {e}", exc_info=True)

        # Отправляем пользователям (без группировки для личных сообщений)
        if self.notify_user_ids:
            telegram_text = message.format_for_telegram(
                node_cache_service=self.message_service.node_cache_service
            )
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
        telegram_config: TelegramConfig,
        notify_user_ids: Optional[List[int]] = None,
        grouping_service: Optional[MessageGroupingService] = None,
    ):
        """
        Создает оба обработчика - для прокси и для основного брокера.

        Args:
            telegram_repo: Репозиторий для работы с Telegram
            proxy_service: Сервис MQTT прокси
            message_service: Сервис обработки сообщений
            telegram_config: Конфигурация Telegram
            notify_user_ids: Список user_id для уведомлений (None = все разрешенные)
            grouping_service: Сервис группировки сообщений (опционально)
        """
        self.proxy_handler = ProxyMessageHandler(proxy_service)
        self.main_handler = MainBrokerMessageHandler(
            telegram_repo=telegram_repo,
            message_service=message_service,
            telegram_config=telegram_config,
            notify_user_ids=notify_user_ids,
            grouping_service=grouping_service,
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
