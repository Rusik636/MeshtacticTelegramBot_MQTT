"""
Unit-тесты для доменной модели MeshtasticMessage.

Покрытие: 100%
"""

from datetime import datetime
from typing import Dict, Any

import pytest
from pydantic import ValidationError

from src.domain.message import MeshtasticMessage


class TestMeshtasticMessage:
    """Тесты для класса MeshtasticMessage."""

    def test_create_minimal_message(self):
        """Тест создания сообщения с минимальными данными (только topic и raw_payload)."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
        )
        
        assert message.topic == "msh/2/json/!12345678"
        assert message.raw_payload == {"type": "text"}
        assert message.message_id is None
        assert message.from_node is None
        assert message.text is None
        assert isinstance(message.received_at, datetime)

    def test_create_full_message(self, sample_text_message_payload: Dict[str, Any]):
        """Тест создания сообщения со всеми полями."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=sample_text_message_payload,
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
        
        assert message.topic == "msh/2/json/!12345678"
        assert message.message_id == "123456"
        assert message.from_node == "!12345678"
        assert message.from_node_name == "Test Node"
        assert message.from_node_short == "TN"
        assert message.sender_node == "!87654321"
        assert message.sender_node_name == "Relay Node"
        assert message.sender_node_short == "RN"
        assert message.to_node == "!11111111"
        assert message.to_node_name == "Target Node"
        assert message.to_node_short == "TGT"
        assert message.hops_away == 2
        assert message.text == "Hello World"
        assert message.timestamp == 1234567890
        assert message.rssi == -80
        assert message.snr == 10.5
        assert message.message_type == "text"

    def test_create_message_without_topic_raises_error(self):
        """Тест валидации обязательного поля topic."""
        with pytest.raises(ValidationError) as exc_info:
            MeshtasticMessage(raw_payload={})
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("topic",) for error in errors)

    def test_create_message_with_none_values(self):
        """Тест создания сообщения с None значениями для опциональных полей."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
            message_id=None,
            from_node=None,
            text=None,
            timestamp=None,
            rssi=None,
            snr=None,
        )
        
        assert message.message_id is None
        assert message.from_node is None
        assert message.text is None
        assert message.timestamp is None
        assert message.rssi is None
        assert message.snr is None

    def test_to_dict_minimal(self):
        """Тест сериализации сообщения с минимальными данными."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={"type": "text"},
        )
        
        result = message.to_dict()
        
        assert result["topic"] == "msh/2/json/!12345678"
        assert result["raw_payload"] == {"type": "text"}
        assert result["message_id"] is None
        assert "received_at" in result
        assert isinstance(result["received_at"], str)  # ISO формат

    def test_to_dict_full(self, sample_text_message_payload: Dict[str, Any]):
        """Тест сериализации сообщения со всеми полями."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=sample_text_message_payload,
            message_id="123456",
            from_node="!12345678",
            from_node_name="Test Node",
            from_node_short="TN",
            text="Hello World",
            timestamp=1234567890,
            rssi=-80,
            snr=10.5,
        )
        
        result = message.to_dict()
        
        assert result["topic"] == "msh/2/json/!12345678"
        assert result["message_id"] == "123456"
        assert result["from_node"] == "!12345678"
        assert result["from_node_name"] == "Test Node"
        assert result["from_node_short"] == "TN"
        assert result["text"] == "Hello World"
        assert result["timestamp"] == 1234567890
        assert result["rssi"] == -80
        assert result["snr"] == 10.5
        assert "received_at" in result
        # Проверяем, что received_at в ISO формате
        datetime.fromisoformat(result["received_at"])

    def test_to_dict_datetime_format(self):
        """Тест формата datetime в to_dict() - должен быть ISO формат."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
        )
        
        result = message.to_dict()
        
        # Проверяем, что received_at можно распарсить как ISO формат
        parsed_dt = datetime.fromisoformat(result["received_at"])
        assert isinstance(parsed_dt, datetime)

    def test_to_dict_with_raw_payload_bytes(self):
        """Тест сериализации с raw_payload_bytes."""
        payload_bytes = b"test payload"
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
            raw_payload_bytes=payload_bytes,
        )
        
        result = message.to_dict()
        
        # raw_payload_bytes не должен быть в to_dict (только для проксирования)
        assert "raw_payload_bytes" not in result

    @pytest.mark.parametrize(
        "rssi_value,expected_type",
        [
            (-80, int),
            (None, type(None)),
            (0, int),
            (-120, int),
        ],
    )
    def test_rssi_type_handling(self, rssi_value, expected_type):
        """Тест обработки различных типов данных для RSSI."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
            rssi=rssi_value,
        )
        
        assert isinstance(message.rssi, expected_type)

    @pytest.mark.parametrize(
        "snr_value,expected_type",
        [
            (10.5, float),
            (None, type(None)),
            (0.0, float),
            (-5.0, float),
        ],
    )
    def test_snr_type_handling(self, snr_value, expected_type):
        """Тест обработки различных типов данных для SNR."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
            snr=snr_value,
        )
        
        assert isinstance(message.snr, expected_type)

    @pytest.mark.parametrize(
        "timestamp_value,expected_type",
        [
            (1234567890, int),
            (None, type(None)),
            (0, int),
        ],
    )
    def test_timestamp_type_handling(self, timestamp_value, expected_type):
        """Тест обработки различных типов данных для timestamp."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
            timestamp=timestamp_value,
        )
        
        assert isinstance(message.timestamp, expected_type)

    def test_received_at_default_factory(self):
        """Тест автоматического создания received_at при создании сообщения."""
        before = datetime.utcnow()
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
        )
        after = datetime.utcnow()
        
        assert before <= message.received_at <= after

    def test_message_with_special_characters_in_text(self):
        """Тест обработки специальных символов в тексте сообщения."""
        special_text = "Test <script>alert('XSS')</script> & 'quotes'"
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
            text=special_text,
        )
        
        assert message.text == special_text
        # Проверяем, что специальные символы сохраняются в модели
        # (экранирование будет в форматтере)

    def test_message_with_unicode_characters(self):
        """Тест обработки Unicode символов в именах нод."""
        unicode_name = "Тестовая нода 🚀"
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
            from_node_name=unicode_name,
        )
        
        assert message.from_node_name == unicode_name

    def test_message_with_empty_strings(self):
        """Тест обработки пустых строк."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
            from_node="",
            text="",
        )
        
        assert message.from_node == ""
        assert message.text == ""

    def test_message_with_very_long_text(self):
        """Тест обработки очень длинного текста сообщения."""
        long_text = "A" * 10000
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
            text=long_text,
        )
        
        assert len(message.text) == 10000
        assert message.text == long_text

    def test_message_with_all_none_optional_fields(self):
        """Тест создания сообщения со всеми опциональными полями = None."""
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload={},
            message_id=None,
            from_node=None,
            from_node_name=None,
            from_node_short=None,
            sender_node=None,
            sender_node_name=None,
            sender_node_short=None,
            to_node=None,
            to_node_name=None,
            to_node_short=None,
            hops_away=None,
            text=None,
            timestamp=None,
            rssi=None,
            snr=None,
            message_type=None,
            raw_payload_bytes=None,
        )
        
        # Проверяем, что все поля установлены в None
        assert message.message_id is None
        assert message.from_node is None
        assert message.text is None
        assert message.timestamp is None
        assert message.rssi is None
        assert message.snr is None


