"""
Конкретные реализации обработчиков сообщений.
"""

import logging
from typing import Optional, TYPE_CHECKING

from src.handlers.message_handler_chain import MessageHandler, HandlerConfig
from src.domain.message import MeshtasticMessage

if TYPE_CHECKING:
    from src.service.mqtt_proxy_service import MQTTProxyService
    from src.service.message_service import MessageService
    from src.service.message_processing_strategy import MessageProcessingStrategy
    from src.service.topic_routing_service import TopicRoutingService
    from src.repo.telegram_repository import TelegramRepository

logger = logging.getLogger(__name__)


class ProxyHandler(MessageHandler):
    """Обработчик проксирования сообщений в другие MQTT брокеры."""

    def __init__(
        self,
        proxy_service: "MQTTProxyService",
        topic_routing_service: Optional["TopicRoutingService"] = None,
        config: Optional[HandlerConfig] = None,
    ):
        """
        Создает обработчик проксирования.

        Args:
            proxy_service: Сервис MQTT прокси
            topic_routing_service: Сервис определения режима из топика (для фильтрации приватных сообщений)
            config: Конфигурация обработчика
        """
        super().__init__(config)
        self.proxy_service = proxy_service
        self.topic_routing_service = topic_routing_service

    async def _process(self, topic: str, payload: bytes) -> None:
        """
        Проксирует сообщение в другие MQTT брокеры.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах
        """
        # Проверяем режим из топика - приватные сообщения не проксируем
        if self.topic_routing_service:
            routing_mode, _ = self.topic_routing_service.get_effective_mode(topic)
            from src.service.topic_routing_service import RoutingMode

            if routing_mode == RoutingMode.PRIVATE:
                logger.debug(
                    f"Пропущено проксирование приватного сообщения: topic={topic}"
                )
                return

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


class TelegramHandler(MessageHandler):
    """Обработчик отправки сообщений в Telegram."""

    def __init__(
        self,
        strategy: "MessageProcessingStrategy",
        telegram_repo: "TelegramRepository",
        message_service: "MessageService",
        topic_routing_service: "TopicRoutingService",
        notify_user_ids: Optional[list[int]] = None,
        config: Optional[HandlerConfig] = None,
    ):
        """
        Создает обработчик Telegram.

        Args:
            strategy: Стратегия обработки сообщений
            telegram_repo: Репозиторий Telegram
            message_service: Сервис обработки сообщений
            topic_routing_service: Сервис определения режима из топика
            notify_user_ids: Список user_id для уведомлений
            config: Конфигурация обработчика
        """
        super().__init__(config)
        self.strategy = strategy
        self.telegram_repo = telegram_repo
        self.message_service = message_service
        self.topic_routing_service = topic_routing_service
        self.notify_user_ids = notify_user_ids
        self.payload_format = getattr(message_service, "payload_format", "json")

    async def _process(self, topic: str, payload: bytes) -> None:
        """
        Обрабатывает сообщение и отправляет в Telegram согласно стратегии.

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
        try:
            message: MeshtasticMessage = self.message_service.parse_mqtt_message(
                topic, payload
            )
        except Exception as e:
            logger.error(
                f"Ошибка при парсинге сообщения: topic={topic}, error={e}",
                exc_info=True,
            )
            return

        # Определяем режим обработки из топика
        routing_mode, tg_id = self.topic_routing_service.get_effective_mode(topic)

        # Выбираем стратегию на основе режима из топика
        strategy = self._get_strategy_for_mode(routing_mode)

        # Проверяем, нужно ли обрабатывать сообщение
        if not await strategy.should_process(message):
            logger.debug(
                f"Сообщение не требует обработки: topic={topic}, type={message.message_type}"
            )
            return

        # Обрабатываем сообщение согласно стратегии
        try:
            await strategy.process_message(
                message=message,
                telegram_repo=self.telegram_repo,
                topic=topic,
                tg_id=tg_id,
                notify_user_ids=self.notify_user_ids,
            )
            logger.info(
                f"Успешно обработано сообщение: topic={topic}, mode={routing_mode}, type={message.message_type}"
            )
        except Exception as e:
            logger.error(
                f"Ошибка при обработке сообщения: topic={topic}, error={e}",
                exc_info=True,
            )

    def _get_strategy_for_mode(
        self, routing_mode: "RoutingMode"
    ) -> "MessageProcessingStrategy":
        """
        Получает стратегию обработки для режима из топика.

        Args:
            routing_mode: Режим маршрутизации из топика

        Returns:
            Стратегия обработки сообщений
        """
        from src.service.topic_routing_service import RoutingMode as TRoutingMode
        from src.service.message_processing_strategy import (
            PrivateModeStrategy,
            GroupModeStrategy,
            AllModeStrategy,
        )

        # Если стратегия уже соответствует режиму - используем её
        if isinstance(self.strategy, PrivateModeStrategy) and routing_mode in (
            TRoutingMode.PRIVATE,
            TRoutingMode.PRIVATE_GROUP,
        ):
            return self.strategy
        if isinstance(self.strategy, GroupModeStrategy) and routing_mode == TRoutingMode.GROUP:
            return self.strategy
        if isinstance(self.strategy, AllModeStrategy) and routing_mode == TRoutingMode.ALL:
            return self.strategy

        # Создаем новую стратегию на основе режима из топика
        if routing_mode == TRoutingMode.PRIVATE:
            return PrivateModeStrategy(
                node_cache_service=self.strategy.node_cache_service,
                grouping_service=self.strategy.grouping_service,
                telegram_config=self.strategy.telegram_config,
            )
        elif routing_mode == TRoutingMode.GROUP:
            return GroupModeStrategy(
                send_to_users=False,
                node_cache_service=self.strategy.node_cache_service,
                grouping_service=self.strategy.grouping_service,
                telegram_config=self.strategy.telegram_config,
            )
        elif routing_mode == TRoutingMode.PRIVATE_GROUP:
            # Для PRIVATE_GROUP используем GroupModeStrategy с отправкой пользователям
            return GroupModeStrategy(
                send_to_users=True,
                node_cache_service=self.strategy.node_cache_service,
                grouping_service=self.strategy.grouping_service,
                telegram_config=self.strategy.telegram_config,
            )
        else:  # TRoutingMode.ALL
            return AllModeStrategy(
                node_cache_service=self.strategy.node_cache_service,
                grouping_service=self.strategy.grouping_service,
                telegram_config=self.strategy.telegram_config,
            )

