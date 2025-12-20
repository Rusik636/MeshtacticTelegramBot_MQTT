"""
Сервис обработки сообщений.

Парсит сообщения от Meshtastic (JSON и Protobuf) и создает доменные модели.
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


def _normalize_node_id(node_id: Any) -> Optional[str]:
    """
    Нормализует node ID к единому формату "!hex" (например, "!12345678").

    Обрабатывает различные форматы:
    - int: конвертирует в hex с префиксом "!"
    - str "!12345678": возвращает как есть (в нижнем регистре)
    - str "12345678": парсит как hex и добавляет префикс "!"
    - str "0x12345678": конвертирует в "!12345678"

    Args:
        node_id: Node ID в любом формате (int, str)

    Returns:
        Нормализованный node ID в формате "!hex" или None, если node_id пустой/невалидный
    """
    if node_id is None:
        return None

    try:
        if isinstance(node_id, int):
            # int -> "!hex"
            return f"!{hex(node_id)[2:]}"
        elif isinstance(node_id, str):
            node_str = node_id.strip()
            if not node_str:
                return None

            # Если уже в формате "!hex", нормализуем регистр
            if node_str.startswith("!"):
                hex_part = node_str[1:]
                if not hex_part:
                    return None
                # Проверяем, что после "!" валидный hex
                try:
                    int(hex_part, 16)
                    return f"!{hex_part.lower()}"
                except ValueError:
                    # Если невалидный hex, возвращаем как есть (нормализованный регистр)
                    return f"!{hex_part.lower()}"

            # Если начинается с "0x" или "0X", убираем префикс
            if node_str.startswith("0x") or node_str.startswith("0X"):
                hex_part = node_str[2:]
                if not hex_part:
                    return None
                try:
                    num = int(hex_part, 16)
                    return f"!{hex(num)[2:]}"
                except ValueError:
                    # Если невалидный hex, возвращаем как есть с "!"
                    return f"!{hex_part.lower()}"

            # Пытаемся распарсить как hex число
            try:
                num = int(node_str, 16)
                return f"!{hex(num)[2:]}"
            except ValueError:
                # Если не hex, пытаемся как десятичное число
                try:
                    num = int(node_str, 10)
                    return f"!{hex(num)[2:]}"
                except ValueError:
                    # Если не число, возвращаем как есть с "!" (для нестандартных форматов)
                    return f"!{node_str.lower()}"
        else:
            # Для других типов конвертируем в строку и пытаемся распарсить
            return _normalize_node_id(str(node_id))
    except Exception as e:
        # В случае любой ошибки возвращаем None
        logger.warning(f"Ошибка нормализации node_id: {node_id}, error: {e}")
        return None


class BaseParser:
    def __init__(self, node_cache_service: Optional[Any] = None):
        self.node_cache_service = node_cache_service

    def _common_enrich(
        self,
        raw_payload: Dict[str, Any],
        topic: str,
        raw_payload_bytes: Optional[bytes] = None,
    ) -> MeshtasticMessage:
        """
        Создает MeshtasticMessage из распарсенных данных и обновляет кэш нод.

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

        from_node_name = None
        from_node_short = None

        if message_type == "nodeinfo":
            # Логируем полную структуру raw_payload для контекста
            try:
                raw_payload_json = json.dumps(raw_payload, ensure_ascii=False, indent=2, default=str)
                logger.info(
                    f"📋 Полная структура raw_payload для nodeinfo:\n"
                    f"{'=' * 80}\n"
                    f"{raw_payload_json}\n"
                    f"{'=' * 80}"
                )
            except Exception as e:
                logger.warning(
                    f"Не удалось сериализовать raw_payload в JSON: {e}"
                )
            
            payload_data = raw_payload.get("payload", {})
            if isinstance(payload_data, dict):
                # Логируем полное содержимое распарсенного payload nodeinfo в красивом JSON формате
                try:
                    payload_json = json.dumps(payload_data, ensure_ascii=False, indent=2, default=str)
                    logger.info(
                        f"📦 Распарсенный payload nodeinfo (полное содержимое):\n"
                        f"{'=' * 80}\n"
                        f"{payload_json}\n"
                        f"{'=' * 80}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Не удалось сериализовать payload nodeinfo в JSON: {e}. "
                        f"Payload type: {type(payload_data)}, keys: {list(payload_data.keys()) if isinstance(payload_data, dict) else 'N/A'}"
                    )
                
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
                    node_id_from_payload = from_node_str
                    logger.debug(
                        f"node_id не найден в payload nodeinfo, используем from_node: {node_id_from_payload}"
                    )
                
                # Нормализуем node_id перед обновлением кэша
                if node_id_from_payload:
                    node_id_normalized = _normalize_node_id(node_id_from_payload)
                    if self.node_cache_service and node_id_normalized:
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
                    elif not node_id_normalized:
                        logger.warning(
                            f"Не удалось нормализовать node_id из nodeinfo: {node_id_from_payload} "
                            f"(тип: {type(node_id_from_payload)})"
                        )
                else:
                    logger.warning(
                        f"node_id не найден в nodeinfo сообщении. payload_data keys: {list(payload_data.keys())}, "
                        f"from_node: {from_node_str}"
                    )
        elif message_type == "position":
            payload_data = raw_payload.get("payload", {})
            if isinstance(payload_data, dict) and self.node_cache_service:
                node_id = None
                from_node_raw = raw_payload.get("from")
                if from_node_raw:
                    node_id = _normalize_node_id(from_node_raw)
                if node_id:
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
                else:
                    logger.warning(
                        "Получено сообщение position без ID ноды (sender/from отсутствует)"
                    )

        # Кэширование отправителя
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

        # Кэширование ретранслятора
        if message_type != "nodeinfo" and self.node_cache_service and sender_node_str:
            cached_sender_name = self.node_cache_service.get_node_name(sender_node_str)
            cached_sender_short = self.node_cache_service.get_node_shortname(sender_node_str)
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
            f"Распарсено Meshtastic сообщение: topic={topic}, "
            f"message_id={message_id}, from_node={from_node_str}, "
            f"from_node_name={from_node_name}"
        )
        return message


