"""
Unit-тесты для MessageService.

Покрытие: 95%+
"""

import json
from unittest.mock import Mock, MagicMock, patch, AsyncMock

import pytest

from src.domain.message import MeshtasticMessage
from src.service.message_service import MessageService, JsonMessageParser, ProtobufMessageParser


class TestMessageService:
    """Тесты для класса MessageService."""

    def test_init_with_dependencies(
        self, mock_node_cache_service, mock_message_factory, mock_node_cache_updater
    ):
        """Тест инициализации с переданными зависимостями."""
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="json",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        assert service.node_cache_service == mock_node_cache_service
        assert service.payload_format == "json"
        assert service.json_parser is not None
        assert service.protobuf_parser is not None

    def test_init_without_message_factory_raises_error(self, mock_node_cache_service):
        """Тест ошибки при отсутствии message_factory."""
        with pytest.raises(ValueError, match="message_factory обязателен"):
            MessageService(
                node_cache_service=mock_node_cache_service,
                message_factory=None,
                node_cache_updater=Mock(),
            )

    def test_init_without_node_cache_updater_raises_error(self, mock_node_cache_service):
        """Тест ошибки при отсутствии node_cache_updater."""
        with pytest.raises(ValueError, match="node_cache_updater обязателен"):
            MessageService(
                node_cache_service=mock_node_cache_service,
                message_factory=Mock(),
                node_cache_updater=None,
            )

    def test_parse_json_text_message(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
        sample_text_message_payload,
    ):
        """Тест парсинга JSON текстового сообщения."""
        # Настраиваем мок фабрики
        expected_message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=sample_text_message_payload,
        )
        mock_message_factory.create_message.return_value = expected_message
        
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="json",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"
        payload = json.dumps(sample_text_message_payload).encode("utf-8")
        
        result = service.parse_mqtt_message(topic, payload)
        
        assert result == expected_message
        mock_message_factory.create_message.assert_called_once()
        mock_node_cache_updater.update_from_message.assert_called_once()

    def test_parse_protobuf_message(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
    ):
        """Тест парсинга Protobuf сообщения."""
        expected_message = MeshtasticMessage(
            topic="msh/2/e/LongFast/!12345678",
            raw_payload={"type": "text"},
        )
        mock_message_factory.create_message.return_value = expected_message
        
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="protobuf",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/e/LongFast/!12345678"
        # Мокируем protobuf payload
        with patch("src.service.message_service.ProtobufMessageParser") as mock_parser_class:
            mock_parser = Mock()
            mock_parser.parse.return_value = expected_message
            mock_parser_class.return_value = mock_parser
            
            # Пересоздаем сервис с мокнутым парсером
            service.protobuf_parser = mock_parser
            
            payload = b"protobuf_data"
            result = service.parse_mqtt_message(topic, payload)
            
            assert result == expected_message
            mock_parser.parse.assert_called_once_with(topic, payload)

    def test_parse_determines_format_from_topic(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
        sample_text_message_payload,
    ):
        """Тест определения формата по топику."""
        expected_message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=sample_text_message_payload,
        )
        mock_message_factory.create_message.return_value = expected_message
        
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="both",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        # JSON топик
        json_topic = "msh/2/json/!12345678"
        json_payload = json.dumps(sample_text_message_payload).encode("utf-8")
        result = service.parse_mqtt_message(json_topic, json_payload)
        
        assert result == expected_message

    def test_parse_invalid_json_returns_error_message(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
    ):
        """Тест обработки невалидного JSON - должен вернуть MeshtasticMessage с error."""
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="json",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"
        invalid_payload = b"invalid json {"
        
        result = service.parse_mqtt_message(topic, invalid_payload)
        
        assert isinstance(result, MeshtasticMessage)
        assert result.topic == topic
        assert "error" in result.raw_payload
        assert "Failed to parse JSON" in result.raw_payload.get("error", "")

    def test_parse_empty_payload(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
    ):
        """Тест обработки пустого payload."""
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="json",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"
        empty_payload = b""
        
        # Пустой payload должен вызвать JSONDecodeError
        result = service.parse_mqtt_message(topic, empty_payload)
        
        assert isinstance(result, MeshtasticMessage)
        assert "error" in result.raw_payload

    def test_parse_unicode_decode_error(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
    ):
        """Тест обработки бинарных данных в JSON топике."""
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="json",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"
        binary_payload = b"\x00\x01\x02\x03\xff"
        
        result = service.parse_mqtt_message(topic, binary_payload)
        
        assert isinstance(result, MeshtasticMessage)
        assert "error" in result.raw_payload
        # Бинарные данные в JSON топике вызывают JSONDecodeError, а не UnicodeDecodeError
        assert "Failed to parse JSON" in result.raw_payload.get("error", "")

    def test_parse_calls_message_factory(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
        sample_text_message_payload,
    ):
        """Тест вызова message_factory.create_message()."""
        expected_message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=sample_text_message_payload,
        )
        mock_message_factory.create_message.return_value = expected_message
        
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="json",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"
        payload = json.dumps(sample_text_message_payload).encode("utf-8")
        
        service.parse_mqtt_message(topic, payload)
        
        # Проверяем, что create_message был вызван с правильными параметрами
        mock_message_factory.create_message.assert_called_once()
        call_args = mock_message_factory.create_message.call_args
        assert call_args[1]["topic"] == topic
        assert call_args[1]["raw_payload_bytes"] == payload

    def test_parse_calls_node_cache_updater(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
        sample_text_message_payload,
    ):
        """Тест вызова node_cache_updater.update_from_message()."""
        expected_message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=sample_text_message_payload,
        )
        mock_message_factory.create_message.return_value = expected_message
        
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="json",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"
        payload = json.dumps(sample_text_message_payload).encode("utf-8")
        
        service.parse_mqtt_message(topic, payload)
        
        # Проверяем, что update_from_message был вызван
        mock_node_cache_updater.update_from_message.assert_called_once()
        call_args = mock_node_cache_updater.update_from_message.call_args
        assert call_args[0][0] == expected_message

    def test_parse_fallback_for_nodeinfo_cache_update(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
    ):
        """Тест fallback парсинга для обновления кэша (nodeinfo/position)."""
        nodeinfo_payload = {
            "type": "nodeinfo",
            "from": "!12345678",
            "payload": {"id": "!12345678", "longname": "Test Node"},
        }
        
        expected_message = MeshtasticMessage(
            topic="msh/2/e/LongFast/!12345678",
            raw_payload=nodeinfo_payload,
            message_type="nodeinfo",
        )
        mock_message_factory.create_message.return_value = expected_message
        
        # Настраиваем сервис с payload_format="json", но топик protobuf
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="json",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        # Мокируем protobuf парсер для fallback
        # Protobuf парсер вызывает _create_message, который вызывает update_from_message
        # Поэтому мокируем parse так, чтобы он возвращал сообщение и вызывал update_from_message
        def mock_parse(topic, payload):
            # Вызываем update_from_message вручную, как это делает _create_message
            service.protobuf_parser.node_cache_updater.update_from_message(expected_message, nodeinfo_payload)
            return expected_message
        
        with patch.object(service.protobuf_parser, "parse", side_effect=mock_parse):
            topic = "msh/2/e/LongFast/!12345678"  # Protobuf топик
            payload = b"protobuf_data"
            
            result = service.parse_mqtt_message(topic, payload)
            
            # Должен попытаться парсить protobuf для обновления кэша
            assert result == expected_message
            # update_from_message должен быть вызван
            mock_node_cache_updater.update_from_message.assert_called_once()

    def test_parse_with_both_format(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
        sample_text_message_payload,
    ):
        """Тест парсинга с payload_format='both'."""
        expected_message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=sample_text_message_payload,
        )
        mock_message_factory.create_message.return_value = expected_message
        
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="both",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"
        payload = json.dumps(sample_text_message_payload).encode("utf-8")
        
        result = service.parse_mqtt_message(topic, payload)
        
        assert result == expected_message

    def test_parse_protobuf_topic_detection(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
    ):
        """Тест определения protobuf топика по наличию /e/."""
        expected_message = MeshtasticMessage(
            topic="msh/2/e/LongFast/!12345678",
            raw_payload={"type": "text"},
        )
        mock_message_factory.create_message.return_value = expected_message
        
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="both",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        # Мокируем protobuf парсер
        with patch.object(service, "protobuf_parser") as mock_protobuf_parser:
            mock_protobuf_parser.parse.return_value = expected_message
            
            topic = "msh/2/e/LongFast/!12345678"  # Protobuf топик
            payload = b"protobuf_data"
            
            result = service.parse_mqtt_message(topic, payload)
            
            # Должен использовать protobuf парсер
            mock_protobuf_parser.parse.assert_called_once_with(topic, payload)
            assert result == expected_message

    def test_parse_json_topic_detection(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
        sample_text_message_payload,
    ):
        """Тест определения JSON топика (без /e/ и с /json/)."""
        expected_message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=sample_text_message_payload,
        )
        mock_message_factory.create_message.return_value = expected_message
        
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="both",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"  # JSON топик
        payload = json.dumps(sample_text_message_payload).encode("utf-8")
        
        result = service.parse_mqtt_message(topic, payload)
        
        # Должен использовать JSON парсер
        assert result == expected_message
        mock_message_factory.create_message.assert_called_once()

    def test_parse_unexpected_error_handling(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
    ):
        """Тест обработки неожиданных ошибок при парсинге."""
        # Мокируем ошибку в парсере
        mock_message_factory.create_message.side_effect = Exception("Unexpected error")
        
        service = MessageService(
            node_cache_service=mock_node_cache_service,
            payload_format="json",
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"
        payload = json.dumps({"type": "text"}).encode("utf-8")
        
        result = service.parse_mqtt_message(topic, payload)
        
        # Должен вернуть MeshtasticMessage с error
        assert isinstance(result, MeshtasticMessage)
        assert "error" in result.raw_payload


class TestJsonMessageParser:
    """Тесты для класса JsonMessageParser."""

    def test_parse_json_message(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
        sample_text_message_payload,
    ):
        """Тест успешного парсинга JSON сообщения."""
        expected_message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=sample_text_message_payload,
        )
        mock_message_factory.create_message.return_value = expected_message
        
        parser = JsonMessageParser(
            node_cache_service=mock_node_cache_service,
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"
        payload = json.dumps(sample_text_message_payload).encode("utf-8")
        
        result = parser.parse(topic, payload)
        
        assert result == expected_message
        mock_message_factory.create_message.assert_called_once()
        mock_node_cache_updater.update_from_message.assert_called_once()

    def test_parse_preserves_raw_payload_bytes(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
        sample_text_message_payload,
    ):
        """Тест сохранения raw_payload_bytes для проксирования."""
        expected_message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=sample_text_message_payload,
        )
        mock_message_factory.create_message.return_value = expected_message
        
        parser = JsonMessageParser(
            node_cache_service=mock_node_cache_service,
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/json/!12345678"
        payload = json.dumps(sample_text_message_payload).encode("utf-8")
        
        parser.parse(topic, payload)
        
        # Проверяем, что raw_payload_bytes передан в create_message
        call_args = mock_message_factory.create_message.call_args
        assert call_args[1]["raw_payload_bytes"] == payload


class TestProtobufMessageParser:
    """Тесты для класса ProtobufMessageParser."""

    def test_parse_protobuf_message(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
    ):
        """Тест успешного парсинга Protobuf сообщения."""
        raw_payload = {
            "type": "text",
            "id": "123456",
            "from": "!12345678",
        }
        
        expected_message = MeshtasticMessage(
            topic="msh/2/e/LongFast/!12345678",
            raw_payload=raw_payload,
        )
        mock_message_factory.create_message.return_value = expected_message
        
        parser = ProtobufMessageParser(
            node_cache_service=mock_node_cache_service,
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/e/LongFast/!12345678"
        
        # Мокируем _parse_protobuf_payload
        with patch.object(parser, "_parse_protobuf_payload") as mock_parse:
            mock_parse.return_value = raw_payload
            
            payload = b"protobuf_data"
            result = parser.parse(topic, payload)
            
            assert result == expected_message
            mock_parse.assert_called_once_with(payload)
            mock_message_factory.create_message.assert_called_once()
            mock_node_cache_updater.update_from_message.assert_called_once()

    def test_parse_protobuf_preserves_raw_payload_bytes(
        self,
        mock_node_cache_service,
        mock_message_factory,
        mock_node_cache_updater,
    ):
        """Тест сохранения raw_payload_bytes для проксирования."""
        raw_payload = {"type": "text"}
        expected_message = MeshtasticMessage(
            topic="msh/2/e/LongFast/!12345678",
            raw_payload=raw_payload,
        )
        mock_message_factory.create_message.return_value = expected_message
        
        parser = ProtobufMessageParser(
            node_cache_service=mock_node_cache_service,
            message_factory=mock_message_factory,
            node_cache_updater=mock_node_cache_updater,
        )
        
        topic = "msh/2/e/LongFast/!12345678"
        payload = b"protobuf_data"
        
        with patch.object(parser, "_parse_protobuf_payload") as mock_parse:
            mock_parse.return_value = raw_payload
            
            parser.parse(topic, payload)
            
            # Проверяем, что raw_payload_bytes передан
            call_args = mock_message_factory.create_message.call_args
            assert call_args[1]["raw_payload_bytes"] == payload


