"""
Доменная модель сообщения от Meshtastic.

Структурированное представление сообщения, полученного из MQTT.
"""

from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.service.node_cache_service import NodeCacheService


class MeshtasticMessage(BaseModel):
    """Модель сообщения от Meshtastic с распарсенными полями."""

    # Исходный топик MQTT
    topic: str = Field(description="MQTT топик, из которого получено сообщение")

    # Исходный payload (JSON) - распарсенные данные для внутренней обработки
    raw_payload: Dict[str, Any] = Field(
        description="Исходный JSON payload (распарсенный)"
    )

    # Исходный payload в сыром виде (bytes) - для проксирования без изменений
    raw_payload_bytes: Optional[bytes] = Field(
        default=None,
        description="Исходный payload в сыром виде (bytes) - как получен от ноды",
    )

    # Время получения
    received_at: datetime = Field(
        default_factory=datetime.utcnow, description="Время получения сообщения"
    )

    # Извлеченные поля из Meshtastic JSON
    message_id: Optional[str] = Field(default=None, description="ID сообщения")
    from_node: Optional[str] = Field(default=None, description="ID отправителя")
    from_node_name: Optional[str] = Field(
        default=None, description="Название ноды отправителя"
    )
    from_node_short: Optional[str] = Field(
        default=None, description="Короткое имя ноды отправителя"
    )
    sender_node: Optional[str] = Field(
        default=None, description="ID ноды, которая ретранслировала сообщение"
    )
    sender_node_name: Optional[str] = Field(
        default=None, description="Название ноды, которая ретранслировала сообщение"
    )
    sender_node_short: Optional[str] = Field(
        default=None, description="Короткое имя ноды, которая ретранслировала сообщение"
    )
    to_node: Optional[str] = Field(default=None, description="ID получателя")
    to_node_name: Optional[str] = Field(
        default=None, description="Название ноды получателя"
    )
    to_node_short: Optional[str] = Field(
        default=None, description="Короткое имя ноды получателя"
    )
    hops_away: Optional[int] = Field(
        default=None, description="Количество ретрансляций (hops)"
    )
    text: Optional[str] = Field(default=None, description="Текст сообщения")
    timestamp: Optional[int] = Field(
        default=None, description="Unix timestamp сообщения"
    )
    rssi: Optional[int] = Field(
        default=None, description="RSSI (Received Signal Strength Indicator) в dBm"
    )
    snr: Optional[float] = Field(
        default=None, description="SNR (Signal-to-Noise Ratio) в dB"
    )
    message_type: Optional[str] = Field(
        default=None, description="Тип сообщения (text, nodeinfo, position и т.д.)"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Преобразует сообщение в словарь для сериализации."""
        return {
            "topic": self.topic,
            "raw_payload": self.raw_payload,
            "received_at": self.received_at.isoformat(),
            "message_id": self.message_id,
            "from_node": self.from_node,
            "from_node_name": self.from_node_name,
            "from_node_short": self.from_node_short,
            "sender_node": self.sender_node,
            "sender_node_name": self.sender_node_name,
            "sender_node_short": self.sender_node_short,
            "to_node": self.to_node,
            "text": self.text,
            "timestamp": self.timestamp,
            "rssi": self.rssi,
            "snr": self.snr,
        }
