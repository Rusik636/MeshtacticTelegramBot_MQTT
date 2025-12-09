"""
Доменная модель сообщения от Meshtastic.

Представляет структурированное сообщение, полученное из MQTT.
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class MeshtasticMessage(BaseModel):
    """
    Модель сообщения от Meshtastic.
    
    Сообщения приходят в формате JSON через MQTT топик msh/2/json/#.
    """
    # Исходный топик MQTT
    topic: str = Field(description="MQTT топик, из которого получено сообщение")
    
    # Исходный payload (JSON)
    raw_payload: Dict[str, Any] = Field(description="Исходный JSON payload")
    
    # Время получения
    received_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Время получения сообщения"
    )
    
    # Извлеченные поля из Meshtastic JSON
    message_id: Optional[str] = Field(default=None, description="ID сообщения")
    from_node: Optional[str] = Field(default=None, description="ID отправителя")
    to_node: Optional[str] = Field(default=None, description="ID получателя")
    text: Optional[str] = Field(default=None, description="Текст сообщения")
    timestamp: Optional[int] = Field(default=None, description="Unix timestamp сообщения")
    
    def format_for_telegram(self) -> str:
        """
        Форматирует сообщение для отправки в Telegram.
        
        Returns:
            Отформатированная строка сообщения.
        """
        parts = []
        
        if self.from_node:
            parts.append(f"📡 От: {self.from_node}")
        
        if self.text:
            parts.append(f"💬 {self.text}")
        
        if self.timestamp:
            try:
                dt = datetime.fromtimestamp(self.timestamp)
                parts.append(f"🕐 {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            except (ValueError, OSError):
                pass
        
        if not parts:
            # Если не удалось извлечь структурированные данные, показываем raw
            parts.append("📨 Новое сообщение Meshtastic")
            parts.append(f"Топик: {self.topic}")
        
        return "\n".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует сообщение в словарь для сериализации."""
        return {
            "topic": self.topic,
            "raw_payload": self.raw_payload,
            "received_at": self.received_at.isoformat(),
            "message_id": self.message_id,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "text": self.text,
            "timestamp": self.timestamp,
        }

