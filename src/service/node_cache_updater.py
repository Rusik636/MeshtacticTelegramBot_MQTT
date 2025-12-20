"""
Сервис для обновления кэша нод из сообщений Meshtastic.

Отвечает за извлечение информации о нодах из сообщений и обновление кэша.
"""

import logging
from typing import Optional, Any, Dict

from src.domain.message import MeshtasticMessage
from src.service.message_service import _normalize_node_id

logger = logging.getLogger(__name__)


class NodeCacheUpdater:
    """
    Обновляет кэш нод на основе сообщений Meshtastic.
    
    Извлекает информацию о нодах из nodeinfo и position сообщений
    и обновляет кэш через NodeCacheService.
    """

    def __init__(self, node_cache_service: Optional[Any] = None):
        """
        Создает обновлятор кэша нод.

        Args:
            node_cache_service: Сервис кэша нод для обновления
        """
        self.node_cache_service = node_cache_service

    def update_from_message(
        self, message: MeshtasticMessage, raw_payload: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Обновляет кэш нод на основе сообщения Meshtastic.

        Args:
            message: Сообщение Meshtastic
            raw_payload: Распарсенные данные сообщения (если нужны для извлечения nodeinfo)
        """
        if not self.node_cache_service:
            return

        raw_payload = raw_payload or message.raw_payload
        message_type = message.message_type or raw_payload.get("type")

        if message_type == "nodeinfo":
            self._update_from_nodeinfo(message, raw_payload)
        elif message_type == "position":
            self._update_from_position(message, raw_payload)

    def _update_from_nodeinfo(
        self, message: MeshtasticMessage, raw_payload: Dict[str, Any]
    ) -> None:
        """Обновляет кэш из nodeinfo сообщения."""
        payload_data = raw_payload.get("payload", {})
        if not isinstance(payload_data, dict):
            return

        # Логируем полную структуру raw_payload для контекста
        try:
            import json
            raw_payload_json = json.dumps(raw_payload, ensure_ascii=False, indent=2, default=str)
            logger.info(
                f"📋 Полная структура raw_payload для nodeinfo:\n"
                f"{'=' * 80}\n"
                f"{raw_payload_json}\n"
                f"{'=' * 80}"
            )
        except Exception as e:
            logger.warning(f"Не удалось сериализовать raw_payload в JSON: {e}")

        # Пробуем разные варианты имен полей (для JSON и Protobuf)
        # Protobuf использует snake_case (long_name, short_name)
        # JSON может использовать camelCase или snake_case
        from_node_name = (
            payload_data.get("longname")
            or payload_data.get("long_name")
            or payload_data.get("longName")
        )
        from_node_short = (
            payload_data.get("shortname")
            or payload_data.get("short_name")
            or payload_data.get("shortName")
        )
        node_id_from_payload = (
            payload_data.get("id")
            or payload_data.get("user_id")
            or payload_data.get("userId")
        )

        # Если id не найден в payload, пробуем извлечь из from_node
        if not node_id_from_payload:
            node_id_from_payload = message.from_node
            logger.debug(
                f"node_id не найден в payload nodeinfo, используем from_node: {node_id_from_payload}"
            )

        # Нормализуем node_id перед обновлением кэша
        if node_id_from_payload:
            node_id_normalized = _normalize_node_id(node_id_from_payload)
            if node_id_normalized:
                self.node_cache_service.update_node_info(
                    node_id=node_id_normalized,
                    longname=from_node_name,
                    shortname=from_node_short,
                    force=False,
                )
                logger.info(
                    f"Обновлен кэш ноды из nodeinfo: node_id={node_id_normalized}, "
                    f"longname={from_node_name}, shortname={from_node_short}"
                )
            else:
                logger.warning(
                    f"Не удалось нормализовать node_id из nodeinfo: {node_id_from_payload} "
                    f"(тип: {type(node_id_from_payload)})"
                )
        else:
            logger.warning(
                f"node_id не найден в nodeinfo сообщении. payload_data keys: {list(payload_data.keys())}, "
                f"from_node: {message.from_node}"
            )

    def _update_from_position(
        self, message: MeshtasticMessage, raw_payload: Dict[str, Any]
    ) -> None:
        """Обновляет кэш из position сообщения."""
        payload_data = raw_payload.get("payload", {})
        if not isinstance(payload_data, dict):
            return

        node_id = message.from_node
        if not node_id:
            logger.warning(
                "Получено сообщение position без ID ноды (sender/from отсутствует)"
            )
            return

        latitude_i = payload_data.get("latitude_i")
        longitude_i = payload_data.get("longitude_i")
        altitude = payload_data.get("altitude")

        if latitude_i is not None and longitude_i is not None:
            latitude_raw = float(latitude_i)
            longitude_raw = float(longitude_i)
            if abs(latitude_raw) > 1000 or abs(longitude_raw) > 1000:
                latitude = latitude_raw / 1e7
                longitude = longitude_raw / 1e7
            else:
                latitude = latitude_raw
                longitude = longitude_raw

            logger.info(
                f"Получены координаты ноды: {node_id} "
                f"({latitude:.6f}, {longitude:.6f}, altitude={altitude})"
            )
            self.node_cache_service.update_node_position(
                node_id=node_id,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                force_disk_update=False,
            )
        else:
            logger.warning(
                f"Получено сообщение position без координат для ноды: {node_id}"
            )

