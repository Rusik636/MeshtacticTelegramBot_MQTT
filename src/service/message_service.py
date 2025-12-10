"""
Сервис обработки сообщений.

Отвечает за парсинг и обработку сообщений от Meshtastic.
Поддерживает UTF-8 для корректной обработки названий нод, тегов и текста сообщений.
"""
import base64
import json
import logging
from typing import Dict, Any, Optional

try:
    from google.protobuf.json_format import MessageToDict  # type: ignore
    from meshtastic.protobuf import mqtt_pb2  # type: ignore
    PROTOBUF_AVAILABLE = True
except Exception:  # noqa: BLE001
    PROTOBUF_AVAILABLE = False

from src.domain.message import MeshtasticMessage


logger = logging.getLogger(__name__)


class MessageService:
    """
    Сервис для обработки сообщений от Meshtastic.
    
    Парсит payload (JSON или protobuf) из MQTT и создает доменные модели сообщений.
    """
    
    def __init__(self, node_cache_service: Optional[Any] = None, payload_format: str = "json"):
        """
        Инициализирует сервис обработки сообщений.
        
        Args:
            node_cache_service: Сервис кэша нод (опционально)
            payload_format: Формат входящих сообщений (json | protobuf | both)
        """
        self.node_cache_service = node_cache_service
        self.payload_format = payload_format.lower() if payload_format else "json"
    
    def parse_mqtt_message(self, topic: str, payload: bytes) -> MeshtasticMessage:
        """
        Парсит MQTT сообщение и создает доменную модель.
        
        Args:
            topic: MQTT топик
            payload: Данные сообщения (bytes)
            
        Returns:
            Объект MeshtasticMessage
        """
        is_protobuf_topic = "/e/" in topic and "/json/" not in topic
        should_parse_protobuf = self.payload_format in ("protobuf", "both") and is_protobuf_topic
        should_parse_json = self.payload_format in ("json", "both") and not is_protobuf_topic

        try:
            if should_parse_protobuf:
                raw_payload = self._parse_protobuf_payload(payload)
            elif should_parse_json:
                payload_str = payload.decode("utf-8", errors="replace")
                raw_payload: Dict[str, Any] = json.loads(payload_str)
            else:
                raise ValueError(
                    f"Сообщение не соответствует выбранному формату payload_format={self.payload_format}, topic={topic}"
                )

            # Извлекаем тип сообщения
            message_type = raw_payload.get("type")
            
            # Извлекаем поля из Meshtastic JSON
            # Структура Meshtastic JSON может варьироваться, поэтому используем безопасное извлечение
            message_id = raw_payload.get("id")
            from_node = raw_payload.get("from")
            to_node = raw_payload.get("to")
            hops_away = raw_payload.get("hops_away")
            timestamp = raw_payload.get("rx_time") or raw_payload.get("timestamp")
            
            # Извлекаем текст в зависимости от типа сообщения
            text = None
            if message_type == "text":
                text = raw_payload.get("payload", {}).get("text") if isinstance(raw_payload.get("payload"), dict) else None
                # Если текст не найден в payload, пробуем другие варианты
                if not text:
                    text = raw_payload.get("text")
            
            # Если from_node в hex формате, конвертируем для отображения
            # from_node - это реальный отправитель, sender - это нода-ретранслятор
            from_node_str = None
            if from_node:
                # Meshtastic использует hex формат для ID нод (например, 0x698535e0)
                if isinstance(from_node, (int, str)):
                    from_node_str = f"!{hex(int(from_node))[2:]}" if isinstance(from_node, int) else str(from_node)
                else:
                    from_node_str = str(from_node)
            
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
            elif message_type == "position":
                # Для position извлекаем координаты из payload
                payload_data = raw_payload.get("payload", {})
                if isinstance(payload_data, dict) and self.node_cache_service:
                    # Извлекаем ID ноды из from (реальный отправитель), а не sender (ретранслятор)
                    node_id = None
                    from_node_raw = raw_payload.get("from")
                    if from_node_raw:
                        # Конвертируем from в hex формат
                        if isinstance(from_node_raw, (int, str)):
                            node_id = f"!{hex(int(from_node_raw))[2:]}" if isinstance(from_node_raw, int) else str(from_node_raw)
                    
                    if node_id:
                        # Извлекаем координаты
                        # Meshtastic передает координаты как latitude_i и longitude_i
                        # Формат может быть разным: либо уже в градусах, либо в градусах * 1e7
                        latitude_i = payload_data.get("latitude_i")
                        longitude_i = payload_data.get("longitude_i")
                        altitude = payload_data.get("altitude")
                        
                        if latitude_i is not None and longitude_i is not None:
                            # Конвертируем координаты
                            # Если значения большие (> 1000), значит это формат * 1e7, иначе уже градусы
                            latitude_raw = float(latitude_i)
                            longitude_raw = float(longitude_i)
                            
                            if abs(latitude_raw) > 1000 or abs(longitude_raw) > 1000:
                                # Формат Meshtastic: градусы * 1e7
                                latitude = latitude_raw / 1e7
                                longitude = longitude_raw / 1e7
                            else:
                                # Уже в градусах
                                latitude = latitude_raw
                                longitude = longitude_raw
                            
                            logger.info(
                                f"Получены координаты ноды: {node_id} "
                                f"({latitude:.6f}, {longitude:.6f}, altitude={altitude})"
                            )
                            
                            # Обновляем координаты в кэше
                            # force_disk_update=False - сохраняем на диск только если прошло 3 дня
                            self.node_cache_service.update_node_position(
                                node_id=node_id,
                                latitude=latitude,
                                longitude=longitude,
                                altitude=altitude,
                                force_disk_update=False
                            )
                        else:
                            logger.warning(f"Получено сообщение position без координат для ноды: {node_id}")
                    else:
                        logger.warning("Получено сообщение position без ID ноды (sender/from отсутствует)")
            
            # Для всех типов сообщений (кроме nodeinfo) получаем имя отправителя из кэша
            # Используем from_node_str (реальный отправитель), а не sender (ретранслятор)
            if message_type != "nodeinfo" and self.node_cache_service and from_node_str:
                cached_name = self.node_cache_service.get_node_name(from_node_str)
                cached_short = self.node_cache_service.get_node_shortname(from_node_str)
                if cached_name:
                    from_node_name = cached_name
                if cached_short:
                    from_node_short = cached_short
            
            # Извлекаем информацию о получателе (to_node) из кэша
            to_node_name = None
            to_node_short = None
            to_node_str = None
            
            if to_node is not None:
                # Конвертируем to_node в строку
                if isinstance(to_node, (int, str)):
                    to_node_str = f"!{hex(int(to_node))[2:]}" if isinstance(to_node, int) else str(to_node)
                else:
                    to_node_str = str(to_node)
                
                # Если to_node = 4294967295 (0xFFFFFFFF), это "Всем"
                if to_node == 4294967295 or to_node_str == "!ffffffff":
                    to_node_str = "Всем"
                elif self.node_cache_service:
                    # Получаем информацию о получателе из кэша
                    to_node_name = self.node_cache_service.get_node_name(to_node_str)
                    to_node_short = self.node_cache_service.get_node_shortname(to_node_str)
            
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
            
            # Конвертируем hops_away в int, если возможно
            hops_away_int = None
            if hops_away is not None:
                try:
                    hops_away_int = int(hops_away)
                except (ValueError, TypeError):
                    hops_away_int = None
            
            message = MeshtasticMessage(
                topic=topic,
                raw_payload=raw_payload,
                message_id=str(message_id) if message_id else None,
                from_node=from_node_str,
                from_node_name=from_node_name,  # Поддерживает UTF-8
                from_node_short=from_node_short,  # Поддерживает UTF-8
                to_node=to_node_str,
                to_node_name=to_node_name,  # Поддерживает UTF-8
                to_node_short=to_node_short,  # Поддерживает UTF-8
                hops_away=hops_away_int,
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

    def _parse_protobuf_payload(self, payload: bytes) -> Dict[str, Any]:
        """
        Парсит protobuf payload Meshtastic (ServiceEnvelope) в словарь,
        максимально совместимый с текущей JSON-логикой.
        """
        if not PROTOBUF_AVAILABLE:
            raise RuntimeError(
                "Выбран payload_format=protobuf, но зависимости meshtastic/protobuf не установлены."
            )

        envelope = mqtt_pb2.ServiceEnvelope()
        envelope.ParseFromString(payload)

        envelope_dict = MessageToDict(
            envelope,
            preserving_proto_field_name=True,
            including_default_value_fields=False,
        )

        packet = envelope_dict.get("packet", {}) if isinstance(envelope_dict, dict) else {}
        decoded = packet.get("decoded", {}) if isinstance(packet, dict) else {}

        raw_payload: Dict[str, Any] = {
            "type": None,
            "id": packet.get("id"),
            "from": packet.get("from"),
            "to": packet.get("to"),
            "hops_away": packet.get("hop_limit"),
            "timestamp": packet.get("rx_time") or packet.get("timestamp"),
            "rx_time": packet.get("rx_time"),
            "rssi": packet.get("rx_rssi"),
            "snr": packet.get("rx_snr"),
            "payload": {},
        }

        portnum = decoded.get("portnum")
        if portnum:
            portnum_lower = str(portnum).lower()
            if "text" in portnum_lower:
                raw_payload["type"] = "text"
            elif "node" in portnum_lower:
                raw_payload["type"] = "nodeinfo"
            elif "position" in portnum_lower:
                raw_payload["type"] = "position"

        payload_b64 = decoded.get("payload")
        if payload_b64:
            try:
                decoded_bytes = base64.b64decode(payload_b64)
                if raw_payload["type"] == "text":
                    text = decoded_bytes.decode("utf-8", errors="replace")
                    raw_payload["payload"] = {"text": text}
                else:
                    raw_payload["payload"] = {"raw_base64": payload_b64}
            except Exception:
                raw_payload["payload"] = {"raw_base64": payload_b64}

        return raw_payload

