"""
Фабрика для создания доменных моделей MeshtasticMessage.

Отвечает за создание объектов MeshtasticMessage из распарсенных данных.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from src.domain.message import MeshtasticMessage
from src.service.message_service import _normalize_node_id

logger = logging.getLogger(__name__)


class MessageFactory:
    """
    Фабрика для создания доменных моделей MeshtasticMessage.
    
    Извлекает данные из распарсенного payload и создает доменную модель
    без обновления кэша (это ответственность NodeCacheUpdater).
    """

    def __init__(self, node_cache_service: Optional[Any] = None):
        """
        Создает фабрику сообщений.

        Args:
            node_cache_service: Сервис кэша нод для получения имен нод (опционально)
        """
        self.node_cache_service = node_cache_service

    def create_message(
        self,
        raw_payload: Dict[str, Any],
        topic: str,
        raw_payload_bytes: Optional[bytes] = None,
    ) -> MeshtasticMessage:
        """
        Создает MeshtasticMessage из распарсенных данных.

        Args:
            raw_payload: Распарсенные данные сообщения
            topic: MQTT топик сообщения
            raw_payload_bytes: Исходный payload в байтах (для проксирования)

        Returns:
            Созданный объект MeshtasticMessage
        """
        message_type = raw_payload.get("type")
        message_id = raw_payload.get("id")
        from_node = raw_payload.get("from")
        sender_node = raw_payload.get("sender")
        to_node = raw_payload.get("to")
        hops_away = raw_payload.get("hops_away")
        hop_start = raw_payload.get("hop_start")
        hop_limit = raw_payload.get("hop_limit")
        timestamp = raw_payload.get("rx_time") or raw_payload.get("timestamp")

        text = None
        if message_type == "text":
            text = (
                raw_payload.get("payload", {}).get("text")
                if isinstance(raw_payload.get("payload"), dict)
                else None
            )
            if not text:
                text = raw_payload.get("text")

        # from_node - нормализуем к единому формату
        from_node_str = _normalize_node_id(from_node)

        # Получаем имена нод из кэша (если доступен)
        from_node_name = None
        from_node_short = None
        if message_type != "nodeinfo" and self.node_cache_service and from_node_str:
            cached_name = self.node_cache_service.get_node_name(from_node_str)
            cached_short = self.node_cache_service.get_node_shortname(from_node_str)
            if cached_name:
                from_node_name = cached_name
            if cached_short:
                from_node_short = cached_short

        # sender_node (ретранслятор) - нормализуем к единому формату
        sender_node_str = _normalize_node_id(sender_node)
        sender_node_name = None
        sender_node_short = None

        # Получаем имена ретранслятора из кэша
        if message_type != "nodeinfo" and self.node_cache_service and sender_node_str:
            cached_sender_name = self.node_cache_service.get_node_name(sender_node_str)
            cached_sender_short = self.node_cache_service.get_node_shortname(
                sender_node_str
            )
            if cached_sender_name:
                sender_node_name = cached_sender_name
            if cached_sender_short:
                sender_node_short = cached_sender_short

        # Получатель
        to_node_name = None
        to_node_short = None
        to_node_str = None
        if to_node is not None:
            # Нормализуем to_node, но сохраняем специальное значение "Всем"
            to_node_str = _normalize_node_id(to_node)
            # Проверяем специальное значение "Всем" (4294967295 = 0xffffffff)
            if (
                to_node == 4294967295
                or to_node_str == "!ffffffff"
                or to_node_str == "!FFFFFFFF"
            ):
                to_node_str = "Всем"
            elif to_node_str and self.node_cache_service:
                to_node_name = self.node_cache_service.get_node_name(to_node_str)
                to_node_short = self.node_cache_service.get_node_shortname(to_node_str)

        rssi = raw_payload.get("rssi")
        snr = raw_payload.get("snr")
        if rssi is not None:
            try:
                rssi = int(rssi)
            except (ValueError, TypeError):
                rssi = None
        if snr is not None:
            try:
                snr = float(snr)
            except (ValueError, TypeError):
                snr = None

        hops_away_int = None
        if hops_away is not None:
            try:
                hops_away_int = int(hops_away)
            except (ValueError, TypeError):
                hops_away_int = None
        if hops_away_int is None and hop_start is not None and hop_limit is not None:
            try:
                hs = int(hop_start)
                hl = int(hop_limit)
                diff = hs - hl
                hops_away_int = diff if diff >= 0 else None
            except (ValueError, TypeError):
                pass

        message = MeshtasticMessage(
            topic=topic,
            raw_payload=raw_payload,
            raw_payload_bytes=raw_payload_bytes,
            message_id=str(message_id) if message_id else None,
            from_node=from_node_str,
            from_node_name=from_node_name,
            from_node_short=from_node_short,
            sender_node=sender_node_str,
            sender_node_name=sender_node_name,
            sender_node_short=sender_node_short,
            to_node=to_node_str,
            to_node_name=to_node_name,
            to_node_short=to_node_short,
            hops_away=hops_away_int,
            text=text,
            timestamp=timestamp,
            rssi=rssi,
            snr=snr,
            message_type=message_type,
        )

        logger.debug(
            f"Создано Meshtastic сообщение: topic={topic}, "
            f"message_id={message_id}, from_node={from_node_str}, "
            f"from_node_name={from_node_name}"
        )
        return message

