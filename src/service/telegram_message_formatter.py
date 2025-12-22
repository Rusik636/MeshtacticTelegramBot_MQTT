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

        # Валидация: RSSI должен быть отрицательным числом (или 0 считается некорректным)
        # Типичный диапазон для LoRa: от -150 до 0 dBm
        if rssi >= 0:
            return "⚪"  # Некорректное значение (положительное или 0)
        if rssi < -150:
            return "⚪"  # Некорректное значение (слишком большое отрицательное)

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
        - 🟢 Отличный: >= 10 dB
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

        # Валидация: SNR для LoRa обычно в диапазоне от -20 до 30 dB
        # Значения вне этого диапазона считаются некорректными
        if snr < -20 or snr > 30:
            return "⚪"  # Некорректное значение (вне физических пределов)

        if snr >= 10:
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
        # Показываем только валидные значения (игнорируем None, 0, некорректные)
        signal_parts = []
        if message.rssi is not None and message.rssi < 0:
            rssi_emoji = self.get_rssi_quality_emoji(message.rssi)
            # Показываем только если эмодзи не "Неизвестно" (некорректные значения)
            if rssi_emoji != "⚪":
                signal_parts.append(f"{rssi_emoji} RSSI: {message.rssi} dBm")

        if message.snr is not None:
            snr_emoji = self.get_snr_quality_emoji(message.snr)
            # Показываем только если эмодзи не "Неизвестно" (некорректные значения)
            if snr_emoji != "⚪":
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

        # Добавляем информацию о нодах-получателях с деревом маршрутизации
        if received_by_nodes:
            parts.append("\n📥 <b>Получено нодами:</b>\n")

            # Группируем ноды по sender_node для построения дерева
            routing_tree = self._build_routing_tree(
                message.from_node, received_by_nodes, cache_service
            )

            # Отображаем каждую ноду-получателя с информацией о маршрутизации
            for node_info in received_by_nodes:
                node_parts = []
                node_parts.append("  • ")

                # Имя ноды-получателя
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

                # Количество хопов
                hops_away = node_info.get("hops_away")
                if hops_away is not None:
                    node_parts.append(f" 🔄 Хопов: {hops_away}")
                else:
                    node_parts.append(" 🔄 Хопов: 0")

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

                # Информация о sender_node (от кого получено)
                sender_node = node_info.get("sender_node")
                sender_node_name = node_info.get("sender_node_name")
                sender_node_short = node_info.get("sender_node_short")
                sender_rssi = node_info.get("sender_rssi")
                sender_snr = node_info.get("sender_snr")

                # Определяем, от кого получено сообщение
                # Если sender_node отсутствует или равен from_node - прямая доставка
                if not sender_node or sender_node == message.from_node:
                    # Прямая доставка от отправителя
                    sender_display_name = None
                    if message.from_node_name and message.from_node_short:
                        sender_display_name = f"{html.escape(message.from_node_name)} ({html.escape(message.from_node_short)})"
                    elif message.from_node_name:
                        sender_display_name = html.escape(message.from_node_name)
                    elif message.from_node_short:
                        sender_display_name = html.escape(message.from_node_short)
                    elif message.from_node:
                        sender_display_name = html.escape(message.from_node)
                    else:
                        sender_display_name = "Отправитель"
                    
                    node_parts.append(f"\n     • ⬆️ {sender_display_name}")
                    
                    # RSSI/SNR от отправителя (если есть)
                    signal_parts = []
                    if sender_rssi is not None and sender_rssi < 0:
                        rssi_emoji = self.get_rssi_quality_emoji(sender_rssi)
                        if rssi_emoji != "⚪":
                            signal_parts.append(f"{rssi_emoji} {sender_rssi} dBm")
                    
                    if sender_snr is not None:
                        snr_emoji = self.get_snr_quality_emoji(sender_snr)
                        if snr_emoji != "⚪":
                            signal_parts.append(f"{snr_emoji} SNR: {sender_snr:.1f} dB")
                    
                    if signal_parts:
                        node_parts.append(f" {' | '.join(signal_parts)}")
                else:
                    # Получено от ретранслятора (sender_node)
                    node_parts.append("\n     • ⬆️ ")
                    
                    # Имя sender_node
                    if sender_node_name and sender_node_short:
                        escaped_sender_name = html.escape(sender_node_name)
                        escaped_sender_short = html.escape(sender_node_short)
                        node_parts.append(f"{escaped_sender_name} ({escaped_sender_short})")
                    elif sender_node_name:
                        node_parts.append(html.escape(sender_node_name))
                    elif sender_node_short:
                        node_parts.append(html.escape(sender_node_short))
                    else:
                        node_parts.append(html.escape(sender_node))

                    # RSSI/SNR от sender_node
                    signal_parts = []
                    if sender_rssi is not None and sender_rssi < 0:
                        rssi_emoji = self.get_rssi_quality_emoji(sender_rssi)
                        if rssi_emoji != "⚪":
                            signal_parts.append(f"{rssi_emoji} {sender_rssi} dBm")
                    
                    if sender_snr is not None:
                        snr_emoji = self.get_snr_quality_emoji(sender_snr)
                        if snr_emoji != "⚪":
                            signal_parts.append(f"{snr_emoji} SNR: {sender_snr:.1f} dB")
                    
                    if signal_parts:
                        node_parts.append(f" {' | '.join(signal_parts)}")

                parts.append("".join(node_parts))

            parts.append("\n")

            # Дерево маршрутизации
            if routing_tree:
                parts.append("<b>Дерево маршрутизации:</b>\n")
                tree_text = self._format_routing_tree(routing_tree, cache_service)
                parts.append(tree_text)
                parts.append("\n")

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

    def _build_routing_tree(
        self,
        from_node: Optional[str],
        received_by_nodes: List[Dict[str, Any]],
        cache_service: Optional["NodeCacheService"],
    ) -> Dict[str, Any]:
        """
        Строит дерево маршрутизации на основе sender_node для каждой ноды-получателя.
        
        Args:
            from_node: ID ноды-отправителя
            received_by_nodes: Список нод-получателей
            cache_service: Сервис кэша нод
            
        Returns:
            Словарь с деревом маршрутизации: {node_id: {children: [...], level: int}}
        """
        if not from_node:
            return {}
        
        # Создаем структуру дерева
        tree: Dict[str, Dict[str, Any]] = {}
        
        # Добавляем корневую ноду (отправитель)
        tree[from_node] = {
            "node_id": from_node,
            "node_name": None,
            "node_short": None,
            "children": [],
            "level": 0,
        }
        
        if cache_service:
            tree[from_node]["node_name"] = cache_service.get_node_name(from_node)
            tree[from_node]["node_short"] = cache_service.get_node_shortname(from_node)
        
        # Группируем ноды-получатели по sender_node
        # sender_node - это нода, от которой получили сообщение
        nodes_by_sender: Dict[str, List[Dict[str, Any]]] = {}
        for node_info in received_by_nodes:
            # Если sender_node отсутствует или равен from_node, значит получили напрямую
            sender = node_info.get("sender_node")
            if not sender or sender == from_node:
                sender = from_node
            # Нормализуем sender_node (убеждаемся, что это строка)
            sender = str(sender) if sender else from_node
            
            if sender not in nodes_by_sender:
                nodes_by_sender[sender] = []
            nodes_by_sender[sender].append(node_info)
        
        # Рекурсивно строим дерево
        def add_to_tree(parent_id: str, level: int, max_level: int = 10):
            """Рекурсивно добавляет ноды в дерево."""
            if level > max_level:
                return
            
            if parent_id not in nodes_by_sender:
                return
            
            for node_info in nodes_by_sender[parent_id]:
                node_id = node_info.get("node_id")
                if not node_id or node_id in tree:
                    continue
                
                # Добавляем ноду в дерево
                tree[node_id] = {
                    "node_id": node_id,
                    "node_name": node_info.get("node_name"),
                    "node_short": node_info.get("node_short"),
                    "children": [],
                    "level": level,
                    "parent_id": parent_id,
                }
                
                # Добавляем в children родителя
                if parent_id in tree:
                    tree[parent_id]["children"].append(node_id)
                
                # Рекурсивно обрабатываем детей этой ноды
                add_to_tree(node_id, level + 1, max_level)
        
        # Начинаем построение дерева от корня
        add_to_tree(from_node, 1)
        
        # Убеждаемся, что все ноды-получатели включены в дерево
        # (на случай, если они не были добавлены из-за отсутствия sender_node или других причин)
        for node_info in received_by_nodes:
            node_id = node_info.get("node_id")
            if node_id and node_id not in tree:
                # Добавляем как дочернюю ноду отправителя
                tree[node_id] = {
                    "node_id": node_id,
                    "node_name": node_info.get("node_name"),
                    "node_short": node_info.get("node_short"),
                    "children": [],
                    "level": 1,
                    "parent_id": from_node,
                }
                if from_node in tree:
                    tree[from_node]["children"].append(node_id)
        
        return tree

    def _format_routing_tree(
        self,
        tree: Dict[str, Dict[str, Any]],
        cache_service: Optional["NodeCacheService"],
    ) -> str:
        """
        Форматирует дерево маршрутизации для отображения в Telegram.
        
        Args:
            tree: Дерево маршрутизации
            cache_service: Сервис кэша нод для получения координат
            
        Returns:
            Отформатированная строка с деревом маршрутизации
        """
        if not tree:
            return ""
        
        parts = []
        
        def format_node(node_id: str, number_prefix: str = "", is_last: bool = True) -> None:
            """Рекурсивно форматирует ноду и её детей с нумерацией."""
            if node_id not in tree:
                return
            
            node = tree[node_id]
            node_name = node.get("node_name")
            node_short = node.get("node_short")
            
            # Формируем имя ноды
            if node_name and node_short:
                display_name = f"{html.escape(node_name)} ({html.escape(node_short)})"
            elif node_name:
                display_name = html.escape(node_name)
            elif node_short:
                display_name = html.escape(node_short)
            else:
                display_name = html.escape(node_id)
            
            # Получаем координаты для ссылки
            position = None
            if cache_service:
                position = cache_service.get_node_position(node_id)
            
            if position:
                latitude, longitude, altitude = position
                yandex_map_url = (
                    f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=15&l=map"
                )
                node_link = f'<a href="{yandex_map_url}">{display_name}</a>'
            else:
                node_link = display_name
            
            # Формируем номер для ноды (1, 1.1, 1.2, 1.2.1 и т.д.)
            if number_prefix:
                node_number = number_prefix
            else:
                node_number = "1"
            
            parts.append(f"📍 {node_number}. {node_link}")
            
            # Обрабатываем детей
            children = node.get("children", [])
            if children:
                for i, child_id in enumerate(children):
                    is_last_child = i == len(children) - 1
                    # Формируем номер для ребенка: parent_number.child_index
                    child_number = f"{node_number}.{i + 1}"
                    format_node(child_id, child_number, is_last_child)
        
        # Находим корневую ноду (level = 0)
        root_nodes = [node_id for node_id, node in tree.items() if node.get("level") == 0]
        if root_nodes:
            format_node(root_nodes[0])
        
        return "\n".join(parts)

