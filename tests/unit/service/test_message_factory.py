"""
Unit-тесты для MessageFactory.

Покрытие: 95%+
"""

from unittest.mock import Mock, MagicMock

import pytest

from src.domain.message import MeshtasticMessage
from src.service.message_factory import MessageFactory


class TestMessageFactory:
    """Тесты для класса MessageFactory."""

    def test_create_message_minimal(self, mock_node_cache_service):
        """Тест создания сообщения с минимальными данными."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {"type": "text"}
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert isinstance(result, MeshtasticMessage)
        assert result.topic == topic
        assert result.raw_payload == raw_payload
        assert result.message_type == "text"

    def test_create_message_full(self, mock_node_cache_service, sample_text_message_payload):
        """Тест создания сообщения с полными данными."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        topic = "msh/2/json/!12345678"
        result = factory.create_message(sample_text_message_payload, topic)
        
        assert isinstance(result, MeshtasticMessage)
        assert result.topic == topic
        assert result.message_id == "123456"
        assert result.from_node == "!12345678"
        assert result.to_node == "!87654321"
        assert result.text == "Hello World"
        assert result.timestamp == 1234567890
        assert result.rssi == -80
        assert result.snr == 10.5
        assert result.hops_away == 2

    @pytest.mark.parametrize(
        "node_id_input,expected",
        [
            (0x12345678, "!12345678"),
            ("!12345678", "!12345678"),
            ("12345678", "!12345678"),
            ("0x12345678", "!12345678"),
            (None, None),
        ],
    )
    def test_normalize_node_id(self, mock_node_cache_service, node_id_input, expected):
        """Тест нормализации node_id из различных форматов."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {"type": "text", "from": node_id_input}
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.from_node == expected

    def test_get_names_from_cache(self, mock_node_cache_service):
        """Тест получения имен нод из кэша."""
        mock_node_cache_service.get_node_name.return_value = "Cached Name"
        mock_node_cache_service.get_node_shortname.return_value = "CN"
        
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "from": "!12345678",
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.from_node_name == "Cached Name"
        assert result.from_node_short == "CN"
        mock_node_cache_service.get_node_name.assert_called_with("!12345678")
        mock_node_cache_service.get_node_shortname.assert_called_with("!12345678")

    def test_get_names_when_cache_unavailable(self):
        """Тест получения имен когда кэш недоступен (None)."""
        factory = MessageFactory(node_cache_service=None)
        
        raw_payload = {
            "type": "text",
            "from": "!12345678",
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.from_node_name is None
        assert result.from_node_short is None

    def test_get_names_when_not_in_cache(self, mock_node_cache_service):
        """Тест получения имен когда они отсутствуют в кэше."""
        mock_node_cache_service.get_node_name.return_value = None
        mock_node_cache_service.get_node_shortname.return_value = None
        
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "from": "!12345678",
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.from_node_name is None
        assert result.from_node_short is None

    def test_get_sender_node_names_from_cache(self, mock_node_cache_service):
        """Тест получения имен ретранслятора из кэша."""
        mock_node_cache_service.get_node_name.return_value = "Relay Node"
        mock_node_cache_service.get_node_shortname.return_value = "RN"
        
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "from": "!12345678",
            "sender": "!87654321",
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.sender_node_name == "Relay Node"
        assert result.sender_node_short == "RN"

    def test_get_recipient_names_from_cache(self, mock_node_cache_service):
        """Тест получения имен получателя из кэша."""
        mock_node_cache_service.get_node_name.return_value = "Target Node"
        mock_node_cache_service.get_node_shortname.return_value = "TGT"
        
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "from": "!12345678",
            "to": "!11111111",
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.to_node_name == "Target Node"
        assert result.to_node_short == "TGT"

    def test_calculate_hops_away_from_field(self, mock_node_cache_service):
        """Тест вычисления hops_away из поля hops_away."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "hops_away": 3,
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.hops_away == 3

    def test_calculate_hops_away_from_hop_start_limit(self, mock_node_cache_service):
        """Тест вычисления hops_away из hop_start и hop_limit."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "hop_start": 5,
            "hop_limit": 2,
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.hops_away == 3  # 5 - 2 = 3

    def test_calculate_hops_away_none_when_negative(self, mock_node_cache_service):
        """Тест обработки отрицательного hops_away (hop_start < hop_limit)."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "hop_start": 2,
            "hop_limit": 5,
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.hops_away is None

    def test_calculate_hops_away_none_when_missing(self, mock_node_cache_service):
        """Тест обработки отсутствующих полей для hops_away."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.hops_away is None

    @pytest.mark.parametrize(
        "to_node_value,expected",
        [
            (4294967295, "Всем"),
            ("!ffffffff", "Всем"),
            ("!FFFFFFFF", "Всем"),
            ("!12345678", "!12345678"),
            (0x12345678, "!12345678"),
        ],
    )
    def test_special_value_vsem(self, mock_node_cache_service, to_node_value, expected):
        """Тест обработки специального значения 'Всем' для to_node."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "to": to_node_value,
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.to_node == expected

    @pytest.mark.parametrize(
        "rssi_input,expected",
        [
            (-80, -80),
            ("-80", -80),
            (None, None),
            (0, 0),
        ],
    )
    def test_rssi_conversion(self, mock_node_cache_service, rssi_input, expected):
        """Тест конвертации RSSI в int."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "rssi": rssi_input,
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.rssi == expected

    def test_rssi_invalid_value(self, mock_node_cache_service):
        """Тест обработки невалидного значения RSSI."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "rssi": "invalid",
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.rssi is None

    @pytest.mark.parametrize(
        "snr_input,expected",
        [
            (10.5, 10.5),
            ("10.5", 10.5),
            (None, None),
            (0.0, 0.0),
            (-5.0, -5.0),
        ],
    )
    def test_snr_conversion(self, mock_node_cache_service, snr_input, expected):
        """Тест конвертации SNR в float."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "snr": snr_input,
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.snr == expected

    def test_snr_invalid_value(self, mock_node_cache_service):
        """Тест обработки невалидного значения SNR."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "snr": "invalid",
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.snr is None

    def test_extract_text_from_payload_text(self, mock_node_cache_service):
        """Тест извлечения текста из payload.text."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "payload": {"text": "Hello from payload"},
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.text == "Hello from payload"

    def test_extract_text_from_root(self, mock_node_cache_service):
        """Тест извлечения текста из корня payload."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "text": "Hello from root",
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.text == "Hello from root"

    def test_extract_text_missing(self, mock_node_cache_service):
        """Тест обработки отсутствующего текста."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.text is None

    def test_create_nodeinfo_message(self, mock_node_cache_service, sample_nodeinfo_payload):
        """Тест создания nodeinfo сообщения."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        topic = "msh/2/json/!12345678"
        result = factory.create_message(sample_nodeinfo_payload, topic)
        
        assert isinstance(result, MeshtasticMessage)
        assert result.message_type == "nodeinfo"
        assert result.from_node == "!12345678"

    def test_create_position_message(self, mock_node_cache_service, sample_position_payload):
        """Тест создания position сообщения."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        topic = "msh/2/json/!12345678"
        result = factory.create_message(sample_position_payload, topic)
        
        assert isinstance(result, MeshtasticMessage)
        assert result.message_type == "position"
        assert result.from_node == "!12345678"

    def test_preserve_raw_payload_bytes(self, mock_node_cache_service):
        """Тест сохранения raw_payload_bytes."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {"type": "text"}
        topic = "msh/2/json/!12345678"
        payload_bytes = b"test_bytes"
        
        result = factory.create_message(raw_payload, topic, raw_payload_bytes=payload_bytes)
        
        assert result.raw_payload_bytes == payload_bytes

    def test_timestamp_from_rx_time(self, mock_node_cache_service):
        """Тест использования rx_time как timestamp."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "rx_time": 1234567890,
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.timestamp == 1234567890

    def test_timestamp_from_timestamp_field(self, mock_node_cache_service):
        """Тест использования поля timestamp."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "timestamp": 9876543210,
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.timestamp == 9876543210

    def test_timestamp_rx_time_priority(self, mock_node_cache_service):
        """Тест приоритета rx_time над timestamp."""
        factory = MessageFactory(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "rx_time": 1234567890,
            "timestamp": 9876543210,
        }
        topic = "msh/2/json/!12345678"
        
        result = factory.create_message(raw_payload, topic)
        
        assert result.timestamp == 1234567890  # rx_time имеет приоритет


