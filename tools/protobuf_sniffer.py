"""
Утилита для отладки: подписывается на MQTT брокер, принимает protobuf-пакеты
Meshtastic (topics с `/e/`) и JSON-пакеты (topics с `/json/`), декодирует их
и выводит в консоль форматированный JSON с временными метками.

Пакеты с одинаковым ID группируются вместе и выводятся одной группой,
разделенной "===================".

Настройки задаются в YAML/JSON файле.

Пример запуска:
  python tools/protobuf_sniffer.py --config tools/protobuf_sniffer.yaml

Пример YAML (protobuf_sniffer.yaml):
  host: mosquitto
  port: 1883
  topic: msh/#   # подписываемся на все топики (protobuf и JSON)
  username: ""
  password: ""
  client_id: meshtastic-sniffer
  keepalive: 60
  qos: 0
  pretty: true
  color: true
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import base64
import aiomqtt
from google.protobuf.json_format import MessageToDict
import yaml

# Импорт meshtastic.protobuf с обработкой ошибок
# Проблема: meshtastic.__init__ импортирует pubsub, который может иметь проблемы совместимости
# Пытаемся обойти проблему, загружая protobuf модули напрямую
PROTOBUF_AVAILABLE = False
mqtt_pb2 = None

DEFAULT_CONFIG = {
    "host": "212.193.26.136",
    "port": 1883,
    "topic": "msh/#",
    "username": None,
    "password": None,
    "client_id": None,
    "keepalive": 60,
    "qos": 1,
    "pretty": True,
    "color": True,
}

try:
    from meshtastic.protobuf import mqtt_pb2  # type: ignore

    PROTOBUF_AVAILABLE = True
except (NameError, ImportError) as e:
    error_msg = str(e)
    if "Publisher" in error_msg or "pubsub" in error_msg.lower():
        # Пытаемся обойти проблему, загружая protobuf напрямую через importlib
        try:
            import importlib.util
            import os

            # Ищем meshtastic в site-packages
            meshtastic_protobuf_path = None
            for path in sys.path:
                if "site-packages" in path or "dist-packages" in path:
                    potential_path = os.path.join(
                        path, "meshtastic", "protobuf", "mqtt_pb2.py"
                    )
                    if os.path.exists(potential_path):
                        meshtastic_protobuf_path = potential_path
                        break

            if meshtastic_protobuf_path:
                # Загружаем модуль напрямую, минуя __init__.py
                spec = importlib.util.spec_from_file_location(
                    "meshtastic.protobuf.mqtt_pb2", meshtastic_protobuf_path
                )
                if spec and spec.loader:
                    mqtt_pb2 = importlib.util.module_from_spec(spec)
                    # Добавляем в sys.modules для корректной работы импортов внутри модуля
                    sys.modules["meshtastic"] = type(sys)("meshtastic")
                    sys.modules["meshtastic.protobuf"] = type(sys)("meshtastic.protobuf")
                    sys.modules["meshtastic.protobuf.mqtt_pb2"] = mqtt_pb2
                    spec.loader.exec_module(mqtt_pb2)
                    PROTOBUF_AVAILABLE = True
                    print(
                        "Предупреждение: Загружен meshtastic.protobuf напрямую, "
                        "обходя проблему с pubsub.",
                        file=sys.stderr,
                    )
        except Exception as direct_import_error:
            print(
                "Ошибка: Проблема с библиотекой pubsub при импорте meshtastic.\n"
                "Это известная проблема совместимости версий.\n\n"
                "Решение:\n"
                "1. Обновите библиотеку pubsub: pip install --upgrade pubsub\n"
                "2. Или переустановите meshtastic: pip install --upgrade --force-reinstall meshtastic\n"
                "3. Если проблема сохраняется, попробуйте:\n"
                "   pip install --upgrade meshtastic pubsub pypubsub\n\n"
                f"Детали ошибки: {error_msg}\n"
                f"Ошибка прямого импорта: {direct_import_error}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        print(
            f"Ошибка импорта meshtastic.protobuf: {error_msg}\n"
            "Убедитесь, что установлены зависимости: pip install meshtastic protobuf",
            file=sys.stderr,
        )
        sys.exit(1)
except Exception as e:
    print(
        f"Неожиданная ошибка при импорте meshtastic.protobuf: {e}\n"
        "Убедитесь, что установлены зависимости: pip install meshtastic protobuf",
        file=sys.stderr,
    )
    sys.exit(1)

if not PROTOBUF_AVAILABLE or mqtt_pb2 is None:
    print(
        "Критическая ошибка: Не удалось загрузить meshtastic.protobuf.mqtt_pb2",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    import unishox2_py  # type: ignore

    UNISHOX_AVAILABLE = True
except Exception:
    UNISHOX_AVAILABLE = False


def _to_json(data: Dict[str, Any], pretty: bool, color: bool) -> str:
    text = json.dumps(data, indent=2 if pretty else None, ensure_ascii=False)
    if color and sys.stdout.isatty():
        try:
            # минимальная подсветка для читаемости
            from pygments import highlight  # type: ignore
            from pygments.formatters import TerminalFormatter  # type: ignore
            from pygments.lexers import JsonLexer  # type: ignore

            return highlight(text, JsonLexer(), TerminalFormatter())
        except Exception:
            return text
    return text


def _normalize_node_id_for_sniffer(node_id: Any) -> Optional[str]:
    """
    Нормализует node ID к формату "!hex" для sniffer.
    
    Args:
        node_id: Node ID в любом формате (int, str)
    
    Returns:
        Нормализованный node ID в формате "!hex" или None
    """
    if node_id is None:
        return None
    try:
        if isinstance(node_id, int):
            return f"!{hex(node_id)[2:]}"
        elif isinstance(node_id, str):
            node_str = node_id.strip()
            if not node_str:
                return None
            if node_str.startswith("!"):
                return node_str.lower()
            # Пытаемся распарсить как hex
            try:
                num = int(node_str, 16)
                return f"!{hex(num)[2:]}"
            except ValueError:
                return f"!{node_str.lower()}"
    except Exception:
        return None
    return None


def decode_json_payload(payload: bytes) -> Dict[str, Any]:
    """
    Декодирует JSON payload из топика msh/2/json/#.
    
    Args:
        payload: JSON payload в байтах
        
    Returns:
        Распарсенный JSON словарь
    """
    try:
        json_str = payload.decode("utf-8", errors="replace")
        data = json.loads(json_str)
        return data
    except json.JSONDecodeError as e:
        return {"_error": f"JSON decode error: {e}", "_raw": payload.decode("utf-8", errors="replace")}
    except Exception as e:
        return {"_error": f"Error processing JSON: {e}"}


def decode_payload(payload: bytes) -> Dict[str, Any]:
    envelope = mqtt_pb2.ServiceEnvelope()
    envelope.ParseFromString(payload)
    data = MessageToDict(envelope, preserving_proto_field_name=True)

    # Извлекаем packet для доступа к полям маршрутизации
    packet = data.get("packet", {})
    
    # Извлекаем и нормализуем поля маршрутизации из packet
    if isinstance(packet, dict):
        # next_hop - следующий узел в маршруте (если сообщение еще не достигло получателя)
        next_hop = packet.get("next_hop")
        if next_hop is not None:
            next_hop_normalized = _normalize_node_id_for_sniffer(next_hop)
            if next_hop_normalized:
                packet["next_hop_normalized"] = next_hop_normalized
        
        # relay_node - нода, которая ретранслировала сообщение
        # Проверяем наличие поля relay_node (может отсутствовать в некоторых версиях)
        relay_node = packet.get("relay_node")
        if relay_node is not None:
            relay_node_normalized = _normalize_node_id_for_sniffer(relay_node)
            if relay_node_normalized:
                packet["relay_node_normalized"] = relay_node_normalized
                packet["relay_node_source"] = "relay_node_field"
        # Если relay_node нет, но есть sender, используем sender как relay_node
        elif packet.get("sender") is not None:
            sender = packet.get("sender")
            relay_node_normalized = _normalize_node_id_for_sniffer(sender)
            if relay_node_normalized:
                packet["relay_node_normalized"] = relay_node_normalized
                packet["relay_node_source"] = "sender_field"
        
        # Также нормализуем основные поля для консистентности
        if packet.get("from") is not None:
            from_normalized = _normalize_node_id_for_sniffer(packet.get("from"))
            if from_normalized:
                packet["from_normalized"] = from_normalized
        
        if packet.get("to") is not None:
            to_normalized = _normalize_node_id_for_sniffer(packet.get("to"))
            if to_normalized:
                packet["to_normalized"] = to_normalized
        
        if packet.get("sender") is not None:
            sender_normalized = _normalize_node_id_for_sniffer(packet.get("sender"))
            if sender_normalized:
                packet["sender_normalized"] = sender_normalized

    # Декодируем base64 payload внутри decoded, если есть
    try:
        decoded = packet.get("decoded", {})
        b64_payload = decoded.get("payload")
        portnum = str(decoded.get("portnum", "")).lower()
        if isinstance(b64_payload, str):
            try:
                decoded_bytes = base64.b64decode(b64_payload, validate=True)
                decoded["payload_bytes_len"] = len(decoded_bytes)
                decoded["payload_hex"] = decoded_bytes.hex()

                # Пытаемся декодировать по типу portnum
                decoded["payload_decoded"] = None

                # TEXT_MESSAGE_APP
                if "text_message" in portnum and "compressed" not in portnum:
                    decoded["payload_decoded"] = decoded_bytes.decode(
                        "utf-8", errors="replace"
                    )

                # TEXT_MESSAGE_COMPRESSED_APP (unishox2)
                elif "text_message_compressed" in portnum and UNISHOX_AVAILABLE:
                    try:
                        decompressed = unishox2_py.decompress(decoded_bytes)
                        decoded["payload_decoded"] = decompressed.decode(
                            "utf-8", errors="replace"
                        )
                        decoded["payload_unishox"] = True
                    except Exception:
                        decoded["payload_unishox_error"] = True

                # NODEINFO_APP (user)
                elif "nodeinfo" in portnum:
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        user_msg = mesh_pb2.User()
                        user_msg.ParseFromString(decoded_bytes)
                        decoded["payload_decoded"] = MessageToDict(
                            user_msg, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        decoded["payload_decode_error"] = str(e)

                # POSITION_APP
                elif "position" in portnum:
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        pos = mesh_pb2.Position()
                        pos.ParseFromString(decoded_bytes)
                        decoded["payload_decoded"] = MessageToDict(
                            pos, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        decoded["payload_decode_error"] = str(e)

                # WAYPOINT_APP
                elif "waypoint" in portnum:
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        wp = mesh_pb2.Waypoint()
                        wp.ParseFromString(decoded_bytes)
                        decoded["payload_decoded"] = MessageToDict(
                            wp, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        decoded["payload_decode_error"] = str(e)

                # TELEMETRY_APP
                elif "telemetry" in portnum:
                    try:
                        from meshtastic.protobuf import telemetry_pb2  # type: ignore

                        tm = telemetry_pb2.Telemetry()
                        tm.ParseFromString(decoded_bytes)
                        decoded["payload_decoded"] = MessageToDict(
                            tm, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        decoded["payload_decode_error"] = str(e)

                # PAXCOUNTER_APP
                elif "paxcounter" in portnum:
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        pax = mesh_pb2.Paxcounter()
                        pax.ParseFromString(decoded_bytes)
                        decoded["payload_decoded"] = MessageToDict(
                            pax, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        decoded["payload_decode_error"] = str(e)

                # ROUTING_APP
                elif "routing" in portnum:
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        rt = mesh_pb2.Routing()
                        rt.ParseFromString(decoded_bytes)
                        decoded["payload_decoded"] = MessageToDict(
                            rt, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        decoded["payload_decode_error"] = str(e)

                # ADMIN_APP
                elif "admin" in portnum:
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        adm = mesh_pb2.AdminMessage()
                        adm.ParseFromString(decoded_bytes)
                        decoded["payload_decoded"] = MessageToDict(
                            adm, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        decoded["payload_decode_error"] = str(e)

                # NEIGHBORINFO_APP
                elif "neighborinfo" in portnum:
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        neighbor_info = mesh_pb2.NeighborInfo()
                        neighbor_info.ParseFromString(decoded_bytes)
                        decoded["payload_decoded"] = MessageToDict(
                            neighbor_info, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        decoded["payload_decode_error"] = str(e)

                # TRACEROUTE_APP
                elif "traceroute" in portnum:
                    try:
                        from meshtastic.protobuf import mesh_pb2  # type: ignore

                        route_discovery = mesh_pb2.RouteDiscovery()
                        route_discovery.ParseFromString(decoded_bytes)
                        decoded["payload_decoded"] = MessageToDict(
                            route_discovery, preserving_proto_field_name=True
                        )
                    except Exception as e:
                        decoded["payload_decode_error"] = str(e)

                # AUDIO_APP (оставляем как hex, это codec2)
                elif "audio" in portnum:
                    decoded["payload_decoded"] = None

                # IP_TUNNEL_APP (сырые IP пакеты) — оставляем hex
                elif "ip_tunnel" in portnum:
                    decoded["payload_decoded"] = None

            except Exception:
                pass
    except Exception:
        pass

    return data


def _extract_packet_id(data: Dict[str, Any]) -> Optional[str]:
    """
    Извлекает ID пакета для группировки.
    
    Поддерживает как protobuf (через packet.id), так и JSON форматы.
    
    Args:
        data: Декодированные данные пакета (protobuf или JSON)
        
    Returns:
        ID пакета в виде строки или None
    """
    try:
        # Для protobuf формата: ищем в packet.id
        packet = data.get("packet", {})
        if isinstance(packet, dict):
            packet_id = packet.get("id")
            if packet_id is not None:
                return str(packet_id)
        
        # Для JSON формата: может быть прямо в корне или в другом месте
        # Пытаемся найти id в разных местах
        packet_id = data.get("id") or data.get("packet_id")
        if packet_id is not None:
            return str(packet_id)
        
        # Если нет явного ID, пытаемся использовать комбинацию from + to + timestamp
        # для уникальной идентификации
        if isinstance(packet, dict):
            from_node = packet.get("from")
            to_node = packet.get("to")
            rx_time = packet.get("rx_time") or packet.get("rxTime")
            if from_node is not None and rx_time is not None:
                return f"{from_node}_{to_node}_{rx_time}"
        
        # Для JSON: проверяем корневые поля
        from_node = data.get("from")
        to_node = data.get("to")
        rx_time = data.get("rx_time") or data.get("rxTime")
        if from_node is not None and rx_time is not None:
            return f"{from_node}_{to_node}_{rx_time}"
        
        # Если ничего не найдено, возвращаем None (пакет не будет сгруппирован)
        return None
    except Exception:
        return None


def load_config(path: Path) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                data = loaded
    cfg = DEFAULT_CONFIG | data
    return cfg


async def run(cfg: Dict[str, Any]) -> None:
    # Словарь для группировки пакетов по ID
    # Ключ: packet_id, Значение: список кортежей (timestamp, topic, decoded_data)
    packet_groups: Dict[str, list] = {}
    # ID текущей активной группы
    current_group_id: Optional[str] = None
    
    async def flush_group(packet_id: str) -> None:
        """Выводит группу пакетов и очищает её."""
        if packet_id not in packet_groups or not packet_groups[packet_id]:
            return
        
        group = packet_groups[packet_id]
        if group:
            # Выводим разделитель
            print("=" * 50)
            # Выводим все пакеты группы
            for timestamp, topic, decoded_data in group:
                print(f"[{timestamp}] Topic: {topic}")
                print(
                    _to_json(
                        decoded_data,
                        pretty=bool(cfg["pretty"]),
                        color=bool(cfg["color"]),
                    )
                )
                print()  # Пустая строка между пакетами в группе
            # Выводим разделитель
            print("=" * 50)
            print()  # Пустая строка после группы
            
            # Очищаем группу
            del packet_groups[packet_id]
    
    async with aiomqtt.Client(
        hostname=cfg["host"],
        port=int(cfg["port"]),
        username=cfg.get("username") or None,
        password=cfg.get("password") or None,
        keepalive=int(cfg["keepalive"]),
        identifier=cfg.get("client_id") or None,
    ) as client:
        await client.subscribe(cfg["topic"], qos=int(cfg["qos"]))
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"Subscribed to {cfg['topic']} on {cfg['host']}:{cfg['port']}",
            file=sys.stderr,
        )

        async for msg in client.messages:
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Определяем тип топика: JSON или protobuf
                is_json_topic = "/json/" in msg.topic.value
                
                if is_json_topic:
                    # Обрабатываем JSON payload
                    decoded = decode_json_payload(msg.payload)
                else:
                    # Обрабатываем protobuf payload
                    decoded = decode_payload(msg.payload)
                
                # Извлекаем ID пакета для группировки
                packet_id = _extract_packet_id(decoded)
                
                if packet_id:
                    # Если пришел пакет с другим ID, выводим предыдущую группу
                    if current_group_id is not None and current_group_id != packet_id:
                        await flush_group(current_group_id)
                    
                    # Добавляем пакет в группу
                    if packet_id not in packet_groups:
                        packet_groups[packet_id] = []
                    packet_groups[packet_id].append((timestamp, msg.topic.value, decoded))
                    current_group_id = packet_id
                else:
                    # Если ID нет, выводим предыдущую группу (если есть) и текущий пакет сразу
                    if current_group_id is not None:
                        await flush_group(current_group_id)
                        current_group_id = None
                    
                    # Выводим пакет без группировки
                    print(f"[{timestamp}] Topic: {msg.topic.value}")
                    print(
                        _to_json(
                            decoded,
                            pretty=bool(cfg["pretty"]),
                            color=bool(cfg["color"]),
                        )
                    )
                    print()  # Пустая строка после пакета
                    
            except Exception as e:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(
                    f"[{timestamp}] [decode-error] topic={msg.topic} err={e}",
                    file=sys.stderr,
                )
        
        # При завершении выводим все оставшиеся группы
        if current_group_id is not None:
            await flush_group(current_group_id)
        for packet_id in list(packet_groups.keys()):
            await flush_group(packet_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Meshtastic protobuf sniffer")
    parser.add_argument(
        "--config",
        default="tools/protobuf_sniffer.yaml",
        help="Путь к YAML/JSON конфигу (default: tools/protobuf_sniffer.yaml)",
    )
    args = parser.parse_args()

    # Windows fix: aiomqtt/paho использует add_reader/add_writer, нужны selector loop
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass

    cfg_path = Path(args.config)
    cfg = load_config(cfg_path)

    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)


if __name__ == "__main__":
    main()
