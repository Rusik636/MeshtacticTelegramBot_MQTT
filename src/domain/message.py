"""
Доменная модель сообщения от Meshtastic.

Структурированное представление сообщения, полученного из MQTT.
"""

import html
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING
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

    @staticmethod
    def get_rssi_quality_emoji(rssi: Optional[int]) -> str:
        """
        Определяет эмодзи качества сигнала на основе RSSI.

        Пороги для LoRa/Meshtastic:
        - 🟢 Отличный: > -80 dBm
        - 🟡 Нормальный: -80 до -100 dBm
        - 🔴 Плохой: -100 до -120 dBm
        - ⚫ Очень плохой: < -120 dBm

        Args:
            rssi: Значение RSSI в dBm (отрицательное число)

        Returns:
            Эмодзи, соответствующий качеству RSSI
        """
        if rssi is None:
            return "⚪"  # Неизвестно

        if rssi > -80:
            return "🟢"  # Отличный
        elif rssi >= -100:
            return "🟡"  # Нормальный
        elif rssi >= -120:
            return "🔴"  # Плохой
        else:
            return "⚫"  # Очень плохой

    @staticmethod
    def get_snr_quality_emoji(snr: Optional[float]) -> str:
        """
        Определяет эмодзи качества сигнала на основе SNR.

        Пороги для LoRa/Meshtastic:
        - 🟢 Отличный: > 7 dB
        - 🟡 Нормальный: 3 до 7 dB
        - 🔴 Плохой: 0 до 3 dB
        - ⚫ Очень плохой: < 0 dB

        Args:
            snr: Значение SNR в dB (может быть отрицательным)

        Returns:
            Эмодзи, соответствующий качеству SNR
        """
        if snr is None:
            return "⚪"  # Неизвестно

        if snr > 10:
            return "🟢"  # Отличный
        elif snr >= 5:
            return "🟡"  # Хороший
        elif snr >= 0:
            return "🟠"  # Удовлетворительный
        elif snr >= -5:
            return "🔴"  # Плохой
        else:
            return "⚫"  # Очень плохой


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
