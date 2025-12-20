"""
Сервис форматирования сообщений Meshtastic для Telegram.

Отвечает за преобразование доменных моделей в форматированный текст для отправки в Telegram.
"""

import html
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from src.domain.message import MeshtasticMessage

if TYPE_CHECKING:
    from src.service.node_cache_service import NodeCacheService

logger = logging.getLogger(__name__)


class TelegramMessageFormatter:
    """
    Форматтер сообщений Meshtastic для Telegram.
    
    Отвечает за преобразование доменных моделей в форматированный HTML текст.
    """

    def __init__(self, node_cache_service: Optional["NodeCacheService"] = None):
        """
        Создает форматтер сообщений.

        Args:
            node_cache_service: Сервис кэша нод для получения координат (опционально)
        """
        self.node_cache_service = node_cache_service

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
        - 🟢 Отличный: > 10 dB
        - 🟡 Хороший: 5 до 10 dB
        - 🟠 Удовлетворительный: 0 до 5 dB
        - 🔴 Плохой: -5 до 0 dB
        - ⚫ Очень плохой: < -5 dB

        Args:
            snr: Значение SNR в dB (может быть отрицательным для LoRa)

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

    def format(
        self, message: MeshtasticMessage, node_cache_service: Optional["NodeCacheService"] = None
    ) -> str:
        """
        Форматирует сообщение для отправки в Telegram.

        Поддерживает UTF-8 символы в названиях и тегах нод.
        Отображает качество сигнала с цветными индикаторами.
        Добавляет ссылку на местоположение, если доступно.

        Args:
            message: Сообщение Meshtastic для форматирования
            node_cache_service: Сервис кэша нод (если не передан в конструкторе)

        Returns:
            Отформатированная строка сообщения.
        """
        cache_service = node_cache_service or self.node_cache_service
        parts = []

        # Временная метка в формате чч:мм дд.мм.гггг (вверху)
        if message.timestamp:
            try:
                dt = datetime.fromtimestamp(message.timestamp)
                # Формат: чч:мм дд.мм.гггг (например: 22:30 09.12.2025)
                parts.append(f"🕐 <b>{dt.strftime('%H:%M %d.%m.%Y')}</b>")
            except (ValueError, OSError):
                pass

        # Формируем информацию об отправителе
        # Экранируем все пользовательские данные для защиты от XSS
        sender_info = []

        if message.from_node_name and message.from_node_short:
            # Если есть и longname и shortname: longname (shortname)
            escaped_longname = html.escape(message.from_node_name)
            escaped_shortname = html.escape(message.from_node_short)
            sender_info.append(f"{escaped_longname} ({escaped_shortname})")
        elif message.from_node_name:
            # Если есть только longname: longname
            sender_info.append(html.escape(message.from_node_name))
        elif message.from_node_short:
            # Если есть только shortname: shortname (без скобок)
            sender_info.append(html.escape(message.from_node_short))
        elif message.from_node:
            # Иначе: hex ID от from
            sender_info.append(html.escape(message.from_node))

        if sender_info:
            # Объединяем информацию об отправителе
            sender_str = " ".join(sender_info)
            parts.append(f"\n📡 <b>От:</b> {sender_str}")

        # Формируем информацию о ретрансляторе (sender)
        # Показываем только если sender отличается от from_node (сообщение было ретранслировано)
        # Сравниваем нормализованные значения (оба уже должны быть в формате "!hex")
        sender_normalized = (
            message.sender_node.lower() if message.sender_node else None
        )
        from_normalized = message.from_node.lower() if message.from_node else None
        if sender_normalized and sender_normalized != from_normalized:
            # Экранируем все пользовательские данные для защиты от XSS
            repeater_info = []

            if message.sender_node_name and message.sender_node_short:
                # Если есть и longname и shortname: longname (shortname)
                escaped_longname = html.escape(message.sender_node_name)
                escaped_shortname = html.escape(message.sender_node_short)
                repeater_info.append(f"{escaped_longname} ({escaped_shortname})")
            elif message.sender_node_name:
                # Если есть только longname: longname
                repeater_info.append(html.escape(message.sender_node_name))
            elif message.sender_node_short:
                # Если есть только shortname: shortname (без скобок)
                repeater_info.append(html.escape(message.sender_node_short))
            else:
                # Иначе: hex ID от sender
                repeater_info.append(html.escape(message.sender_node))

            if repeater_info:
                # Объединяем информацию о ретрансляторе
                repeater_str = " ".join(repeater_info)
                parts.append(f"🔄 <b>Ретранслировал:</b> {repeater_str}")

        # Формируем информацию о получателе
        if message.to_node:
            recipient_info = []
            # Если to_node = "Всем", просто показываем "Всем"
            if message.to_node == "Всем":
                recipient_info.append("Всем")
            else:
                # Получаем информацию о получателе из кэша, если доступен
                if cache_service:
                    cached_to_name = cache_service.get_node_name(message.to_node)
                    cached_to_short = cache_service.get_node_shortname(
                        message.to_node
                    )

                    if cached_to_name:
                        recipient_info.append(html.escape(cached_to_name))
                    elif cached_to_short:
                        recipient_info.append(html.escape(cached_to_short))

                # Добавляем ID получателя
                escaped_to_node = html.escape(message.to_node)
                if recipient_info:
                    recipient_info.append(f"({escaped_to_node})")
                else:
                    recipient_info.append(escaped_to_node)

            if recipient_info:
                recipient_str = " ".join(recipient_info)
                parts.append(f"📨 <b>Кому:</b> {recipient_str}\n")

        # Информация о ретрансляции
        if message.hops_away is not None:
            if message.hops_away == 0:
                parts.append("📬 Прямая доставка")
            else:
                parts.append(f"🔄 Ретранслировано {message.hops_away} раз")

        # Качество сигнала (RSSI и SNR с отдельными индикаторами)
        signal_parts = []
        if message.rssi is not None:
            rssi_emoji = self.get_rssi_quality_emoji(message.rssi)
            signal_parts.append(f"{rssi_emoji} RSSI: {message.rssi} dBm")

        if message.snr is not None:
            snr_emoji = self.get_snr_quality_emoji(message.snr)
            signal_parts.append(f"{snr_emoji} SNR: {message.snr:.1f} dB")

        if signal_parts:
            parts.append(f"📶 {' | '.join(signal_parts)}")

        # Местоположение отправителя и получателя (ссылки на Яндекс Карты)
        location_parts = []

        # Местоположение отправителя
        if cache_service and message.from_node:
            sender_position = cache_service.get_node_position(message.from_node)
            if sender_position:
                latitude, longitude, altitude = sender_position
                yandex_map_url = (
                    f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=15&l=map"
                )
                location_parts.append(f'📍 <a href="{yandex_map_url}">Отправитель</a>')
            else:
                location_parts.append("📍 Отправитель: Не известно")
        else:
            location_parts.append("📍 Отправитель: Не известно")

        # Местоположение получателя (только если получатель не "Всем")
        if message.to_node and message.to_node != "Всем":
            if cache_service:
                recipient_position = cache_service.get_node_position(message.to_node)
                if recipient_position:
                    latitude, longitude, altitude = recipient_position
                    yandex_map_url = (
                        f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=15&l=map"
                    )
                    location_parts.append(
                        f'📍 <a href="{yandex_map_url}">Получатель</a>'
                    )
                else:
                    location_parts.append("📍 Получатель: Не известно")
            else:
                location_parts.append("📍 Получатель: Не известно")

        if location_parts:
            parts.append(" | ".join(location_parts))

        # Текст сообщения в цитате (может содержать UTF-8 символы) - экранируем
        # HTML (внизу)
        if message.text:
            escaped_text = html.escape(message.text)
            # Формируем сообщение с цитатой: "💬 Сообщение:\n" + текст в цитате
            parts.append(
                f"\n💬 <b>Сообщение:</b>\n<blockquote>{escaped_text}</blockquote>"
            )

        if not parts:
            # Если не удалось извлечь структурированные данные, показываем raw
            parts.append("📨 Новое сообщение Meshtastic")
            if message.topic:
                # Экранируем топик для защиты от XSS
                escaped_topic = html.escape(message.topic)
                parts.append(f"Топик: {escaped_topic}")

        return "\n".join(parts)

    def format_with_grouping(
        self,
        message: MeshtasticMessage,
        received_by_nodes: List[Dict[str, Any]],
        show_receive_time: bool = False,
        node_cache_service: Optional["NodeCacheService"] = None,
    ) -> str:
        """
        Форматирует сообщение для отправки в Telegram с учетом группировки нод-получателей.

        Args:
            message: Сообщение Meshtastic для форматирования
            received_by_nodes: Список словарей с информацией о нодах-получателях
                Каждый словарь должен содержать: node_id, node_name, node_short,
                received_at, rssi, snr, hops_away, sender_node, sender_node_name
            show_receive_time: Показывать ли время получения каждой нодой
            node_cache_service: Сервис кэша нод (если не передан в конструкторе)

        Returns:
            Отформатированная строка сообщения с информацией о нодах-получателях.
        """
        cache_service = node_cache_service or self.node_cache_service
        parts = []

        # Временная метка в формате чч:мм дд.мм.гггг (вверху)
        if message.timestamp:
            try:
                dt = datetime.fromtimestamp(message.timestamp)
                parts.append(f"🕐 <b>{dt.strftime('%H:%M %d.%m.%Y')}</b>")
            except (ValueError, OSError):
                pass

        # Формируем информацию об отправителе
        sender_info = []
        if message.from_node_name and message.from_node_short:
            escaped_longname = html.escape(message.from_node_name)
            escaped_shortname = html.escape(message.from_node_short)
            sender_info.append(f"{escaped_longname} ({escaped_shortname})")
        elif message.from_node_name:
            sender_info.append(html.escape(message.from_node_name))
        elif message.from_node_short:
            sender_info.append(html.escape(message.from_node_short))
        elif message.from_node:
            sender_info.append(html.escape(message.from_node))

        if sender_info:
            sender_str = " ".join(sender_info)
            parts.append(f"\n📡 <b>От:</b> {sender_str}")

        # Формируем информацию о ретрансляторе (sender)
        sender_normalized = (
            message.sender_node.lower() if message.sender_node else None
        )
        from_normalized = message.from_node.lower() if message.from_node else None
        if sender_normalized and sender_normalized != from_normalized:
            repeater_info = []
            if message.sender_node_name and message.sender_node_short:
                escaped_longname = html.escape(message.sender_node_name)
                escaped_shortname = html.escape(message.sender_node_short)
                repeater_info.append(f"{escaped_longname} ({escaped_shortname})")
            elif message.sender_node_name:
                repeater_info.append(html.escape(message.sender_node_name))
            elif message.sender_node_short:
                repeater_info.append(html.escape(message.sender_node_short))
            else:
                repeater_info.append(html.escape(message.sender_node))

            if repeater_info:
                repeater_str = " ".join(repeater_info)
                parts.append(f"🔄 <b>Ретранслировал:</b> {repeater_str}")

        # Формируем информацию о получателе
        if message.to_node:
            recipient_info = []
            if message.to_node == "Всем":
                recipient_info.append("Всем")
            else:
                if cache_service:
                    cached_to_name = cache_service.get_node_name(message.to_node)
                    cached_to_short = cache_service.get_node_shortname(
                        message.to_node
                    )
                    if cached_to_name:
                        recipient_info.append(html.escape(cached_to_name))
                    elif cached_to_short:
                        recipient_info.append(html.escape(cached_to_short))

                escaped_to_node = html.escape(message.to_node)
                if recipient_info:
                    recipient_info.append(f"({escaped_to_node})")
                else:
                    recipient_info.append(escaped_to_node)

            if recipient_info:
                recipient_str = " ".join(recipient_info)
                parts.append(f"📨 <b>Кому:</b> {recipient_str}\n")

        # Информация о ретрансляции
        if message.hops_away is not None:
            if message.hops_away == 0:
                parts.append("📬 Прямая доставка")
            else:
                parts.append(f"🔄 Ретранслировано {message.hops_away} раз")

        # Качество сигнала (RSSI и SNR с отдельными индикаторами)
        signal_parts = []
        if message.rssi is not None:
            rssi_emoji = self.get_rssi_quality_emoji(message.rssi)
            signal_parts.append(f"{rssi_emoji} RSSI: {message.rssi} dBm")

        if message.snr is not None:
            snr_emoji = self.get_snr_quality_emoji(message.snr)
            signal_parts.append(f"{snr_emoji} SNR: {message.snr:.1f} dB")

        if signal_parts:
            parts.append(f"📶 {' | '.join(signal_parts)}")

        # Добавляем информацию о нодах-получателях
        if received_by_nodes:
            separator_length = 10
            parts.append("\n📥 <b>Получено нодами:</b>")

            for node_info in received_by_nodes:
                node_parts = []
                node_parts.append("  • ")

                # Имя ноды
                node_name = node_info.get("node_name")
                node_short = node_info.get("node_short")
                node_id = node_info.get("node_id", "")

                if node_name and node_short:
                    escaped_name = html.escape(node_name)
                    escaped_short = html.escape(node_short)
                    node_parts.append(f"{escaped_name} ({escaped_short})")
                elif node_name:
                    node_parts.append(html.escape(node_name))
                elif node_short:
                    node_parts.append(html.escape(node_short))
                else:
                    node_parts.append(html.escape(node_id))

                # Время получения (если включено)
                if show_receive_time:
                    received_at = node_info.get("received_at")
                    if received_at:
                        if isinstance(received_at, datetime):
                            time_str = received_at.strftime("%H:%M:%S")
                        elif isinstance(received_at, str):
                            try:
                                dt = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
                                time_str = dt.strftime("%H:%M:%S")
                            except (ValueError, AttributeError):
                                time_str = str(received_at)
                        else:
                            time_str = str(received_at)
                        node_parts.append(f" ({time_str})")

                # Качество сигнала
                rssi = node_info.get("rssi")
                if rssi is not None:
                    rssi_emoji = self.get_rssi_quality_emoji(rssi)
                    node_parts.append(f" {rssi_emoji} {rssi} dBm")

                parts.append("".join(node_parts))

            parts.append("\n")

        # Местоположение отправителя и получателя
        location_parts = []
        if cache_service and message.from_node:
            sender_position = cache_service.get_node_position(message.from_node)
            if sender_position:
                latitude, longitude, altitude = sender_position
                yandex_map_url = (
                    f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=15&l=map"
                )
                location_parts.append(f'📍 <a href="{yandex_map_url}">Отправитель</a>')
            else:
                location_parts.append("📍 Отправитель: Не известно")
        else:
            location_parts.append("📍 Отправитель: Не известно")

        if message.to_node and message.to_node != "Всем":
            if cache_service:
                recipient_position = cache_service.get_node_position(message.to_node)
                if recipient_position:
                    latitude, longitude, altitude = recipient_position
                    yandex_map_url = (
                        f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=15&l=map"
                    )
                    location_parts.append(
                        f'📍 <a href="{yandex_map_url}">Получатель</a>'
                    )
                else:
                    location_parts.append("📍 Получатель: Не известно")
            else:
                location_parts.append("📍 Получатель: Не известно")

        if location_parts:
            parts.append(" | ".join(location_parts))

        # Текст сообщения
        if message.text:
            escaped_text = html.escape(message.text)
            parts.append(
                f"\n💬 <b>Сообщение:</b>\n<blockquote>{escaped_text}</blockquote>"
            )

        if not parts:
            parts.append("📨 Новое сообщение Meshtastic")
            if message.topic:
                escaped_topic = html.escape(message.topic)
                parts.append(f"Топик: {escaped_topic}")

        return "\n".join(parts)

