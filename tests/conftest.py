"""
Общие фикстуры для всех unit-тестов.

Содержит моки для внешних зависимостей и тестовые данные.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from src.domain.message import MeshtasticMessage
from src.config import MQTTBrokerConfig, TelegramConfig


# ============================================================================
# Фикстуры для моков внешних зависимостей
# ============================================================================


@pytest.fixture
def mock_file_storage():
    """
    Мок файлового хранилища.
    
    Returns:
        MagicMock с методами read_json, write_json, exists, ensure_directory
    """
    storage = MagicMock()
    storage.read_json = Mock(return_value={"nodes": [], "last_saved": None})
    storage.write_json = Mock()
    storage.exists = Mock(return_value=False)
    storage.ensure_directory = Mock()
    return storage


@pytest.fixture
def mock_node_cache_service():
    """
    Мок сервиса кэша нод.
    
    Returns:
        MagicMock с методами get_node_name, get_node_shortname, get_node_position,
        update_node_info, update_node_position
    """
    service = MagicMock()
    service.get_node_name = Mock(return_value=None)
    service.get_node_shortname = Mock(return_value=None)
    service.get_node_position = Mock(return_value=None)
    service.update_node_info = Mock(return_value=True)
    service.update_node_position = Mock(return_value=True)
    return service


@pytest.fixture
def mock_telegram_repo():
    """
    Мок Telegram репозитория.
    
    Returns:
        AsyncMock с async методами send_to_user, send_to_group, edit_message,
        и синхронным методом is_user_allowed
    """
    repo = AsyncMock()
    repo.send_to_user = AsyncMock()
    repo.send_to_group = AsyncMock(return_value=12345)  # Возвращает message_id
    repo.edit_message = AsyncMock()
    repo.edit_group_message = AsyncMock()
    repo.is_user_allowed = Mock(return_value=True)
    repo.bot = MagicMock()
    return repo


@pytest.fixture
def mock_mqtt_repo():
    """
    Мок MQTT репозитория.
    
    Returns:
        AsyncMock с async методами connect, disconnect, subscribe, publish
    """
    repo = AsyncMock()
    repo.connect = AsyncMock()
    repo.disconnect = AsyncMock()
    repo.subscribe = AsyncMock()
    repo.publish = AsyncMock()
    return repo


@pytest.fixture
def mock_mqtt_connection_manager():
    """
    Мок менеджера подключения к MQTT.
    
    Returns:
        MagicMock с async методами connect, disconnect и свойствами client, is_connected
    """
    manager = MagicMock()
    manager.connect = AsyncMock()
    manager.disconnect = AsyncMock()
    manager.client = None
    manager.is_connected = False
    return manager


@pytest.fixture
def mock_telegram_connection_manager():
    """
    Мок менеджера подключения к Telegram.
    
    Returns:
        MagicMock со свойством bot
    """
    manager = MagicMock()
    manager.bot = MagicMock()
    return manager


@pytest.fixture
def mock_message_factory():
    """
    Мок фабрики сообщений.
    
    Returns:
        MagicMock с методом create_message
    """
    factory = MagicMock()
    factory.create_message = Mock(return_value=MagicMock(spec=MeshtasticMessage))
    return factory


@pytest.fixture
def mock_node_cache_updater():
    """
    Мок обновлятора кэша нод.
    
    Returns:
        MagicMock с методом update_from_message
    """
    updater = MagicMock()
    updater.update_from_message = Mock()
    return updater


# ============================================================================
# Фикстуры для тестовых данных
# ============================================================================


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """
    Временная директория для тестов.
    
    Args:
        tmp_path: Фикстура pytest для временной директории
        
    Returns:
        Path к временной директории
    """
    return tmp_path


@pytest.fixture
def sample_text_message_payload() -> Dict[str, Any]:
    """
    Пример payload текстового сообщения Meshtastic.
    
    Returns:
        Словарь с данными текстового сообщения
    """
    return {
        "type": "text",
        "id": "123456",
        "from": "!12345678",
        "to": "!87654321",
        "text": "Hello World",
        "timestamp": 1234567890,
        "rssi": -80,
        "snr": 10.5,
        "hops_away": 2,
        "sender": "!12345678",
    }


@pytest.fixture
def sample_nodeinfo_payload() -> Dict[str, Any]:
    """
    Пример payload nodeinfo сообщения Meshtastic.
    
    Returns:
        Словарь с данными nodeinfo сообщения
    """
    return {
        "type": "nodeinfo",
        "from": "!12345678",
        "payload": {
            "id": "!12345678",
            "longname": "Test Node",
            "shortname": "TN",
        },
    }


@pytest.fixture
def sample_position_payload() -> Dict[str, Any]:
    """
    Пример payload position сообщения Meshtastic.
    
    Returns:
        Словарь с данными position сообщения
    """
    return {
        "type": "position",
        "from": "!12345678",
        "payload": {
            "latitude_i": 557580288,  # 55.7580288 * 1e7
            "longitude_i": 524550144,  # 52.4550144 * 1e7
            "altitude": 143,
        },
    }


@pytest.fixture
def sample_meshtastic_message(sample_text_message_payload: Dict[str, Any]) -> MeshtasticMessage:
    """
    Пример объекта MeshtasticMessage.
    
    Args:
        sample_text_message_payload: Фикстура с payload текстового сообщения
        
    Returns:
        Объект MeshtasticMessage
    """
    return MeshtasticMessage(
        topic="msh/2/json/!12345678",
        raw_payload=sample_text_message_payload,
        message_id="123456",
        from_node="!12345678",
        to_node="!87654321",
        text="Hello World",
        timestamp=1234567890,
        rssi=-80,
        snr=10.5,
        hops_away=2,
        message_type="text",
    )


@pytest.fixture
def sample_mqtt_broker_config() -> MQTTBrokerConfig:
    """
    Пример конфигурации MQTT брокера.
    
    Returns:
        Объект MQTTBrokerConfig
    """
    return MQTTBrokerConfig(
        host="localhost",
        port=1883,
        username="test_user",
        password="test_pass",
        client_id="test_client",
        topic="msh/2/json/#",
        qos=1,
        keepalive=60,
        payload_format="json",
    )


@pytest.fixture
def sample_telegram_config() -> TelegramConfig:
    """
    Пример конфигурации Telegram бота.
    
    Returns:
        Объект TelegramConfig
    """
    return TelegramConfig(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        group_chat_id=-1001234567890,
        allowed_user_ids=[123456789],
        show_receive_time=False,
        message_grouping_enabled=True,
        message_grouping_timeout=30,
    )


# ============================================================================
# Фикстуры для сервисов
# ============================================================================


@pytest.fixture
def node_cache_service(mock_file_storage, temp_dir: Path):
    """
    Реальный NodeCacheService с временным файлом.
    
    Args:
        mock_file_storage: Мок файлового хранилища
        temp_dir: Временная директория
        
    Returns:
        Экземпляр NodeCacheService
    """
    from src.service.node_cache_service import NodeCacheService
    
    cache_file = temp_dir / "nodes_cache.json"
    return NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)


@pytest.fixture
def message_factory(mock_node_cache_service):
    """
    MessageFactory с моком node_cache_service.
    
    Args:
        mock_node_cache_service: Мок сервиса кэша нод
        
    Returns:
        Экземпляр MessageFactory
    """
    from src.service.message_factory import MessageFactory
    
    return MessageFactory(node_cache_service=mock_node_cache_service)


@pytest.fixture
def node_cache_updater(mock_node_cache_service):
    """
    NodeCacheUpdater с моком node_cache_service.
    
    Args:
        mock_node_cache_service: Мок сервиса кэша нод
        
    Returns:
        Экземпляр NodeCacheUpdater
    """
    from src.service.node_cache_updater import NodeCacheUpdater
    
    return NodeCacheUpdater(node_cache_service=mock_node_cache_service)


# ============================================================================
# Настройки pytest
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def setup_test_logging():
    """Настройка логирования для тестов."""
    import logging
    
    logging.basicConfig(
        level=logging.WARNING,  # Минимальный уровень для тестов
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


# Настройка asyncio mode для pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

