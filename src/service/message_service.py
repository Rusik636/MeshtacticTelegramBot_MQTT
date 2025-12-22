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
    """
    Базовый класс для парсеров сообщений Meshtastic.
    
    Отвечает только за парсинг данных, создание моделей и обновление кэша
    делегируется соответствующим сервисам.
    """
    
    def __init__(
        self,
        node_cache_service: Optional[Any] = None,
        message_factory: Optional[Any] = None,
        node_cache_updater: Optional[Any] = None,
    ):
        """
        Создает базовый парсер.

        Args:
            node_cache_service: Сервис кэша нод (для обратной совместимости)
            message_factory: Фабрика для создания доменных моделей
            node_cache_updater: Обновлятор кэша нод
        """
        self.node_cache_service = node_cache_service

        # Инициализируем фабрику и обновлятор, если не переданы
        if message_factory is None:
            from src.service.message_factory import MessageFactory
            message_factory = MessageFactory(node_cache_service=node_cache_service)
        self.message_factory = message_factory
        
        if node_cache_updater is None:
            from src.service.node_cache_updater import NodeCacheUpdater
            node_cache_updater = NodeCacheUpdater(node_cache_service=node_cache_service)
        self.node_cache_updater = node_cache_updater

    def _create_message(
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
        # Создаем доменную модель через фабрику
        message = self.message_factory.create_message(
            raw_payload=raw_payload,
            topic=topic,
            raw_payload_bytes=raw_payload_bytes,
        )
        
        # Обновляем кэш нод через обновлятор
        self.node_cache_updater.update_from_message(message, raw_payload)
        
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
        return self._create_message(raw_payload, topic, raw_payload_bytes=payload)


class ProtobufMessageParser(BaseParser):
    """Парсит Protobuf сообщения от Meshtastic."""

    def parse(self, topic: str, payload: bytes) -> MeshtasticMessage:
        """Парсит Protobuf payload и создает MeshtasticMessage."""
        raw_payload = self._parse_protobuf_payload(payload)
        # Сохраняем исходные bytes для проксирования
        return self._create_message(raw_payload, topic, raw_payload_bytes=payload)

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
            # Проверяем более специфичные типы первыми
            if "text_message_compressed" in portnum_lower:
                raw_payload["type"] = "text_compressed"
            elif "text_message" in portnum_lower:
                raw_payload["type"] = "text"
            elif "nodeinfo" in portnum_lower:
                raw_payload["type"] = "nodeinfo"
            elif "position" in portnum_lower:
                raw_payload["type"] = "position"
            elif "telemetry" in portnum_lower:
                raw_payload["type"] = "telemetry"
            elif "traceroute" in portnum_lower or "route_discovery" in portnum_lower:
                raw_payload["type"] = "routing"
            elif "routing" in portnum_lower:
                raw_payload["type"] = "routing"
            elif "neighborinfo" in portnum_lower:
                raw_payload["type"] = "neighborinfo"
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
            else:
                logger.debug(
                    f"Неизвестный portnum: {portnum} (topic={topic})"
                )
        else:
            # Если portnum не определен, логируем для отладки
            if decoded:
                logger.debug(
                    f"portnum не найден в decoded: topic={topic}, decoded keys={list(decoded.keys())}"
                )
            else:
                logger.debug(
                    f"decoded пустой или отсутствует: topic={topic}"
                )

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

                        # Пробуем RouteDiscovery (для ROUTING_APP / TRACEROUTE_APP)
                        try:
                            rt = mesh_pb2.RouteDiscovery()
                            rt.ParseFromString(decoded_bytes)
                            raw_payload["payload"] = MessageToDict(
                                rt, preserving_proto_field_name=True
                            )
                        except Exception:
                            # Если RouteDiscovery не подошел, пробуем Routing
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

                elif raw_payload["type"] == "neighborinfo":
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        # NEIGHBORINFO_APP использует структуру NeighborInfo
                        # Пробуем разные варианты структуры
                        try:
                            neighbor = mesh_pb2.NeighborInfo()
                            neighbor.ParseFromString(decoded_bytes)
                            raw_payload["payload"] = MessageToDict(
                                neighbor, preserving_proto_field_name=True
                            )
                        except Exception:
                            # Если NeighborInfo не найден, сохраняем как raw
                            raw_payload["payload"] = {
                                "raw_base64": payload_b64,
                                "raw_hex": decoded_bytes.hex(),
                                "note": "NeighborInfo structure not available",
                            }
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
        self,
        node_cache_service: Optional[Any] = None,
        payload_format: str = "json",
        message_factory: Any = None,
        node_cache_updater: Any = None,
    ):
        """
        Создает парсеры для JSON и Protobuf сообщений.

        Args:
            node_cache_service: Сервис кэширования нод (опционально)
            payload_format: Формат payload ("json", "protobuf" или "both")
            message_factory: Фабрика для создания доменных моделей (обязательно)
            node_cache_updater: Обновлятор кэша нод (обязательно)

        Raises:
            ValueError: Если message_factory или node_cache_updater не переданы
        """
        if message_factory is None:
            raise ValueError("message_factory обязателен для MessageService")
        if node_cache_updater is None:
            raise ValueError("node_cache_updater обязателен для MessageService")
        
        self.node_cache_service = node_cache_service
        self.payload_format = payload_format.lower() if payload_format else "json"
        
        self.json_parser = JsonMessageParser(
            node_cache_service=node_cache_service,
            message_factory=message_factory,
            node_cache_updater=node_cache_updater,
        )
        self.protobuf_parser = ProtobufMessageParser(
            node_cache_service=node_cache_service,
            message_factory=message_factory,
            node_cache_updater=node_cache_updater,
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
        except json.JSONDecodeError as e:
            # Специфичная обработка JSONDecodeError - возвращаем сообщение с ошибкой
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
            # Специфичная обработка UnicodeDecodeError
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
            # Если основной формат не подошел, пробуем альтернативный для обновления кэша
            if should_parse_protobuf:
                logger.debug(f"Ошибка парсинга protobuf, пробуем JSON для кэша: {e}")
                try:
                    return self.json_parser.parse(topic, payload)
                except Exception:
                    # Если и альтернативный не подошел, возвращаем сообщение с ошибкой
                    try:
                        raw_str = payload.decode("utf-8", errors="ignore")
                    except Exception:
                        raw_str = f"<binary data, {len(payload)} bytes>"
                    return MeshtasticMessage(
                        topic=topic,
                        raw_payload={"error": str(e), "raw": raw_str},
                        raw_payload_bytes=payload,
                    )
            elif should_parse_json:
                logger.debug(f"Ошибка парсинга JSON, пробуем protobuf для кэша: {e}")
                try:
                    return self.protobuf_parser.parse(topic, payload)
                except Exception:
                    # Если и альтернативный не подошел, возвращаем сообщение с ошибкой
                    try:
                        raw_str = payload.decode("utf-8", errors="ignore")
                    except Exception:
                        raw_str = f"<binary data, {len(payload)} bytes>"
                    return MeshtasticMessage(
                        topic=topic,
                        raw_payload={"error": str(e), "raw": raw_str},
                        raw_payload_bytes=payload,
                    )
            else:
                # Если формат не определен, возвращаем сообщение с ошибкой
                try:
                    raw_str = payload.decode("utf-8", errors="ignore")
                except Exception:
                    raw_str = f"<binary data, {len(payload)} bytes>"
                return MeshtasticMessage(
                    topic=topic,
                    raw_payload={
                        "error": f"Сообщение не соответствует выбранному формату payload_format={self.payload_format}",
                        "raw": raw_str,
                    },
                    raw_payload_bytes=payload,
                )

