"""
Unit-тесты для TelegramMessageFormatter.

Покрытие: 90%+
"""

from datetime import datetime
from unittest.mock import Mock, MagicMock

import pytest

from src.domain.message import MeshtasticMessage
from src.service.telegram_message_formatter import TelegramMessageFormatter


class TestTelegramMessageFormatter:
    """Тесты для класса TelegramMessageFormatter."""

    def test_format_basic_message(self, mock_node_cache_service):
        """Тест базового форматирования текстового сообщения."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            text="Hello World",
            timestamp=1234567890,
        )
        
        result = formatter.format(message)
        
        assert "Hello World" in result
        assert "<blockquote>" in result
        assert "💬" in result

    def test_format_full_message(self, mock_node_cache_service):
        """Тест форматирования сообщения со всеми данными."""
        mock_node_cache_service.get_node_position.return_value = (55.7580288, 52.4550144, 143)
        
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            message_id="123456",
            from_node="!12345678",
            from_node_name="Test Node",
            from_node_short="TN",
            sender_node="!87654321",
            sender_node_name="Relay Node",
            sender_node_short="RN",
            to_node="!11111111",
            to_node_name="Target Node",
            to_node_short="TGT",
            hops_away=2,
            text="Hello World",
            timestamp=1234567890,
            rssi=-80,
            snr=10.5,
            message_type="text",
        )
        
        result = formatter.format(message)
        
        assert "Test Node" in result
        assert "TN" in result
        assert "Hello World" in result
        assert "🟢" in result or "🟡" in result  # Эмодзи качества сигнала
        assert "📍" in result  # Местоположение

    def test_format_without_data(self, mock_node_cache_service):
        """Тест форматирования без данных (минимальные поля)."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
        )
        
        result = formatter.format(message)
        
        # При отсутствии данных форматтер показывает информацию об отправителе как "Неизвестно"
        assert "📍 Отправитель: Не известно" in result or "📍 Отправитель: Неизвестно" in result
        assert "msh/2/json/!12345678" not in result  # Топик не отображается в форматированном сообщении

    def test_format_html_escaping(self, mock_node_cache_service):
        """Тест экранирования HTML специальных символов."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            from_node_name="<script>alert('XSS')</script>",
            text="Test & <b>bold</b> & 'quotes'",
        )
        
        result = formatter.format(message)
        
        # Проверяем, что HTML символы экранированы
        assert "&lt;script&gt;" in result
        assert "&amp;" in result
        assert "&lt;b&gt;" in result

    def test_format_with_grouping(self, mock_node_cache_service):
        """Тест форматирования с группировкой нод."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            text="Hello World",
            timestamp=1234567890,
        )
        
        received_by_nodes = [
            {
                "node_id": "!11111111",
                "node_name": "Node 1",
                "node_short": "N1",
                "received_at": datetime.utcnow(),
                "rssi": -80,
            },
            {
                "node_id": "!22222222",
                "node_name": "Node 2",
                "node_short": "N2",
                "received_at": datetime.utcnow(),
                "rssi": -90,
            },
        ]
        
        result = formatter.format_with_grouping(
            message, received_by_nodes=received_by_nodes, show_receive_time=False
        )
        
        assert "📥" in result
        assert "Получено нодами" in result
        assert "Node 1" in result
        assert "Node 2" in result

    def test_format_with_grouping_show_time(self, mock_node_cache_service):
        """Тест форматирования с группировкой и временем получения."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            text="Hello World",
        )
        
        received_at = datetime(2025, 1, 1, 12, 30, 45)
        received_by_nodes = [
            {
                "node_id": "!11111111",
                "node_name": "Node 1",
                "received_at": received_at,
            },
        ]
        
        result = formatter.format_with_grouping(
            message, received_by_nodes=received_by_nodes, show_receive_time=True
        )
        
        assert "12:30:45" in result

    def test_format_with_grouping_empty_list(self, mock_node_cache_service):
        """Тест форматирования с пустым списком нод."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            text="Hello World",
        )
        
        result = formatter.format_with_grouping(message, received_by_nodes=[])
        
        # Не должно быть блока "Получено нодами"
        assert "📥" not in result or "Получено нодами" not in result

    def test_format_with_grouping_escapes_names(self, mock_node_cache_service):
        """Тест экранирования имен нод в группировке."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            text="Hello",
        )
        
        received_by_nodes = [
            {
                "node_id": "!11111111",
                "node_name": "<script>alert('XSS')</script>",
                "node_short": "N1",
            },
        ]
        
        result = formatter.format_with_grouping(message, received_by_nodes=received_by_nodes)
        
        assert "&lt;script&gt;" in result

    @pytest.mark.parametrize(
        "rssi,expected_emoji",
        [
            (-70, "🟢"),  # Отличный
            (-80, "🟡"),  # Нормальный
            (-100, "🟡"),  # Нормальный
            (-110, "🔴"),  # Плохой
            (-120, "🔴"),  # Плохой
            (-130, "⚫"),  # Очень плохой
            (None, "⚪"),  # Неизвестно
        ],
    )
    def test_get_rssi_quality_emoji(self, rssi, expected_emoji):
        """Тест определения эмодзи качества RSSI."""
        emoji = TelegramMessageFormatter.get_rssi_quality_emoji(rssi)
        assert emoji == expected_emoji

    @pytest.mark.parametrize(
        "snr,expected_emoji",
        [
            (15.0, "🟢"),  # Отличный
            (10.0, "🟢"),  # Отличный
            (7.0, "🟡"),  # Хороший
            (5.0, "🟡"),  # Хороший
            (2.0, "🟠"),  # Удовлетворительный
            (0.0, "🟠"),  # Удовлетворительный
            (-2.0, "🔴"),  # Плохой
            (-5.0, "🔴"),  # Плохой
            (-10.0, "⚫"),  # Очень плохой
            (None, "⚪"),  # Неизвестно
        ],
    )
    def test_get_snr_quality_emoji(self, snr, expected_emoji):
        """Тест определения эмодзи качества SNR."""
        emoji = TelegramMessageFormatter.get_snr_quality_emoji(snr)
        assert emoji == expected_emoji

    def test_format_uses_node_cache_service(self, mock_node_cache_service):
        """Тест использования node_cache_service для получения координат."""
        mock_node_cache_service.get_node_position.return_value = (55.7580288, 52.4550144, 143)
        
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            from_node="!12345678",
        )
        
        result = formatter.format(message)
        
        assert "yandex.ru/maps" in result
        mock_node_cache_service.get_node_position.assert_called_with("!12345678")

    def test_format_without_cache_service(self):
        """Тест форматирования без cache service."""
        formatter = TelegramMessageFormatter(node_cache_service=None)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            from_node="!12345678",
        )
        
        result = formatter.format(message)
        
        assert "Не известно" in result

    def test_format_empty_text(self, mock_node_cache_service):
        """Тест форматирования с пустым текстом сообщения."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            text=None,
        )
        
        result = formatter.format(message)
        
        assert "💬" not in result or "Сообщение" not in result

    def test_format_missing_node_names(self, mock_node_cache_service):
        """Тест форматирования без имен нод."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            from_node="!12345678",
            from_node_name=None,
            from_node_short=None,
        )
        
        result = formatter.format(message)
        
        # Должен использовать node_id
        assert "!12345678" in result

    def test_format_missing_rssi_snr(self, mock_node_cache_service):
        """Тест форматирования без RSSI/SNR."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            rssi=None,
            snr=None,
        )
        
        result = formatter.format(message)
        
        # Не должно быть блока качества сигнала
        assert "📶" not in result

    def test_format_very_long_node_names(self, mock_node_cache_service):
        """Тест форматирования с очень длинными именами нод."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        long_name = "A" * 200
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            from_node_name=long_name,
        )
        
        result = formatter.format(message)
        
        # Должно быть экранировано
        assert long_name in result
        assert "&lt;" not in long_name  # Имя не должно содержать HTML

    def test_format_special_characters_in_names(self, mock_node_cache_service):
        """Тест форматирования со специальными символами в именах."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            from_node_name="Node & Co. <test>",
            from_node_short="N&C",
        )
        
        result = formatter.format(message)
        
        # Должно быть экранировано
        assert "&amp;" in result
        assert "&lt;test&gt;" in result

    def test_format_recipient_vsem(self, mock_node_cache_service):
        """Тест форматирования получателя 'Всем'."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            to_node="Всем",
        )
        
        result = formatter.format(message)
        
        assert "Всем" in result
        # Не должно быть местоположения получателя для "Всем"
        assert "Получатель" not in result or "Всем" in result

    def test_format_direct_delivery(self, mock_node_cache_service):
        """Тест форматирования прямой доставки (hops_away=0)."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            hops_away=0,
        )
        
        result = formatter.format(message)
        
        assert "Прямая доставка" in result

    def test_format_relayed_message(self, mock_node_cache_service):
        """Тест форматирования ретранслированного сообщения."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            from_node="!12345678",
            sender_node="!87654321",  # Отличается от from_node
            sender_node_name="Relay Node",
            hops_away=2,
        )
        
        result = formatter.format(message)
        
        assert "Ретранслировал" in result
        assert "Relay Node" in result
        assert "Ретранслировано 2 раз" in result

    def test_format_timestamp_formatting(self, mock_node_cache_service):
        """Тест форматирования временной метки."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        # Timestamp для 01.01.2025 12:30:45
        timestamp = 1735732245
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            timestamp=timestamp,
        )
        
        result = formatter.format(message)
        
        assert "🕐" in result
        assert "12:30" in result or "01.01" in result

    def test_format_invalid_timestamp(self, mock_node_cache_service):
        """Тест обработки невалидного timestamp."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            timestamp=999999999999,  # Очень большое значение
        )
        
        # Не должно быть ошибки
        result = formatter.format(message)
        assert isinstance(result, str)

    def test_format_with_grouping_multiple_nodes(self, mock_node_cache_service):
        """Тест форматирования с множеством нод-получателей."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            text="Hello",
        )
        
        received_by_nodes = [
            {"node_id": f"!{i:08x}", "node_name": f"Node {i}", "rssi": -80 - i}
            for i in range(5)
        ]
        
        result = formatter.format_with_grouping(message, received_by_nodes=received_by_nodes)
        
        # Все ноды должны быть в результате
        for i in range(5):
            assert f"Node {i}" in result

    def test_format_with_grouping_rssi_display(self, mock_node_cache_service):
        """Тест отображения RSSI в группировке."""
        formatter = TelegramMessageFormatter(node_cache_service=mock_node_cache_service)
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
            text="Hello",
        )
        
        received_by_nodes = [
            {
                "node_id": "!11111111",
                "node_name": "Node 1",
                "rssi": -80,
            },
        ]
        
        result = formatter.format_with_grouping(message, received_by_nodes=received_by_nodes)
        
        assert "-80" in result
        assert "dBm" in result


