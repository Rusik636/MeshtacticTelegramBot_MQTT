"""
Сервис обработки сообщений.

Отвечает за парсинг и обработку сообщений от Meshtastic.
Поддерживает UTF-8 для корректной обработки названий нод, тегов и текста сообщений.
"""
import json
import logging
from typing import Dict, Any, Optional

from src.domain.message import MeshtasticMessage


logger = logging.getLogger(__name__)


class MessageService:
    """
    Сервис для обработки сообщений от Meshtastic.
    
    Парсит JSON payload из MQTT и создает доменные модели сообщений.
    """
    
    def __init__(self, node_cache_service: Optional[Any] = None):
        """
        Инициализирует сервис обработки сообщений.
        
        Args:
            node_cache_service: Сервис кэша нод (опционально)
        """
        self.node_cache_service = node_cache_service
    
    def parse_mqtt_message(self, topic: str, payload: bytes) -> MeshtasticMessage:
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
            
            # Извлекаем тип сообщения
            message_type = raw_payload.get("type")
            
            # Извлекаем поля из Meshtastic JSON
            # Структура Meshtastic JSON может варьироваться, поэтому используем безопасное извлечение
            message_id = raw_payload.get("id")
            from_node = raw_payload.get("from")
            to_node = raw_payload.get("to")
            timestamp = raw_payload.get("rx_time") or raw_payload.get("timestamp")
            
            # Извлекаем текст в зависимости от типа сообщения
            text = None
            if message_type == "text":
                text = raw_payload.get("payload", {}).get("text") if isinstance(raw_payload.get("payload"), dict) else None
                # Если текст не найден в payload, пробуем другие варианты
                if not text:
                    text = raw_payload.get("text")
            
            # Извлекаем информацию о ноде отправителе (название, тег) с поддержкой UTF-8
            from_node_name = None
            from_node_short = None
            
            # Обрабатываем разные типы сообщений
            if message_type == "nodeinfo":
                # Для nodeinfo извлекаем информацию из payload
                payload_data = raw_payload.get("payload", {})
                if isinstance(payload_data, dict):
                    from_node_name = payload_data.get("longname")
                    from_node_short = payload_data.get("shortname")
                    node_id_from_payload = payload_data.get("id")
                    
                    # Обновляем кэш нод, если доступен сервис
                    if self.node_cache_service and node_id_from_payload:
                        self.node_cache_service.update_node_info(
                            node_id=node_id_from_payload,
                            longname=from_node_name,
                            shortname=from_node_short,
                            force=False  # Обновляем только если прошло 3 дня
                        )
            else:
                # Для других типов сообщений пробуем стандартные поля
                if "sender" in raw_payload:
                    sender = raw_payload["sender"]
                    if isinstance(sender, dict):
                        from_node_name = sender.get("long_name") or sender.get("name")
                        from_node_short = sender.get("short_name")
                    elif isinstance(sender, str):
                        from_node_name = sender
                
                # Альтернативные поля
                if not from_node_name:
                    from_node_name = raw_payload.get("sender_long") or raw_payload.get("from_name")
                if not from_node_short:
                    from_node_short = raw_payload.get("sender_short")
                
            # Если from_node в hex формате, конвертируем для отображения
            from_node_str = None
            if from_node:
                # Meshtastic использует hex формат для ID нод (например, 0x698535e0)
                if isinstance(from_node, (int, str)):
                    from_node_str = f"!{hex(int(from_node))[2:]}" if isinstance(from_node, int) else str(from_node)
                else:
                    from_node_str = str(from_node)
            
            # Если информация не найдена в сообщении, пробуем получить из кэша
            if message_type != "nodeinfo" and self.node_cache_service and from_node_str:
                cached_name = self.node_cache_service.get_node_name(from_node_str)
                cached_short = self.node_cache_service.get_node_shortname(from_node_str)
                if cached_name and not from_node_name:
                    from_node_name = cached_name
                if cached_short and not from_node_short:
                    from_node_short = cached_short
            
            # Извлекаем информацию о качестве сигнала (RSSI и SNR)
            rssi = raw_payload.get("rssi")
            snr = raw_payload.get("snr")
            
            # Конвертируем RSSI в int, если возможно
            if rssi is not None:
                try:
                    rssi = int(rssi)
                except (ValueError, TypeError):
                    rssi = None
            
            # Конвертируем SNR в float, если возможно
            if snr is not None:
                try:
                    snr = float(snr)
                except (ValueError, TypeError):
                    snr = None
            
            message = MeshtasticMessage(
                topic=topic,
                raw_payload=raw_payload,
                message_id=str(message_id) if message_id else None,
                from_node=from_node_str,
                from_node_name=from_node_name,  # Поддерживает UTF-8
                from_node_short=from_node_short,  # Поддерживает UTF-8
                to_node=str(to_node) if to_node else None,
                text=text,  # Поддерживает UTF-8
                timestamp=timestamp,
                rssi=rssi,
                snr=snr,
                message_type=message_type,
            )
            
            logger.debug(
                f"Распарсено Meshtastic сообщение: topic={topic}, "
                f"message_id={message_id}, from_node={from_node_str}, "
                f"from_node_name={from_node_name}"
            )
            
            return message
        except json.JSONDecodeError as e:
            logger.error(
                f"Ошибка парсинга JSON из MQTT сообщения: topic={topic}, error={e}",
                exc_info=True
            )
            # Возвращаем сообщение с минимальной информацией
            # Используем errors="ignore" для безопасного декодирования UTF-8
            try:
                raw_str = payload.decode("utf-8", errors="replace")
            except Exception:
                raw_str = f"<binary data, {len(payload)} bytes>"
            return MeshtasticMessage(
                topic=topic,
                raw_payload={"error": "Failed to parse JSON", "raw": raw_str},
            )
        except UnicodeDecodeError as e:
            # Если payload не является UTF-8 (например, protobuf бинарные данные)
            # Логируем и возвращаем сообщение об ошибке
            logger.warning(
                f"Невозможно декодировать payload как UTF-8 (возможно, protobuf): topic={topic}, error={e}"
            )
            # Возвращаем сообщение с информацией об ошибке
            return MeshtasticMessage(
                topic=topic,
                raw_payload={"error": "Binary payload (protobuf) - use JSON topic instead"},
            )
        except Exception as e:
            logger.error(
                f"Неожиданная ошибка при парсинге MQTT сообщения: topic={topic}, error={e}",
                exc_info=True
            )
            # Пытаемся декодировать с игнорированием ошибок для логирования
            try:
                raw_str = payload.decode("utf-8", errors="ignore")
            except Exception:
                raw_str = f"<binary data, {len(payload)} bytes>"
            return MeshtasticMessage(
                topic=topic,
                raw_payload={"error": str(e), "raw": raw_str},
            )

