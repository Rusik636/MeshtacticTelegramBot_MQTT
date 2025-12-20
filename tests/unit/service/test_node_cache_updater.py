"""
Unit-тесты для NodeCacheUpdater.

Покрытие: 90%+
"""

from unittest.mock import Mock, MagicMock

import pytest

from src.domain.message import MeshtasticMessage
from src.service.node_cache_updater import NodeCacheUpdater


class TestNodeCacheUpdater:
    """Тесты для класса NodeCacheUpdater."""

    def test_update_from_nodeinfo_success(self, mock_node_cache_service):
        """Тест успешного обновления из nodeinfo сообщения."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "nodeinfo",
            "from": "!12345678",
            "payload": {
                "id": "!12345678",
                "longname": "Test Node",
                "shortname": "TN",
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="nodeinfo",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        mock_node_cache_service.update_node_info.assert_called_once_with(
            node_id="!12345678",
            longname="Test Node",
            shortname="TN",
            force=False,
        )

    def test_update_from_nodeinfo_snake_case_fields(self, mock_node_cache_service):
        """Тест обработки различных форматов полей (snake_case)."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "nodeinfo",
            "from": "!12345678",
            "payload": {
                "id": "!12345678",
                "long_name": "Test Node",  # snake_case
                "short_name": "TN",  # snake_case
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="nodeinfo",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        mock_node_cache_service.update_node_info.assert_called_once_with(
            node_id="!12345678",
            longname="Test Node",
            shortname="TN",
            force=False,
        )

    def test_update_from_nodeinfo_camel_case_fields(self, mock_node_cache_service):
        """Тест обработки camelCase полей."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "nodeinfo",
            "from": "!12345678",
            "payload": {
                "id": "!12345678",
                "longName": "Test Node",  # camelCase
                "shortName": "TN",  # camelCase
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="nodeinfo",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        mock_node_cache_service.update_node_info.assert_called_once()
        call_kwargs = mock_node_cache_service.update_node_info.call_args[1]
        assert call_kwargs["longname"] == "Test Node"
        assert call_kwargs["shortname"] == "TN"

    def test_update_from_nodeinfo_extract_id_from_payload(self, mock_node_cache_service):
        """Тест извлечения node_id из payload.id."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "nodeinfo",
            "from": "!12345678",
            "payload": {
                "id": "!87654321",  # Другой ID в payload
                "longname": "Test Node",
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="nodeinfo",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        # Должен использовать id из payload, а не from_node
        mock_node_cache_service.update_node_info.assert_called_once()
        call_kwargs = mock_node_cache_service.update_node_info.call_args[1]
        assert call_kwargs["node_id"] == "!87654321"

    def test_update_from_nodeinfo_fallback_to_from_node(self, mock_node_cache_service):
        """Тест использования from_node если id не найден в payload."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "nodeinfo",
            "from": "!12345678",
            "payload": {
                # Нет поля id
                "longname": "Test Node",
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="nodeinfo",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        # Должен использовать from_node
        mock_node_cache_service.update_node_info.assert_called_once()
        call_kwargs = mock_node_cache_service.update_node_info.call_args[1]
        assert call_kwargs["node_id"] == "!12345678"

    def test_update_from_nodeinfo_invalid_payload(self, mock_node_cache_service):
        """Тест обработки невалидного payload (не dict)."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "nodeinfo",
            "from": "!12345678",
            "payload": "not_a_dict",  # Невалидный payload
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="nodeinfo",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        # Не должно быть вызова update_node_info
        mock_node_cache_service.update_node_info.assert_not_called()

    def test_update_from_position_success(self, mock_node_cache_service):
        """Тест успешного обновления координат из position сообщения."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "position",
            "from": "!12345678",
            "payload": {
                "latitude_i": 557580288,  # 55.7580288 * 1e7
                "longitude_i": 524550144,  # 52.4550144 * 1e7
                "altitude": 143,
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="position",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        mock_node_cache_service.update_node_position.assert_called_once()
        call_kwargs = mock_node_cache_service.update_node_position.call_args[1]
        assert abs(call_kwargs["latitude"] - 55.7580288) < 0.0001
        assert abs(call_kwargs["longitude"] - 52.4550144) < 0.0001
        assert call_kwargs["altitude"] == 143
        assert call_kwargs["force_disk_update"] is False

    def test_update_from_position_coordinates_in_degrees(self, mock_node_cache_service):
        """Тест обработки координат в градусах (без деления на 1e7)."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "position",
            "from": "!12345678",
            "payload": {
                "latitude_i": 55.7580288,  # Уже в градусах
                "longitude_i": 52.4550144,  # Уже в градусах
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="position",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        mock_node_cache_service.update_node_position.assert_called_once()
        call_kwargs = mock_node_cache_service.update_node_position.call_args[1]
        assert abs(call_kwargs["latitude"] - 55.7580288) < 0.0001
        assert abs(call_kwargs["longitude"] - 52.4550144) < 0.0001

    def test_update_from_position_missing_coordinates(self, mock_node_cache_service):
        """Тест обработки отсутствующих координат."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "position",
            "from": "!12345678",
            "payload": {
                # Нет координат
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="position",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        # Не должно быть вызова update_node_position
        mock_node_cache_service.update_node_position.assert_not_called()

    def test_update_from_position_missing_from_node(self, mock_node_cache_service):
        """Тест обработки отсутствующего from_node."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "position",
            "payload": {
                "latitude_i": 557580288,
                "longitude_i": 524550144,
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="position",
            from_node=None,  # Отсутствует
        )
        
        updater.update_from_message(message, raw_payload)
        
        # Не должно быть вызова update_node_position
        mock_node_cache_service.update_node_position.assert_not_called()

    def test_update_from_position_invalid_payload(self, mock_node_cache_service):
        """Тест обработки невалидного payload (не dict)."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "position",
            "from": "!12345678",
            "payload": "not_a_dict",
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="position",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        mock_node_cache_service.update_node_position.assert_not_called()

    def test_update_ignores_other_message_types(self, mock_node_cache_service):
        """Тест игнорирования других типов сообщений."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "text",
            "from": "!12345678",
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="text",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        # Не должно быть вызовов обновления кэша
        mock_node_cache_service.update_node_info.assert_not_called()
        mock_node_cache_service.update_node_position.assert_not_called()

    def test_update_without_cache_service(self):
        """Тест обработки отсутствующего node_cache_service (не должно быть ошибки)."""
        updater = NodeCacheUpdater(node_cache_service=None)
        
        raw_payload = {
            "type": "nodeinfo",
            "from": "!12345678",
            "payload": {
                "id": "!12345678",
                "longname": "Test Node",
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="nodeinfo",
            from_node="!12345678",
        )
        
        # Не должно быть ошибки
        updater.update_from_message(message, raw_payload)

    def test_update_nodeinfo_with_user_id_field(self, mock_node_cache_service):
        """Тест извлечения node_id из поля user_id."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "nodeinfo",
            "from": "!12345678",
            "payload": {
                "user_id": "!87654321",  # Альтернативное поле
                "longname": "Test Node",
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="nodeinfo",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        mock_node_cache_service.update_node_info.assert_called_once()
        call_kwargs = mock_node_cache_service.update_node_info.call_args[1]
        assert call_kwargs["node_id"] == "!87654321"

    def test_update_nodeinfo_with_userId_field(self, mock_node_cache_service):
        """Тест извлечения node_id из поля userId (camelCase)."""
        updater = NodeCacheUpdater(node_cache_service=mock_node_cache_service)
        
        raw_payload = {
            "type": "nodeinfo",
            "from": "!12345678",
            "payload": {
                "userId": "!87654321",  # camelCase
                "longname": "Test Node",
            },
        }
        
        message = MeshtasticMessage(
            topic="msh/2/json/!12345678",
            raw_payload=raw_payload,
            message_type="nodeinfo",
            from_node="!12345678",
        )
        
        updater.update_from_message(message, raw_payload)
        
        mock_node_cache_service.update_node_info.assert_called_once()
        call_kwargs = mock_node_cache_service.update_node_info.call_args[1]
        assert call_kwargs["node_id"] == "!87654321"