class JsonMessageParser(BaseParser):
    """Парсит JSON сообщения от Meshtastic."""

    def parse(self, topic: str, payload: bytes) -> MeshtasticMessage:
        """
        Парсит JSON payload и создает MeshtasticMessage.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах

        Returns:
            Созданный объект MeshtasticMessage
        """
        payload_str = payload.decode("utf-8", errors="replace")
        raw_payload: Dict[str, Any] = json.loads(payload_str)
        # Сохраняем исходные bytes для проксирования
        return self._common_enrich(raw_payload, topic, raw_payload_bytes=payload)


class ProtobufMessageParser(BaseParser):
    """Парсит Protobuf сообщения от Meshtastic."""

    def parse(self, topic: str, payload: bytes) -> MeshtasticMessage:
        """Парсит Protobuf payload и создает MeshtasticMessage."""
        raw_payload = self._parse_protobuf_payload(payload)
        # Сохраняем исходные bytes для проксирования
        return self._common_enrich(raw_payload, topic, raw_payload_bytes=payload)

    def _parse_protobuf_payload(self, payload: bytes) -> Dict[str, Any]:
        if not PROTOBUF_AVAILABLE:
            raise RuntimeError(
                "Выбран payload_format=protobuf, но зависимости meshtastic/protobuf не установлены."
            )

        envelope = mqtt_pb2.ServiceEnvelope()
        envelope.ParseFromString(payload)

        envelope_dict = MessageToDict(
            envelope,
            preserving_proto_field_name=True,
        )

        packet = (
            envelope_dict.get("packet", {}) if isinstance(envelope_dict, dict) else {}
        )
        decoded = packet.get("decoded", {}) if isinstance(packet, dict) else {}

        raw_payload: Dict[str, Any] = {
            "type": None,
            "portnum": decoded.get("portnum"),
            "id": packet.get("id"),
            "from": packet.get("from"),
            "sender": packet.get("sender"),
            "to": packet.get("to"),
            "hop_start": packet.get("hop_start"),
            "hop_limit": packet.get("hop_limit"),
            "hops_away": None,
            "timestamp": packet.get("rx_time") or packet.get("timestamp"),
            "rx_time": packet.get("rx_time"),
            "rssi": packet.get("rx_rssi"),
            "snr": packet.get("rx_snr"),
            "payload": {},
        }

        portnum = decoded.get("portnum")
        if portnum:
            portnum_lower = str(portnum).lower()
            if "text_message" in portnum_lower and "compressed" not in portnum_lower:
                raw_payload["type"] = "text"
            elif "text_message_compressed" in portnum_lower:
                raw_payload["type"] = "text_compressed"
            elif "nodeinfo" in portnum_lower:
                raw_payload["type"] = "nodeinfo"
            elif "position" in portnum_lower:
                raw_payload["type"] = "position"
            elif "telemetry" in portnum_lower:
                raw_payload["type"] = "telemetry"
            elif "routing" in portnum_lower:
                raw_payload["type"] = "routing"
            elif "admin" in portnum_lower:
                raw_payload["type"] = "admin"
            elif "paxcounter" in portnum_lower:
                raw_payload["type"] = "paxcounter"
            elif "waypoint" in portnum_lower:
                raw_payload["type"] = "waypoint"
            elif "audio" in portnum_lower:
                raw_payload["type"] = "audio"
            elif "ip_tunnel" in portnum_lower:
                raw_payload["type"] = "ip_tunnel"

        payload_b64 = decoded.get("payload")
        if payload_b64:
            try:
                decoded_bytes = base64.b64decode(payload_b64)
                raw_payload["payload"] = {
                    "raw_base64": payload_b64,
                    "raw_hex": decoded_bytes.hex(),
                }

                if raw_payload["type"] == "text":
                    text = decoded_bytes.decode("utf-8", errors="replace")
                    raw_payload["payload"]["text"] = text

                elif raw_payload["type"] == "text_compressed":
                    try:
                        import unishox2_py  # type: ignore

                        decompressed = unishox2_py.decompress(decoded_bytes)
                        raw_payload["payload"]["text"] = decompressed.decode(
                            "utf-8", errors="replace"
                        )
                        raw_payload["payload"]["unishox"] = True
                    except Exception as e:
                        raw_payload["payload"]["unishox_error"] = str(e)

                elif raw_payload["type"] == "nodeinfo":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        user_msg = mesh_pb2.User()
                        user_msg.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            user_msg, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "position":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        pos = mesh_pb2.Position()
                        pos.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            pos, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "telemetry":
                    try:
                        from meshtastic.protobuf import telemetry_pb2  # type: ignore

                        tm = telemetry_pb2.Telemetry()
                        tm.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            tm, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "routing":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        rt = mesh_pb2.Routing()
                        rt.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            rt, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "admin":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        adm = mesh_pb2.AdminMessage()
                        adm.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            adm, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "paxcounter":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        pax = mesh_pb2.Paxcounter()
                        pax.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            pax, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "waypoint":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        wp = mesh_pb2.Waypoint()
                        wp.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            wp, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

            except Exception:
                raw_payload["payload"] = {"raw_base64": payload_b64}

        return raw_payload


