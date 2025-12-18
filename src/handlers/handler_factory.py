"""
Фабрика для создания цепочки обработчиков (Factory Pattern).
"""

import logging
from typing import Dict, Any, Optional

from src.handlers.handler_registry import registry, HandlerRegistry
from src.handlers.message_handler_chain import MessageHandler, HandlerConfig
from src.handlers.concrete_handlers import ProxyHandler, TelegramHandler
from src.service.message_processing_strategy import (
    ProcessingMode,
    PrivateModeStrategy,
    GroupModeStrategy,
    AllModeStrategy,
    MessageProcessingStrategy,
)
from src.service.topic_routing_service import TopicRoutingService

logger = logging.getLogger(__name__)


class HandlerChainFactory:
    """Фабрика для создания цепочки обработчиков."""

    @staticmethod
    def create_strategy(
        mode: ProcessingMode,
        send_to_users: bool = False,
        node_cache_service: Optional[Any] = None,
        grouping_service: Optional[Any] = None,
        telegram_config: Optional[Any] = None,
    ) -> MessageProcessingStrategy:
        """
        Создает стратегию обработки по режиму.

        Args:
            mode: Режим обработки
            send_to_users: Отправлять ли также личные сообщения (для GROUP режима)
            node_cache_service: Сервис кэша нод
            grouping_service: Сервис группировки сообщений
            telegram_config: Конфигурация Telegram

        Returns:
            Стратегия обработки сообщений

        Raises:
            ValueError: Если режим неизвестен
        """
        if mode == ProcessingMode.PRIVATE:
            return PrivateModeStrategy(
                node_cache_service=node_cache_service,
                grouping_service=grouping_service,
                telegram_config=telegram_config,
            )
        elif mode == ProcessingMode.GROUP:
            return GroupModeStrategy(
                send_to_users=send_to_users,
                node_cache_service=node_cache_service,
                grouping_service=grouping_service,
                telegram_config=telegram_config,
            )
        elif mode == ProcessingMode.ALL:
            return AllModeStrategy(
                node_cache_service=node_cache_service,
                grouping_service=grouping_service,
                telegram_config=telegram_config,
            )
        else:
            raise ValueError(f"Unknown processing mode: {mode}")

    @staticmethod
    def create_chain(
        handlers_config: Dict[str, Dict[str, Any]],
        dependencies: Dict[str, Any],
        topic_routing_service: Optional[TopicRoutingService] = None,
    ) -> MessageHandler:
        """
        Создает цепочку обработчиков по конфигурации.

        Args:
            handlers_config: Конфигурация обработчиков
                Формат: {"handler_name": {"enabled": True, "priority": 0, ...}}
            dependencies: Зависимости для обработчиков
                Формат: {"handler_name": {"param1": value1, ...}}
            topic_routing_service: Сервис определения режима из топика

        Returns:
            Корневой обработчик цепочки

        Raises:
            ValueError: Если нет включенных обработчиков
        """
        # Регистрируем стандартные обработчики, если еще не зарегистрированы
        if not registry.is_registered("proxy"):
            registry.register(
                "proxy",
                ProxyHandler,
                HandlerConfig(enabled=True, priority=0),
            )
        if not registry.is_registered("telegram"):
            registry.register(
                "telegram",
                TelegramHandler,
                HandlerConfig(enabled=True, priority=1),
            )

        # Создаем обработчики из конфигурации
        handlers = []
        for handler_name, handler_config in sorted(
            handlers_config.items(), key=lambda x: x[1].get("priority", 0)
        ):
            if not handler_config.get("enabled", True):
                logger.debug(f"Обработчик {handler_name} отключен, пропускаем")
                continue

            try:
                # Получаем зависимости для этого обработчика
                handler_deps = dependencies.get(handler_name, {})

                # Для TelegramHandler добавляем topic_routing_service
                if handler_name == "telegram" and topic_routing_service:
                    handler_deps["topic_routing_service"] = topic_routing_service

                # Создаем обработчик
                handler = registry.create_handler(
                    handler_name,
                    HandlerConfig(
                        enabled=handler_config.get("enabled", True),
                        priority=handler_config.get("priority", 0),
                    ),
                    **handler_deps,
                )
                handlers.append(handler)
                logger.debug(f"Создан обработчик: {handler_name}")
            except Exception as e:
                logger.error(
                    f"Ошибка при создании обработчика {handler_name}: {e}",
                    exc_info=True,
                )
                continue

        if not handlers:
            raise ValueError("No enabled handlers found")

        # Связываем обработчики в цепочку
        root = handlers[0]
        current = root
        for handler in handlers[1:]:
            current = current.set_next(handler)

        logger.info(
            f"Создана цепочка обработчиков из {len(handlers)} элементов: "
            f"{', '.join([h.__class__.__name__ for h in handlers])}"
        )
        return root

