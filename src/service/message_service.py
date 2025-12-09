"""
Сервис обработки сообщений.

Отвечает за парсинг и обработку сообщений от Meshtastic.
"""
import json
from typing import Dict, Any
import structlog

from src.domain.message import MeshtasticMessage


logger = structlog.get_logger()


class MessageService:
    """
    Сервис для обработки сообщений от Meshtastic.
    
    Парсит JSON payload из MQTT и создает доменные модели сообщений.
    """
    
    @staticmethod
    def parse_mqtt_message(topic: str, payload: bytes) -> MeshtasticMessage:
        """
        Парсит MQTT сообщение и создает доменную модель.
        
        Args:
            topic: MQTT топик
            payload: Данные сообщения (bytes)
            
        Returns:
            Объект MeshtasticMessage
        """
        try:
            # Декодируем payload
            payload_str = payload.decode("utf-8")
            raw_payload: Dict[str, Any] = json.loads(payload_str)
            
            # Извлекаем поля из Meshtastic JSON
            # Структура Meshtastic JSON может варьироваться, поэтому используем безопасное извлечение
            message_id = raw_payload.get("id")
            from_node = raw_payload.get("from")
            to_node = raw_payload.get("to")
            text = raw_payload.get("payload", {}).get("text") if isinstance(raw_payload.get("payload"), dict) else None
            timestamp = raw_payload.get("rx_time") or raw_payload.get("timestamp")
            
            # Если текст не найден в payload, пробуем другие варианты
            if not text:
                text = raw_payload.get("text")
            
            message = MeshtasticMessage(
                topic=topic,
                raw_payload=raw_payload,
                message_id=str(message_id) if message_id else None,
                from_node=str(from_node) if from_node else None,
                to_node=str(to_node) if to_node else None,
                text=text,
                timestamp=timestamp,
            )
            
            logger.debug(
                "Распарсено Meshtastic сообщение",
                topic=topic,
                message_id=message_id,
                from_node=from_node
            )
            
            return message
        except json.JSONDecodeError as e:
            logger.error(
                "Ошибка парсинга JSON из MQTT сообщения",
                topic=topic,
                error=str(e)
            )
            # Возвращаем сообщение с минимальной информацией
            return MeshtasticMessage(
                topic=topic,
                raw_payload={"error": "Failed to parse JSON", "raw": payload.decode("utf-8", errors="ignore")},
            )
        except Exception as e:
            logger.error(
                "Неожиданная ошибка при парсинге MQTT сообщения",
                topic=topic,
                error=str(e)
            )
            return MeshtasticMessage(
                topic=topic,
                raw_payload={"error": str(e), "raw": payload.decode("utf-8", errors="ignore")},
            )

