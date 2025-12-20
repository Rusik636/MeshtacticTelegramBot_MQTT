"""
Доменная модель сообщения от Meshtastic.

Структурированное представление сообщения, полученного из MQTT.
"""

import html
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.service.node_cache_service import NodeCacheService


class MeshtasticMessage(BaseModel):
    """Модель сообщения от Meshtastic с распарсенными полями."""

    # Исходный топик MQTT
    topic: str = Field(description="MQTT топик, из которого получено сообщение")

    # Исходный payload (JSON) - распарсенные данные для внутренней обработки
    raw_payload: Dict[str, Any] = Field(
        description="Исходный JSON payload (распарсенный)"
    )

    # Исходный payload в сыром виде (bytes) - для проксирования без изменений
    raw_payload_bytes: Optional[bytes] = Field(
        default=None,
        description="Исходный payload в сыром виде (bytes) - как получен от ноды",
    )

    # Время получения
    received_at: datetime = Field(
        default_factory=datetime.utcnow, description="Время получения сообщения"
    )

    # Извлеченные поля из Meshtastic JSON
    message_id: Optional[str] = Field(default=None, description="ID сообщения")
    from_node: Optional[str] = Field(default=None, description="ID отправителя")
    from_node_name: Optional[str] = Field(
        default=None, description="Название ноды отправителя"
    )
    from_node_short: Optional[str] = Field(
        default=None, description="Короткое имя ноды отправителя"
    )
    sender_node: Optional[str] = Field(
        default=None, description="ID ноды, которая ретранслировала сообщение"
    )
    sender_node_name: Optional[str] = Field(
        default=None, description="Название ноды, которая ретранслировала сообщение"
    )
    sender_node_short: Optional[str] = Field(
        default=None, description="Короткое имя ноды, которая ретранслировала сообщение"
    )
    to_node: Optional[str] = Field(default=None, description="ID получателя")
    to_node_name: Optional[str] = Field(
        default=None, description="Название ноды получателя"
    )
    to_node_short: Optional[str] = Field(
        default=None, description="Короткое имя ноды получателя"
    )
    hops_away: Optional[int] = Field(
        default=None, description="Количество ретрансляций (hops)"
    )
    text: Optional[str] = Field(default=None, description="Текст сообщения")
    timestamp: Optional[int] = Field(
        default=None, description="Unix timestamp сообщения"
    )
    rssi: Optional[int] = Field(
        default=None, description="RSSI (Received Signal Strength Indicator) в dBm"
    )
    snr: Optional[float] = Field(
        default=None, description="SNR (Signal-to-Noise Ratio) в dB"
    )
    message_type: Optional[str] = Field(
        default=None, description="Тип сообщения (text, nodeinfo, position и т.д.)"
    )

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

    def format_for_telegram(
        self, node_cache_service: Optional["NodeCacheService"] = None
    ) -> str:
        """
        Форматирует сообщение для отправки в Telegram.

        Поддерживает UTF-8 символы в названиях и тегах нод.
        Отображает качество сигнала с цветными индикаторами.
        Добавляет ссылку на местоположение, если доступно.

        Args:
            node_cache_service: Сервис кэша нод для получения координат (опционально)

        Returns:
            Отформатированная строка сообщения.
        """
        parts = []

        # Временная метка в формате чч:мм дд.мм.гггг (вверху)
        if self.timestamp:
            try:
                dt = datetime.fromtimestamp(self.timestamp)
                # Формат: чч:мм дд.мм.гггг (например: 22:30 09.12.2025)
                parts.append(f"🕐 <b>{dt.strftime('%H:%M %d.%m.%Y')}</b>")
            except (ValueError, OSError):
                pass

        # Формируем информацию об отправителе
        # Экранируем все пользовательские данные для защиты от XSS
        sender_info = []

        if self.from_node_name and self.from_node_short:
            # Если есть и longname и shortname: longname (shortname)
            escaped_longname = html.escape(self.from_node_name)
            escaped_shortname = html.escape(self.from_node_short)
            sender_info.append(f"{escaped_longname} ({escaped_shortname})")
        elif self.from_node_name:
            # Если есть только longname: longname
            sender_info.append(html.escape(self.from_node_name))
        elif self.from_node_short:
            # Если есть только shortname: shortname (без скобок)
            sender_info.append(html.escape(self.from_node_short))
        elif self.from_node:
            # Иначе: hex ID от from
            sender_info.append(html.escape(self.from_node))

        if sender_info:
            # Объединяем информацию об отправителе
            sender_str = " ".join(sender_info)
            parts.append(f"\n📡 <b>От:</b> {sender_str}")

        # Формируем информацию о ретрансляторе (sender)
        # Показываем только если sender отличается от from_node (сообщение было ретранслировано)
        # Сравниваем нормализованные значения (оба уже должны быть в формате "!hex")
        sender_normalized = (
            self.sender_node.lower() if self.sender_node else None
        )
        from_normalized = self.from_node.lower() if self.from_node else None
        if sender_normalized and sender_normalized != from_normalized:
            # Экранируем все пользовательские данные для защиты от XSS
            repeater_info = []

            if self.sender_node_name and self.sender_node_short:
                # Если есть и longname и shortname: longname (shortname)
                escaped_longname = html.escape(self.sender_node_name)
                escaped_shortname = html.escape(self.sender_node_short)
                repeater_info.append(f"{escaped_longname} ({escaped_shortname})")
            elif self.sender_node_name:
                # Если есть только longname: longname
                repeater_info.append(html.escape(self.sender_node_name))
            elif self.sender_node_short:
                # Если есть только shortname: shortname (без скобок)
                repeater_info.append(html.escape(self.sender_node_short))
            else:
                # Иначе: hex ID от sender
                repeater_info.append(html.escape(self.sender_node))

            if repeater_info:
                # Объединяем информацию о ретрансляторе
                repeater_str = " ".join(repeater_info)
                parts.append(f"🔄 <b>Ретранслировал:</b> {repeater_str}")

        # Формируем информацию о получателе
        if self.to_node:
            recipient_info = []
            # Если to_node = "Всем", просто показываем "Всем"
            if self.to_node == "Всем":
                recipient_info.append("Всем")
            else:
                # Получаем информацию о получателе из кэша, если доступен
                if node_cache_service:
                    cached_to_name = node_cache_service.get_node_name(self.to_node)
                    cached_to_short = node_cache_service.get_node_shortname(
                        self.to_node
                    )

                    if cached_to_name:
                        recipient_info.append(html.escape(cached_to_name))
                    elif cached_to_short:
                        recipient_info.append(html.escape(cached_to_short))

                # Добавляем ID получателя
                escaped_to_node = html.escape(self.to_node)
                if recipient_info:
                    recipient_info.append(f"({escaped_to_node})")
                else:
                    recipient_info.append(escaped_to_node)

            if recipient_info:
                recipient_str = " ".join(recipient_info)
                parts.append(f"📨 <b>Кому:</b> {recipient_str}\n")

        # Информация о ретрансляции
        if self.hops_away is not None:
            if self.hops_away == 0:
                parts.append("📬 Прямая доставка")
            else:
                parts.append(f"🔄 Ретранслировано {self.hops_away} раз")

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

        # Местоположение отправителя и получателя (ссылки на Яндекс Карты)
        location_parts = []

        # Местоположение отправителя
        if node_cache_service and self.from_node:
            sender_position = node_cache_service.get_node_position(self.from_node)
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
        if self.to_node and self.to_node != "Всем":
            if node_cache_service:
                recipient_position = node_cache_service.get_node_position(self.to_node)
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
        if self.text:
            escaped_text = html.escape(self.text)
            # Формируем сообщение с цитатой: "💬 Сообщение:\n" + текст в цитате
            parts.append(
                f"\n💬 <b>Сообщение:</b>\n<blockquote>{escaped_text}</blockquote>"
            )

        if not parts:
            # Если не удалось извлечь структурированные данные, показываем raw
            parts.append("📨 Новое сообщение Meshtastic")
            if self.topic:
                # Экранируем топик для защиты от XSS
                escaped_topic = html.escape(self.topic)
                parts.append(f"Топик: {escaped_topic}")

        return "\n".join(parts)

    def format_for_telegram_with_grouping(
        self,
        received_by_nodes: List[Dict[str, Any]],
        show_receive_time: bool = False,
        node_cache_service: Optional["NodeCacheService"] = None,
    ) -> str:
        """
        Форматирует сообщение для отправки в Telegram с учетом группировки нод-получателей.

        Args:
            received_by_nodes: Список словарей с информацией о нодах-получателях
                Каждый словарь должен содержать: node_id, node_name, node_short,
                received_at, rssi, snr, hops_away, sender_node, sender_node_name
            show_receive_time: Показывать ли время получения каждой нодой
            node_cache_service: Сервис кэша нод для получения координат (опционально)

        Returns:
            Отформатированная строка сообщения с информацией о нодах-получателях.
        """
        # Сначала формируем основное сообщение без списка нод
        parts = []

        # Временная метка в формате чч:мм дд.мм.гггг (вверху)
        if self.timestamp:
            try:
                dt = datetime.fromtimestamp(self.timestamp)
                parts.append(f"🕐 <b>{dt.strftime('%H:%M %d.%m.%Y')}</b>")
            except (ValueError, OSError):
                pass

        # Формируем информацию об отправителе
        sender_info = []
        if self.from_node_name and self.from_node_short:
            escaped_longname = html.escape(self.from_node_name)
            escaped_shortname = html.escape(self.from_node_short)
            sender_info.append(f"{escaped_longname} ({escaped_shortname})")
        elif self.from_node_name:
            sender_info.append(html.escape(self.from_node_name))
        elif self.from_node_short:
            sender_info.append(html.escape(self.from_node_short))
        elif self.from_node:
            sender_info.append(html.escape(self.from_node))

        if sender_info:
            sender_str = " ".join(sender_info)
            parts.append(f"\n📡 <b>От:</b> {sender_str}")

        # Формируем информацию о ретрансляторе (sender)
        sender_normalized = (
            self.sender_node.lower() if self.sender_node else None
        )
        from_normalized = self.from_node.lower() if self.from_node else None
        if sender_normalized and sender_normalized != from_normalized:
            repeater_info = []
            if self.sender_node_name and self.sender_node_short:
                escaped_longname = html.escape(self.sender_node_name)
                escaped_shortname = html.escape(self.sender_node_short)
                repeater_info.append(f"{escaped_longname} ({escaped_shortname})")
            elif self.sender_node_name:
                repeater_info.append(html.escape(self.sender_node_name))
            elif self.sender_node_short:
                repeater_info.append(html.escape(self.sender_node_short))
            else:
                repeater_info.append(html.escape(self.sender_node))

            if repeater_info:
                repeater_str = " ".join(repeater_info)
                parts.append(f"🔄 <b>Ретранслировал:</b> {repeater_str}")

        # Формируем информацию о получателе
        if self.to_node:
            recipient_info = []
            if self.to_node == "Всем":
                recipient_info.append("Всем")
            else:
                if node_cache_service:
                    cached_to_name = node_cache_service.get_node_name(self.to_node)
                    cached_to_short = node_cache_service.get_node_shortname(
                        self.to_node
                    )
                    if cached_to_name:
                        recipient_info.append(html.escape(cached_to_name))
                    elif cached_to_short:
                        recipient_info.append(html.escape(cached_to_short))

                escaped_to_node = html.escape(self.to_node)
                if recipient_info:
                    recipient_info.append(f"({escaped_to_node})")
                else:
                    recipient_info.append(escaped_to_node)

            if recipient_info:
                recipient_str = " ".join(recipient_info)
                parts.append(f"📨 <b>Кому:</b> {recipient_str}\n")

        # Информация о ретрансляции
        if self.hops_away is not None:
            if self.hops_away == 0:
                parts.append("📬 Прямая доставка")
            else:
                parts.append(f"🔄 Ретранслировано {self.hops_away} раз")

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
        if node_cache_service and self.from_node:
            sender_position = node_cache_service.get_node_position(self.from_node)
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

        if self.to_node and self.to_node != "Всем":
            if node_cache_service:
                recipient_position = node_cache_service.get_node_position(self.to_node)
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
        if self.text:
            escaped_text = html.escape(self.text)
            parts.append(
                f"\n💬 <b>Сообщение:</b>\n<blockquote>{escaped_text}</blockquote>"
            )

        if not parts:
            parts.append("📨 Новое сообщение Meshtastic")
            if self.topic:
                escaped_topic = html.escape(self.topic)
                parts.append(f"Топик: {escaped_topic}")

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
            "sender_node": self.sender_node,
            "sender_node_name": self.sender_node_name,
            "sender_node_short": self.sender_node_short,
            "to_node": self.to_node,
            "text": self.text,
            "timestamp": self.timestamp,
            "rssi": self.rssi,
            "snr": self.snr,
        }
