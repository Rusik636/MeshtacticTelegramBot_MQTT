"""
Утилита для отладки: подписывается на MQTT брокер, принимает protobuf-пакеты
Meshtastic (topics с `/e/`), декодирует их через meshtastic.protobuf.mqtt_pb2
и выводит в консоль форматированный JSON.

Настройки задаются в YAML/JSON файле.

Пример запуска:
  python tools/protobuf_sniffer.py --config tools/protobuf_sniffer.yaml

Пример YAML (protobuf_sniffer.yaml):
  host: mosquitto
  port: 1883
  topic: msh/2/e/#   # подписываемся на protobuf-топики
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
from pathlib import Path
from typing import Any, Dict

import base64
import aiomqtt
from google.protobuf.json_format import MessageToDict
from meshtastic.protobuf import mqtt_pb2
import yaml

try:
    import unishox2_py  # type: ignore

    UNISHOX_AVAILABLE = True
except Exception:
    UNISHOX_AVAILABLE = False


DEFAULT_CONFIG = {
    "host": "localhost",
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


def decode_payload(payload: bytes) -> Dict[str, Any]:
    envelope = mqtt_pb2.ServiceEnvelope()
    envelope.ParseFromString(payload)
    data = MessageToDict(envelope, preserving_proto_field_name=True)

    # Декодируем base64 payload внутри decoded, если есть
    try:
        packet = data.get("packet", {})
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
            f"Subscribed to {cfg['topic']} on {cfg['host']}:{cfg['port']}",
            file=sys.stderr,
        )

        async for msg in client.messages:
            try:
                decoded = decode_payload(msg.payload)
                print(
                    _to_json(
                        decoded, pretty=bool(cfg["pretty"]), color=bool(cfg["color"])
                    )
                )
            except Exception as e:
                print(f"[decode-error] topic={msg.topic} err={e}", file=sys.stderr)


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
