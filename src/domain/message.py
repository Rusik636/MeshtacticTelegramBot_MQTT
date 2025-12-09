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
    from_node_name: Optional[str] = Field(default=None, description="Название ноды отправителя")
    from_node_short: Optional[str] = Field(default=None, description="Короткое имя ноды отправителя")
    to_node: Optional[str] = Field(default=None, description="ID получателя")
    text: Optional[str] = Field(default=None, description="Текст сообщения")
    timestamp: Optional[int] = Field(default=None, description="Unix timestamp сообщения")
    rssi: Optional[int] = Field(default=None, description="RSSI (Received Signal Strength Indicator) в dBm")
    snr: Optional[float] = Field(default=None, description="SNR (Signal-to-Noise Ratio) в dB")
    message_type: Optional[str] = Field(default=None, description="Тип сообщения (text, nodeinfo, position и т.д.)")
    
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
        
        if snr > 7:
            return "🟢"  # Отличный
        elif snr >= 3:
            return "🟡"  # Нормальный
        elif snr >= 0:
            return "🔴"  # Плохой
        else:
            return "⚫"  # Очень плохой
    
    def format_for_telegram(self) -> str:
        """
        Форматирует сообщение для отправки в Telegram.
        
        Поддерживает UTF-8 символы в названиях и тегах нод.
        Отображает качество сигнала с цветными индикаторами.
        
        Returns:
            Отформатированная строка сообщения.
        """
        parts = []
        
        # Формируем информацию об отправителе с поддержкой UTF-8
        sender_info = []
        if self.from_node_name:
            # Название ноды (может содержать UTF-8 символы)
            sender_info.append(self.from_node_name)
        elif self.from_node_short:
            # Короткое имя ноды
            sender_info.append(self.from_node_short)
        
        if self.from_node:
            # ID ноды (hex формат)
            if sender_info:
                sender_info.append(f"({self.from_node})")
            else:
                sender_info.append(self.from_node)
        
        if sender_info:
            # Объединяем информацию об отправителе
            sender_str = " ".join(sender_info)
            parts.append(f"📡 От: {sender_str}")
        
        # Текст сообщения (может содержать UTF-8 символы)
        if self.text:
            parts.append(f"💬 {self.text}")
        
        # Качество сигнала (RSSI и SNR с отдельными индикаторами)
        signal_parts = []
        if self.rssi is not None:
            rssi_emoji = self.get_rssi_quality_emoji(self.rssi)
            signal_parts.append(f"{rssi_emoji} RSSI: {self.rssi} dBm")
        
        if self.snr is not None:
            snr_emoji = self.get_snr_quality_emoji(self.snr)
            signal_parts.append(f"{snr_emoji} SNR: {self.snr:.1f} dB")
        
        if signal_parts:
            parts.append(f"📶 {' | '.join(signal_parts)}")
        
        # Временная метка в формате чч:мм дд.мм.гггг
        if self.timestamp:
            try:
                dt = datetime.fromtimestamp(self.timestamp)
                # Формат: чч:мм дд.мм.гггг (например: 22:30 09.12.2025)
                parts.append(f"🕐 {dt.strftime('%H:%M %d.%m.%Y')}")
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
            "from_node_name": self.from_node_name,
            "from_node_short": self.from_node_short,
            "to_node": self.to_node,
            "text": self.text,
            "timestamp": self.timestamp,
            "rssi": self.rssi,
            "snr": self.snr,
        }

