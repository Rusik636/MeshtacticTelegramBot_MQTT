"""
Настройка DI-контейнера для приложения.

Регистрирует все зависимости и их жизненный цикл.
"""

import logging

from src.infrastructure.di_container import DIContainer, Lifetime
from src.infrastructure.file_storage import LocalFileStorage, FileStorage
from src.infrastructure.telegram_connection import TelegramConnectionManager
from src.config import AppConfig
from src.service.topic_routing_service import TopicRoutingService, RoutingMode
from src.service.message_processing_strategy import ProcessingMode

logger = logging.getLogger(__name__)


def setup_container(config: AppConfig) -> DIContainer:
    """
    Настраивает DI-контейнер со всеми зависимостями.

    Args:
        config: Конфигурация приложения

    Returns:
        Настроенный DI-контейнер
    """
    container = DIContainer()

    # Регистрируем конфигурацию (должна быть первой)
    container.register_singleton("config", config)

    # Регистрируем инфраструктурные зависимости
    container.register_singleton("file_storage", LocalFileStorage(), FileStorage)
    container.register_singleton(
        "telegram_connection", TelegramConnectionManager(config.telegram)
    )

    # Регистрируем сервисы кэша
    container.register_factory(
        "node_cache_service",
        lambda: _create_node_cache_service(container),
        Lifetime.SINGLETON,
    )

    # Регистрируем сервисы обработки сообщений
    container.register_factory(
        "message_factory",
        lambda: _create_message_factory(container),
        Lifetime.SINGLETON,
    )

    container.register_factory(
        "node_cache_updater",
        lambda: _create_node_cache_updater(container),
        Lifetime.SINGLETON,
    )

    container.register_factory(
        "message_service",
        lambda: _create_message_service(container),
        Lifetime.SINGLETON,
    )

    container.register_factory(
        "telegram_message_formatter",
        lambda: _create_telegram_message_formatter(container),
        Lifetime.SINGLETON,
    )

    # Регистрируем сервисы группировки и маршрутизации
    container.register_factory(
        "message_grouping_service",
        lambda: _create_message_grouping_service(container),
        Lifetime.SINGLETON,
    )

    container.register_factory(
        "topic_routing_service",
        lambda: _create_topic_routing_service(container),
        Lifetime.SINGLETON,
    )

    # Регистрируем репозитории
    container.register_factory(
        "telegram_repository",
        lambda: _create_telegram_repository(container),
        Lifetime.SINGLETON,
    )

    # Регистрируем MQTT сервисы
    container.register_factory(
        "main_broker_service",
        lambda: _create_main_broker_service(container),
        Lifetime.SINGLETON,
    )

    container.register_factory(
        "mqtt_proxy_service",
        lambda: _create_mqtt_proxy_service(container),
        Lifetime.SINGLETON,
    )

    logger.info("DI-контейнер настроен со всеми сервисами")
    return container


def _create_node_cache_service(container: DIContainer):
    """Создает NodeCacheService."""
    from src.service.node_cache_service import NodeCacheService

    file_storage = container.resolve("file_storage")
    config = container.resolve("config")
    return NodeCacheService(
        cache_file="data/nodes_cache.json", file_storage=file_storage
    )


def _create_message_factory(container: DIContainer):
    """Создает MessageFactory."""
    from src.service.message_factory import MessageFactory

    node_cache_service = container.resolve("node_cache_service")
    return MessageFactory(node_cache_service=node_cache_service)


def _create_node_cache_updater(container: DIContainer):
    """Создает NodeCacheUpdater."""
    from src.service.node_cache_updater import NodeCacheUpdater

    node_cache_service = container.resolve("node_cache_service")
    return NodeCacheUpdater(node_cache_service=node_cache_service)


def _create_message_service(container: DIContainer):
    """Создает MessageService."""
    from src.service.message_service import MessageService

    node_cache_service = container.resolve("node_cache_service")
    message_factory = container.resolve("message_factory")
    node_cache_updater = container.resolve("node_cache_updater")
    config = container.resolve("config")

    return MessageService(
        node_cache_service=node_cache_service,
        payload_format=config.mqtt_source.payload_format,
        message_factory=message_factory,
        node_cache_updater=node_cache_updater,
    )


def _create_telegram_message_formatter(container: DIContainer):
    """Создает TelegramMessageFormatter."""
    from src.service.telegram_message_formatter import TelegramMessageFormatter

    node_cache_service = container.resolve("node_cache_service")
    return TelegramMessageFormatter(node_cache_service=node_cache_service)


def _create_message_grouping_service(container: DIContainer):
    """Создает MessageGroupingService."""
    from src.service.message_grouping_service import MessageGroupingService

    config = container.resolve("config")
    return MessageGroupingService(
        grouping_timeout_seconds=config.telegram.message_grouping_timeout
    )


def _create_topic_routing_service(container: DIContainer):
    """Создает TopicRoutingService."""
    config = container.resolve("config")

    default_routing_mode = RoutingMode.ALL
    if config.message_processing.default_mode == "private":
        default_routing_mode = RoutingMode.PRIVATE
    elif config.message_processing.default_mode == "group":
        default_routing_mode = RoutingMode.GROUP

    return TopicRoutingService(default_mode=default_routing_mode)


def _create_telegram_repository(container: DIContainer):
    """Создает AsyncTelegramRepository."""
    from src.repo.telegram_repository import AsyncTelegramRepository

    config = container.resolve("config")
    telegram_connection = container.resolve("telegram_connection")
    return AsyncTelegramRepository(
        config.telegram, connection_manager=telegram_connection
    )


def _create_main_broker_service(container: DIContainer):
    """Создает MainBrokerService."""
    from src.service.main_broker_service import MainBrokerService

    config = container.resolve("config")
    return MainBrokerService(config.mqtt_source)


def _create_mqtt_proxy_service(container: DIContainer):
    """Создает MQTTProxyService."""
    from src.service.mqtt_proxy_service import MQTTProxyService

    config = container.resolve("config")
    return MQTTProxyService(
        config.mqtt_proxy_targets, source_topic=config.mqtt_source.topic
    )

