"""
Интеграционный тест для проверки работы группировки нод при редактировании Telegram-сообщения.

Проверяет полный путь от получения MQTT сообщения до редактирования сообщения в Telegram
со списком полученных нод.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, call

import pytest

from src.domain.message import MeshtasticMessage
from src.handlers.concrete_handlers import TelegramHandler
from src.service.message_factory import MessageFactory
from src.service.message_grouping_service import MessageGroupingService
from src.service.message_processing_strategy import GroupModeStrategy
from src.service.message_service import MessageService
from src.service.node_cache_service import NodeCacheService
from src.service.node_cache_updater import NodeCacheUpdater
from src.service.telegram_message_formatter import TelegramMessageFormatter
from src.service.topic_routing_service import TopicRoutingService, RoutingMode
from src.config import TelegramConfig


@pytest.fixture
def mock_telegram_repo():
    """Мок Telegram репозитория с отслеживанием вызовов."""
    repo = AsyncMock()
    # Настраиваем send_to_group для возврата message_id
    telegram_message_id_counter = [10000]  # Используем список для изменяемого значения
    
    async def send_to_group_side_effect(text: str):
        """Возвращает следующий telegram_message_id."""
        message_id = telegram_message_id_counter[0]
        telegram_message_id_counter[0] += 1
        return message_id
    
    repo.send_to_group = AsyncMock(side_effect=send_to_group_side_effect)
    repo.edit_group_message = AsyncMock()
    repo.is_user_allowed = Mock(return_value=True)
    repo.bot = MagicMock()
    return repo


@pytest.fixture
def mock_node_cache_service():
    """Мок сервиса кэша нод с данными о нодах."""
    service = MagicMock()
    
    # Настраиваем возвращаемые значения для разных нод
    def get_node_name(node_id: str):
        node_names = {
            "!12345678": "Node One",
            "!87654321": "Node Two",
        }
        return node_names.get(node_id)
    
    def get_node_shortname(node_id: str):
        node_shortnames = {
            "!12345678": "N1",
            "!87654321": "N2",
        }
        return node_shortnames.get(node_id)
    
    service.get_node_name = Mock(side_effect=get_node_name)
    service.get_node_shortname = Mock(side_effect=get_node_shortname)
    service.get_node_position = Mock(return_value=None)
    service.update_node_info = Mock()
    service.update_node_position = Mock()
    return service


@pytest.fixture
def telegram_config():
    """Конфигурация Telegram с включенной группировкой."""
    return TelegramConfig(
        bot_token="test_token",
        group_chat_id=-1001234567890,
        allowed_user_ids=[123456789],
        show_receive_time=False,
        message_grouping_enabled=True,
        message_grouping_timeout=30,
    )


@pytest.fixture
def node_cache_service(mock_node_cache_service):
    """Используем мок node_cache_service."""
    return mock_node_cache_service


@pytest.fixture
def message_factory(node_cache_service):
    """Фабрика сообщений."""
    return MessageFactory(node_cache_service=node_cache_service)


@pytest.fixture
def node_cache_updater(node_cache_service):
    """Обновлятор кэша нод."""
    return NodeCacheUpdater(node_cache_service=node_cache_service)


@pytest.fixture
def message_service(message_factory, node_cache_updater, node_cache_service):
    """Сервис обработки сообщений."""
    return MessageService(
        node_cache_service=node_cache_service,
        payload_format="json",
        message_factory=message_factory,
        node_cache_updater=node_cache_updater,
    )


@pytest.fixture
def message_formatter(node_cache_service):
    """Форматтер сообщений для Telegram."""
    return TelegramMessageFormatter(node_cache_service=node_cache_service)


@pytest.fixture
def grouping_service():
    """Сервис группировки сообщений."""
    return MessageGroupingService(grouping_timeout_seconds=30)


@pytest.fixture
def topic_routing_service():
    """Сервис определения режима из топика."""
    return TopicRoutingService()


@pytest.fixture
def group_mode_strategy(grouping_service, telegram_config, message_formatter, node_cache_service):
    """Стратегия обработки сообщений в групповом режиме."""
    return GroupModeStrategy(
        grouping_service=grouping_service,
        telegram_config=telegram_config,
        message_formatter=message_formatter,
        node_cache_service=node_cache_service,
    )


@pytest.fixture
def telegram_handler(
    group_mode_strategy,
    mock_telegram_repo,
    message_service,
    topic_routing_service,
):
    """Обработчик Telegram сообщений."""
    return TelegramHandler(
        strategy=group_mode_strategy,
        telegram_repo=mock_telegram_repo,
        message_service=message_service,
        topic_routing_service=topic_routing_service,
    )


@pytest.mark.asyncio
async def test_message_grouping_integration(
    telegram_handler,
    mock_telegram_repo,
    grouping_service,
    message_service,
    node_cache_service,
):
    """
    Интеграционный тест группировки сообщений.
    
    Проверяет полный путь:
    1. Получение первого MQTT сообщения от ноды 1
    2. Отправка нового сообщения в Telegram
    3. Получение второго MQTT сообщения с тем же message_id от ноды 2
    4. Редактирование сообщения в Telegram с добавлением второй ноды
    """
    # Шаг 1: Подготовка первого MQTT сообщения от ноды 1
    message_id = "1234567890"
    topic1 = "msh/group/2/json/!12345678"  # Нода 1 получила сообщение
    
    payload1 = json.dumps({
        "type": "text",
        "id": message_id,
        "from": "!11111111",  # Отправитель
        "to": "!ffffffff",  # Всем
        "text": "Test message",
        "timestamp": int(datetime.utcnow().timestamp()),
        "rssi": -80,
        "snr": 10.5,
        "hops_away": 0,
    }).encode("utf-8")
    
    # Шаг 2: Обработка первого сообщения
    await telegram_handler._process(topic1, payload1)
    
    # Проверка 1: Сообщение должно быть отправлено в Telegram
    assert mock_telegram_repo.send_to_group.called, "Первое сообщение должно быть отправлено в Telegram"
    send_call_args = mock_telegram_repo.send_to_group.call_args
    assert send_call_args is not None, "Должен быть вызов send_to_group"
    
    # Получаем telegram_message_id из первого вызова
    # send_to_group возвращает message_id через side_effect
    telegram_message_id = 10000  # Первое значение из side_effect
    
    # Проверка 2: Группа должна быть создана
    group = grouping_service.get_group(message_id)
    assert group is not None, "Группа должна быть создана"
    assert group.message_id == message_id, "ID группы должен совпадать"
    assert group.telegram_message_id == telegram_message_id, "Telegram message ID должен быть сохранен"
    assert len(group.get_unique_nodes()) == 1, "В группе должна быть одна нода"
    assert group.get_unique_nodes()[0].node_id == "!12345678", "Нода должна быть !12345678"
    
    # Проверка 3: Текст сообщения должен содержать информацию о первой ноде
    sent_text = send_call_args[0][0] if send_call_args[0] else ""
    assert "Test message" in sent_text, "Текст сообщения должен содержать исходный текст"
    assert "Node One" in sent_text or "N1" in sent_text or "!12345678" in sent_text, \
        "Текст должен содержать информацию о первой ноде"
    assert "📥" in sent_text or "Получено нодами" in sent_text, \
        "Текст должен содержать блок 'Получено нодами'"
    
    # Шаг 3: Подготовка второго MQTT сообщения от ноды 2 (тот же message_id)
    topic2 = "msh/group/2/json/!87654321"  # Нода 2 получила то же сообщение
    
    payload2 = json.dumps({
        "type": "text",  # Может быть None для ретранслированных сообщений
        "id": message_id,  # Тот же message_id
        "from": "!11111111",  # Тот же отправитель
        "to": "!ffffffff",  # Всем
        "text": "Test message",  # Тот же текст
        "timestamp": int(datetime.utcnow().timestamp()),
        "rssi": -90,
        "snr": 8.5,
        "hops_away": 1,  # Ретранслировано через одну ноду
    }).encode("utf-8")
    
    # Шаг 4: Обработка второго сообщения
    await telegram_handler._process(topic2, payload2)
    
    # Проверка 4: Сообщение должно быть отредактировано (не отправлено новое)
    assert mock_telegram_repo.send_to_group.call_count == 1, \
        "send_to_group должен быть вызван только один раз (для первого сообщения)"
    assert mock_telegram_repo.edit_group_message.called, \
        "edit_group_message должен быть вызван для обновления сообщения"
    
    # Проверка 5: Группа должна содержать обе ноды
    group = grouping_service.get_group(message_id)
    assert group is not None, "Группа должна существовать"
    unique_nodes = group.get_unique_nodes()
    assert len(unique_nodes) == 2, f"В группе должно быть 2 ноды, получено: {len(unique_nodes)}"
    
    node_ids = {node.node_id for node in unique_nodes}
    assert "!12345678" in node_ids, "Группа должна содержать ноду !12345678"
    assert "!87654321" in node_ids, "Группа должна содержать ноду !87654321"
    
    # Проверка 6: edit_group_message должен быть вызван с правильными параметрами
    edit_call = mock_telegram_repo.edit_group_message.call_args
    assert edit_call is not None, "Должен быть вызов edit_group_message"
    assert edit_call[0][0] == telegram_message_id, \
        f"edit_group_message должен быть вызван с telegram_message_id={telegram_message_id}"
    
    edited_text = edit_call[0][1]
    assert "Test message" in edited_text, "Отредактированный текст должен содержать исходный текст"
    assert "📥" in edited_text or "Получено нодами" in edited_text, \
        "Отредактированный текст должен содержать блок 'Получено нодами'"
    
    # Проверка 7: Отредактированный текст должен содержать информацию о обеих нодах
    assert "Node One" in edited_text or "N1" in edited_text or "!12345678" in edited_text, \
        "Отредактированный текст должен содержать информацию о первой ноде"
    assert "Node Two" in edited_text or "N2" in edited_text or "!87654321" in edited_text, \
        "Отредактированный текст должен содержать информацию о второй ноде"
    
    # Проверка 8: RSSI/SNR для обеих нод должны быть в тексте (если валидные)
    # Первая нода: rssi=-80, snr=10.5
    # Вторая нода: rssi=-90, snr=8.5
    assert "-80" in edited_text or "🟡" in edited_text, \
        "Текст должен содержать RSSI первой ноды или соответствующий эмодзи"
    assert "-90" in edited_text or "🟡" in edited_text, \
        "Текст должен содержать RSSI второй ноды или соответствующий эмодзи"


@pytest.mark.asyncio
async def test_message_grouping_with_relayed_message(
    telegram_handler,
    mock_telegram_repo,
    grouping_service,
):
    """
    Тест группировки с ретранслированным сообщением (message_type=None).
    
    Проверяет, что ретранслированные сообщения с message_type=None
    также корректно добавляются в группу.
    """
    message_id = "9876543210"
    topic1 = "msh/group/2/json/!12345678"
    
    # Первое сообщение - обычное текстовое
    payload1 = json.dumps({
        "type": "text",
        "id": message_id,
        "from": "!11111111",
        "to": "!ffffffff",
        "text": "Relayed test",
        "timestamp": int(datetime.utcnow().timestamp()),
    }).encode("utf-8")
    
    await telegram_handler._process(topic1, payload1)
    
    # Получаем telegram_message_id из вызова
    telegram_message_id = 10000  # Первое значение из side_effect
    
    # Второе сообщение - ретранслированное (message_type может быть None)
    topic2 = "msh/group/2/json/!87654321"
    payload2 = json.dumps({
        "type": None,  # Ретранслированное сообщение
        "id": message_id,  # Тот же message_id
        "from": "!11111111",
        "to": "!ffffffff",
        "text": "Relayed test",
        "timestamp": int(datetime.utcnow().timestamp()),
    }).encode("utf-8")
    
    await telegram_handler._process(topic2, payload2)
    
    # Проверка: сообщение должно быть отредактировано
    assert mock_telegram_repo.edit_group_message.called, \
        "Ретранслированное сообщение должно обновить группу"
    
    # Проверка: группа должна содержать обе ноды
    group = grouping_service.get_group(message_id)
    assert group is not None, "Группа должна существовать"
    assert len(group.get_unique_nodes()) == 2, \
        "Группа должна содержать обе ноды (включая ретранслированную)"


@pytest.mark.asyncio
async def test_message_grouping_duplicate_node(
    telegram_handler,
    mock_telegram_repo,
    grouping_service,
):
    """
    Тест группировки с дублирующейся нодой.
    
    Проверяет, что если одна и та же нода получает сообщение дважды,
    она не добавляется повторно в группу.
    """
    message_id = "5555555555"
    topic = "msh/group/2/json/!12345678"
    
    payload = json.dumps({
        "type": "text",
        "id": message_id,
        "from": "!11111111",
        "to": "!ffffffff",
        "text": "Duplicate test",
        "timestamp": int(datetime.utcnow().timestamp()),
    }).encode("utf-8")
    
    # Первая обработка
    await telegram_handler._process(topic, payload)
    
    # Получаем telegram_message_id из вызова
    telegram_message_id = 10000  # Первое значение из side_effect
    
    # Вторая обработка того же сообщения от той же ноды
    await telegram_handler._process(topic, payload)
    
    # Проверка: edit_group_message НЕ должен быть вызван (нода уже в группе)
    # или должен быть вызван, но без изменений
    group = grouping_service.get_group(message_id)
    assert group is not None, "Группа должна существовать"
    assert len(group.get_unique_nodes()) == 1, \
        "В группе должна быть только одна нода (дубликаты не добавляются)"