class MessageService:
    """Парсит сообщения от Meshtastic (JSON или Protobuf) и создает доменные модели."""

    def __init__(
        self, node_cache_service: Optional[Any] = None, payload_format: str = "json"
    ):
        """
        Создает парсеры для JSON и Protobuf сообщений.

        Args:
            node_cache_service: Сервис кэширования нод (опционально)
            payload_format: Формат payload ("json", "protobuf" или "both")
        """
        self.node_cache_service = node_cache_service
        self.payload_format = payload_format.lower() if payload_format else "json"
        self.json_parser = JsonMessageParser(node_cache_service=node_cache_service)
        self.protobuf_parser = ProtobufMessageParser(
            node_cache_service=node_cache_service
        )

    def parse_mqtt_message(self, topic: str, payload: bytes) -> MeshtasticMessage:
        """
        Парсит MQTT сообщение в зависимости от формата и топика.
        
        Для обновления кэша нод (nodeinfo, position) пытается парсить оба формата,
        если основной формат не подошел.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах

        Returns:
            Созданный объект MeshtasticMessage

        Raises:
            ValueError: Если сообщение не соответствует выбранному формату
        """
        is_protobuf_topic = "/e/" in topic and "/json/" not in topic
        should_parse_protobuf = (
            self.payload_format in ("protobuf", "both") and is_protobuf_topic
        )
        should_parse_json = (
            self.payload_format in ("json", "both") and not is_protobuf_topic
        )

        try:
            if should_parse_protobuf:
                return self.protobuf_parser.parse(topic, payload)
            if should_parse_json:
                return self.json_parser.parse(topic, payload)
            
            # Если формат не совпадает, но это nodeinfo или position - пытаемся парсить для кэша
            # Это важно для обновления кэша нод независимо от payload_format
            logger.debug(
                f"Формат не совпадает с payload_format={self.payload_format}, "
                f"пытаемся парсить для обновления кэша: topic={topic}"
            )
            if is_protobuf_topic:
                return self.protobuf_parser.parse(topic, payload)
            else:
                return self.json_parser.parse(topic, payload)
        except Exception as e:
            # Если основной формат не подошел, пробуем альтернативный для обновления кэша
            if should_parse_protobuf:
                logger.debug(f"Ошибка парсинга protobuf, пробуем JSON для кэша: {e}")
                try:
                    return self.json_parser.parse(topic, payload)
                except Exception:
                    raise e
            elif should_parse_json:
                logger.debug(f"Ошибка парсинга JSON, пробуем protobuf для кэша: {e}")
                try:
                    return self.protobuf_parser.parse(topic, payload)
                except Exception:
                    raise e
            raise ValueError(
                f"Сообщение не соответствует выбранному формату payload_format={self.payload_format}, topic={topic}"
            )
        except json.JSONDecodeError as e:
            logger.error(
                f"Ошибка парсинга JSON из MQTT сообщения: topic={topic}, error={e}",
                exc_info=True,
            )
            try:
                raw_str = payload.decode("utf-8", errors="replace")
            except Exception:
                raw_str = f"<binary data, {len(payload)} bytes>"
            return MeshtasticMessage(
                topic=topic,
                raw_payload={"error": "Failed to parse JSON", "raw": raw_str},
                raw_payload_bytes=payload,
            )
        except UnicodeDecodeError as e:
            logger.warning(
                f"Невозможно декодировать payload как UTF-8 (возможно, protobuf): topic={topic}, error={e}"
            )
            return MeshtasticMessage(
                topic=topic,
                raw_payload={
                    "error": "Binary payload (protobuf) - use JSON topic instead"
                },
                raw_payload_bytes=payload,
            )
        except Exception as e:
            logger.error(
                f"Неожиданная ошибка при парсинге MQTT сообщения: topic={topic}, error={e}",
                exc_info=True,
            )
            try:
                raw_str = payload.decode("utf-8", errors="ignore")
            except Exception:
                raw_str = f"<binary data, {len(payload)} bytes>"
            return MeshtasticMessage(
                topic=topic,
                raw_payload={"error": str(e), "raw": raw_str},
                raw_payload_bytes=payload,
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
        )

        packet = (
            envelope_dict.get("packet", {}) if isinstance(envelope_dict, dict) else {}
        )
        decoded = packet.get("decoded", {}) if isinstance(packet, dict) else {}

        raw_payload: Dict[str, Any] = {
            "type": None,
            "portnum": decoded.get("portnum"),
            "id": packet.get("id"),
            "from": packet.get("from"),
            "sender": packet.get("sender"),
            "to": packet.get("to"),
            "hop_start": packet.get("hop_start"),
            "hop_limit": packet.get("hop_limit"),
            "hops_away": None,
            "timestamp": packet.get("rx_time") or packet.get("timestamp"),
            "rx_time": packet.get("rx_time"),
            "rssi": packet.get("rx_rssi"),
            "snr": packet.get("rx_snr"),
            "payload": {},
        }

        portnum = decoded.get("portnum")
        if portnum:
            portnum_lower = str(portnum).lower()
            if "text_message" in portnum_lower and "compressed" not in portnum_lower:
                raw_payload["type"] = "text"
            elif "text_message_compressed" in portnum_lower:
                raw_payload["type"] = "text_compressed"
            elif "nodeinfo" in portnum_lower:
                raw_payload["type"] = "nodeinfo"
            elif "position" in portnum_lower:
                raw_payload["type"] = "position"
            elif "telemetry" in portnum_lower:
                raw_payload["type"] = "telemetry"
            elif "routing" in portnum_lower:
                raw_payload["type"] = "routing"
            elif "admin" in portnum_lower:
                raw_payload["type"] = "admin"
            elif "paxcounter" in portnum_lower:
                raw_payload["type"] = "paxcounter"
            elif "waypoint" in portnum_lower:
                raw_payload["type"] = "waypoint"
            elif "audio" in portnum_lower:
                raw_payload["type"] = "audio"
            elif "ip_tunnel" in portnum_lower:
                raw_payload["type"] = "ip_tunnel"

        payload_b64 = decoded.get("payload")
        if payload_b64:
            try:
                decoded_bytes = base64.b64decode(payload_b64)
                raw_payload["payload"] = {
                    "raw_base64": payload_b64,
                    "raw_hex": decoded_bytes.hex(),
                }

                if raw_payload["type"] == "text":
                    text = decoded_bytes.decode("utf-8", errors="replace")
                    raw_payload["payload"]["text"] = text

                elif raw_payload["type"] == "text_compressed":
                    try:
                        import unishox2_py  # type: ignore

                        decompressed = unishox2_py.decompress(decoded_bytes)
                        raw_payload["payload"]["text"] = decompressed.decode(
                            "utf-8", errors="replace"
                        )
                        raw_payload["payload"]["unishox"] = True
                    except Exception as e:
                        raw_payload["payload"]["unishox_error"] = str(e)

                elif raw_payload["type"] == "nodeinfo":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        user_msg = mesh_pb2.User()
                        user_msg.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            user_msg, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "position":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        pos = mesh_pb2.Position()
                        pos.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            pos, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "telemetry":
                    try:
                        from meshtastic.protobuf import telemetry_pb2  # type: ignore

                        tm = telemetry_pb2.Telemetry()
                        tm.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            tm, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "routing":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        rt = mesh_pb2.Routing()
                        rt.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            rt, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "admin":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        adm = mesh_pb2.AdminMessage()
                        adm.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            adm, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "paxcounter":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        pax = mesh_pb2.Paxcounter()
                        pax.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            pax, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

                elif raw_payload["type"] == "waypoint":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        wp = mesh_pb2.Waypoint()
                        wp.ParseFromString(decoded_bytes)
                        raw_payload["payload"] = MessageToDict(
                            wp, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        raw_payload["payload"] = {
                            "raw_base64": payload_b64,
                            "decode_error": str(e),
                        }

            except Exception:
                raw_payload["payload"] = {"raw_base64": payload_b64}

        return raw_payload
