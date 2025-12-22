"""
Сервис для группировки сообщений по message_id.

Группирует сообщения, полученные разными нодами, в одно сообщение Telegram
с возможностью редактирования для добавления новых нод-получателей.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field

from src.domain.message import MeshtasticMessage


logger = logging.getLogger(__name__)


@dataclass
class ReceivedByNode:
    """Информация о ноде, которая получила сообщение."""

    node_id: str
    node_name: Optional[str] = None
    node_short: Optional[str] = None
    received_at: datetime = field(default_factory=datetime.utcnow)
    rssi: Optional[int] = None
    snr: Optional[float] = None
    hops_away: Optional[int] = None
    sender_node: Optional[str] = None
    sender_node_name: Optional[str] = None
    sender_node_short: Optional[str] = None
    sender_rssi: Optional[int] = None  # RSSI от sender_node
    sender_snr: Optional[float] = None  # SNR от sender_node

    def __hash__(self) -> int:
        """Хэш для использования в множествах."""
        return hash(self.node_id)

    def __eq__(self, other: object) -> bool:
        """Сравнение по node_id."""
        if not isinstance(other, ReceivedByNode):
            return False
        return self.node_id == other.node_id


@dataclass
class MessageGroup:
    """Группа сообщений с одинаковым message_id."""

    message_id: str
    telegram_message_id: Optional[int] = None
    original_message: Optional[MeshtasticMessage] = None
    received_by: List[ReceivedByNode] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def add_node(self, node: ReceivedByNode) -> bool:
        """
        Добавляет ноду в список получателей, если её там ещё нет.

        Args:
            node: Информация о ноде-получателе

        Returns:
            True, если нода была добавлена (не была в списке), False если уже была
        """
        if node not in self.received_by:
            self.received_by.append(node)
            self.last_updated = datetime.utcnow()
            return True
        return False

    def get_unique_nodes(self) -> List[ReceivedByNode]:
        """Возвращает список уникальных нод-получателей."""
        seen = set()
        unique = []
        for node in self.received_by:
            if node.node_id not in seen:
                seen.add(node.node_id)
                unique.append(node)
        return unique


class MessageGroupingService:
    """
    Сервис для управления группировкой сообщений по message_id.

    Хранит состояние сообщений и позволяет добавлять новые ноды-получатели
    к существующим сообщениям.
    """

    def __init__(self, grouping_timeout_seconds: int = 30):
        """
        Создает сервис группировки сообщений.

        Args:
            grouping_timeout_seconds: Таймаут в секундах, после которого
                прекращается группировка для сообщения (по умолчанию 30)
        """
        self._groups: Dict[str, MessageGroup] = {}
        self.grouping_timeout = timedelta(seconds=grouping_timeout_seconds)

    def get_or_create_group(
        self, message_id: str, telegram_message_id: Optional[int] = None
    ) -> MessageGroup:
        """
        Получает существующую группу или создает новую.

        Args:
            message_id: ID сообщения Meshtastic
            telegram_message_id: ID сообщения в Telegram (для новых групп)

        Returns:
            Группа сообщений
        """
        if message_id not in self._groups:
            self._groups[message_id] = MessageGroup(
                message_id=message_id, telegram_message_id=telegram_message_id
            )
            logger.debug(f"Создана новая группа сообщений: message_id={message_id}")
        elif telegram_message_id is not None:
            # Обновляем telegram_message_id, если он был передан
            self._groups[message_id].telegram_message_id = telegram_message_id

        return self._groups[message_id]

    def get_group(self, message_id: str) -> Optional[MessageGroup]:
        """
        Получает группу по message_id.

        Args:
            message_id: ID сообщения Meshtastic

        Returns:
            Группа сообщений или None, если не найдена
        """
        return self._groups.get(message_id)

    def add_received_node(
        self,
        message_id: str,
        message: MeshtasticMessage,
        receiver_node_id: Optional[str] = None,
        node_cache_service: Optional[Any] = None,
    ) -> bool:
        """
        Добавляет информацию о ноде-получателе в группу.

        Args:
            message_id: ID сообщения Meshtastic
            message: Объект сообщения Meshtastic
            receiver_node_id: ID ноды, которая получила сообщение (из топика MQTT)
            node_cache_service: Сервис кэша нод для получения имен (опционально)

        Returns:
            True, если нода была добавлена (не была в списке), False если уже была
        """
        group = self.get_or_create_group(message_id)
        if group.original_message is None:
            group.original_message = message

        # Используем receiver_node_id, если передан, иначе пытаемся извлечь из топика
        node_id = receiver_node_id
        if not node_id:
            # Пытаемся извлечь из топика (например, msh/2/json/!12345678)
            topic_parts = message.topic.split("/")
            if len(topic_parts) >= 4:
                potential_node_id = topic_parts[-1]
                if potential_node_id.startswith("!"):
                    node_id = potential_node_id

        if not node_id:
            logger.warning(
                f"Не удалось определить ноду-получателя для message_id={message_id}"
            )
            return False

        # Получаем информацию о ноде из кэша, если доступен
        node_name = None
        node_short = None
        if node_cache_service:
            node_name = node_cache_service.get_node_name(node_id)
            node_short = node_cache_service.get_node_shortname(node_id)

        # Получаем информацию о sender_node из кэша
        sender_node_name = None
        sender_node_short = None
        if node_cache_service and message.sender_node:
            sender_node_name = node_cache_service.get_node_name(message.sender_node)
            sender_node_short = node_cache_service.get_node_shortname(message.sender_node)
        
        received_node = ReceivedByNode(
            node_id=node_id,
            node_name=node_name,
            node_short=node_short,
            received_at=message.received_at,
            rssi=message.rssi,
            snr=message.snr,
            hops_away=message.hops_away,
            sender_node=message.sender_node,
            sender_node_name=sender_node_name or message.sender_node_name,
            sender_node_short=sender_node_short or message.sender_node_short,
            sender_rssi=message.rssi,  # RSSI от sender_node (это RSSI приема сообщения)
            sender_snr=message.snr,   # SNR от sender_node (это SNR приема сообщения)
        )

        return group.add_node(received_node)

    def is_grouping_active(self, message_id: str) -> bool:
        """
        Проверяет, активна ли группировка для сообщения (не истек ли таймаут).

        Args:
            message_id: ID сообщения Meshtastic

        Returns:
            True, если группировка активна, False если истек таймаут или группа не найдена
        """
        group = self.get_group(message_id)
        if not group:
            return False

        elapsed = datetime.utcnow() - group.last_updated
        return elapsed < self.grouping_timeout

    def cleanup_expired_groups(self) -> int:
        """
        Удаляет группы, для которых истек таймаут группировки.

        Returns:
            Количество удаленных групп
        """
        now = datetime.utcnow()
        expired_ids = [
            msg_id
            for msg_id, group in self._groups.items()
            if now - group.last_updated > self.grouping_timeout
        ]

        for msg_id in expired_ids:
            del self._groups[msg_id]

        if expired_ids:
            logger.debug(f"Удалено {len(expired_ids)} истекших групп сообщений")

        return len(expired_ids)

    def get_all_groups(self) -> Dict[str, MessageGroup]:
        """Возвращает все группы сообщений."""
        return self._groups.copy()

