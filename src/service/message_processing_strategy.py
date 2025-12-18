"""
Стратегии обработки сообщений (Strategy Pattern).

Различные режимы работы бота:
- PRIVATE: только личные сообщения
- GROUP: групповой чат (с опцией личных)
- ALL: все пакеты (включая не-текстовые)
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, TYPE_CHECKING, Any
from enum import Enum

from src.domain.message import MeshtasticMessage
from src.repo.telegram_repository import TelegramRepository
from src.service.topic_routing_service import RoutingMode

if TYPE_CHECKING:
    from src.service.node_cache_service import NodeCacheService
    from src.service.message_grouping_service import MessageGroupingService

logger = logging.getLogger(__name__)


class ProcessingMode(str, Enum):
    """Режимы обработки сообщений."""

    PRIVATE = "private"  # Только личные сообщения
    GROUP = "group"  # Групповой чат (с опцией личных)
    ALL = "all"  # Все пакеты (включая не-текстовые)


class MessageProcessingStrategy(ABC):
    """Базовый класс для стратегий обработки сообщений."""

    def __init__(
        self,
        node_cache_service: Optional["NodeCacheService"] = None,
        grouping_service: Optional["MessageGroupingService"] = None,
        telegram_config: Optional[Any] = None,
    ):
        """
        Инициализирует стратегию.

        Args:
            node_cache_service: Сервис кэша нод
            grouping_service: Сервис группировки сообщений
            telegram_config: Конфигурация Telegram
        """
        self.node_cache_service = node_cache_service
        self.grouping_service = grouping_service
        self.telegram_config = telegram_config

    @abstractmethod
    async def should_process(self, message: MeshtasticMessage) -> bool:
        """
        Определяет, нужно ли обрабатывать сообщение.

        Args:
            message: Сообщение для проверки

        Returns:
            True, если сообщение нужно обработать
        """
        pass

    @abstractmethod
    async def process_message(
        self,
        message: MeshtasticMessage,
        telegram_repo: TelegramRepository,
        topic: str,
        tg_id: Optional[int] = None,
        notify_user_ids: Optional[List[int]] = None,
    ) -> None:
        """
        Обрабатывает сообщение согласно стратегии.

        Args:
            message: Сообщение для обработки
            telegram_repo: Репозиторий Telegram
            topic: MQTT топик сообщения
            tg_id: Telegram ID пользователя (если известен)
            notify_user_ids: Список user_id для уведомлений
        """
        pass


class PrivateModeStrategy(MessageProcessingStrategy):
    """Конфиденциальный режим: только личные сообщения."""

    async def should_process(self, message: MeshtasticMessage) -> bool:
        """Обрабатываем только текстовые сообщения."""
        return message.message_type == "text"

    async def process_message(
        self,
        message: MeshtasticMessage,
        telegram_repo: TelegramRepository,
        topic: str,
        tg_id: Optional[int] = None,
        notify_user_ids: Optional[List[int]] = None,
    ) -> None:
        """
        Отправляет сообщение только в личный чат с пользователем.

        Args:
            message: Сообщение для обработки
            telegram_repo: Репозиторий Telegram
            topic: MQTT топик сообщения
            tg_id: Telegram ID пользователя (обязательно для этого режима)
            notify_user_ids: Игнорируется в этом режиме
        """
        if not tg_id:
            logger.warning(
                f"PRIVATE режим требует tg_id, но он не указан. Топик: {topic}"
            )
            return

        if not telegram_repo.is_user_allowed(tg_id):
            logger.warning(
                f"Пользователь {tg_id} не разрешен для получения сообщений"
            )
            return

        # Форматируем сообщение
        telegram_text = message.format_for_telegram(
            node_cache_service=self.node_cache_service
        )

        # Отправляем только указанному пользователю
        try:
            await telegram_repo.send_to_user(tg_id, telegram_text)
            logger.info(
                f"Отправлено личное сообщение пользователю {tg_id} (режим PRIVATE)"
            )
        except Exception as e:
            logger.error(
                f"Ошибка при отправке личного сообщения пользователю {tg_id}: {e}",
                exc_info=True,
            )


class GroupModeStrategy(MessageProcessingStrategy):
    """Общий режим: групповой чат + опционально личные сообщения."""

    def __init__(
        self,
        send_to_users: bool = False,
        node_cache_service: Optional["NodeCacheService"] = None,
        grouping_service: Optional["MessageGroupingService"] = None,
        telegram_config: Optional[Any] = None,
    ):
        """
        Создает стратегию группового режима.

        Args:
            send_to_users: Отправлять ли также личные сообщения
            node_cache_service: Сервис кэша нод
            grouping_service: Сервис группировки сообщений
            telegram_config: Конфигурация Telegram
        """
        super().__init__(node_cache_service, grouping_service, telegram_config)
        self.send_to_users = send_to_users

    async def should_process(self, message: MeshtasticMessage) -> bool:
        """Обрабатываем только текстовые сообщения."""
        return message.message_type == "text"

    async def process_message(
        self,
        message: MeshtasticMessage,
        telegram_repo: TelegramRepository,
        topic: str,
        tg_id: Optional[int] = None,
        notify_user_ids: Optional[List[int]] = None,
    ) -> None:
        """
        Отправляет сообщение в групповой чат и опционально пользователям.

        Args:
            message: Сообщение для обработки
            telegram_repo: Репозиторий Telegram
            topic: MQTT топик сообщения
            tg_id: Telegram ID пользователя (опционально)
            notify_user_ids: Список user_id для уведомлений
        """
        # Извлекаем ноду-получателя из топика
        receiver_node_id = None
        topic_parts = topic.split("/")
        if len(topic_parts) >= 4:
            potential_node_id = topic_parts[-1]
            if potential_node_id.startswith("!"):
                receiver_node_id = potential_node_id

        # Обработка группировки сообщений
        if (
            self.grouping_service
            and self.telegram_config
            and self.telegram_config.message_grouping_enabled
            and message.message_id
        ):
            # Добавляем ноду-получателя в группу
            node_added = self.grouping_service.add_received_node(
                message_id=message.message_id,
                message=message,
                receiver_node_id=receiver_node_id,
                node_cache_service=self.node_cache_service,
            )

            group = self.grouping_service.get_group(message.message_id)
            if group:
                # Проверяем, есть ли уже telegram_message_id
                if group.telegram_message_id is None:
                    # Первое сообщение - отправляем новое
                    received_by_nodes = [
                        {
                            "node_id": node.node_id,
                            "node_name": node.node_name,
                            "node_short": node.node_short,
                            "received_at": node.received_at,
                            "rssi": node.rssi,
                            "snr": node.snr,
                            "hops_away": node.hops_away,
                            "sender_node": node.sender_node,
                            "sender_node_name": node.sender_node_name,
                        }
                        for node in group.get_unique_nodes()
                    ]

                    telegram_text = message.format_for_telegram_with_grouping(
                        received_by_nodes=received_by_nodes,
                        show_receive_time=self.telegram_config.show_receive_time,
                        node_cache_service=self.node_cache_service,
                    )

                    try:
                        telegram_message_id = await telegram_repo.send_to_group(
                            telegram_text
                        )
                        if telegram_message_id:
                            group.telegram_message_id = telegram_message_id
                            logger.info(
                                f"Отправлено новое группированное сообщение: message_id={message.message_id}, telegram_message_id={telegram_message_id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Ошибка при отправке группированного сообщения: {e}",
                            exc_info=True,
                        )
                elif node_added and self.grouping_service.is_grouping_active(
                    message.message_id
                ):
                    # Обновляем существующее сообщение
                    received_by_nodes = [
                        {
                            "node_id": node.node_id,
                            "node_name": node.node_name,
                            "node_short": node.node_short,
                            "received_at": node.received_at,
                            "rssi": node.rssi,
                            "snr": node.snr,
                            "hops_away": node.hops_away,
                            "sender_node": node.sender_node,
                            "sender_node_name": node.sender_node_name,
                        }
                        for node in group.get_unique_nodes()
                    ]

                    telegram_text = message.format_for_telegram_with_grouping(
                        received_by_nodes=received_by_nodes,
                        show_receive_time=self.telegram_config.show_receive_time,
                        node_cache_service=self.node_cache_service,
                    )

                    try:
                        await telegram_repo.edit_group_message(
                            group.telegram_message_id, telegram_text
                        )
                        logger.info(
                            f"Обновлено группированное сообщение: message_id={message.message_id}, telegram_message_id={group.telegram_message_id}, нод: {len(received_by_nodes)}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Ошибка при редактировании группированного сообщения: {e}",
                            exc_info=True,
                        )

            # Очищаем истекшие группы
            self.grouping_service.cleanup_expired_groups()
        else:
            # Обычная отправка без группировки
            telegram_text = message.format_for_telegram(
                node_cache_service=self.node_cache_service
            )

            # Отправляем в групповой чат
            try:
                await telegram_repo.send_to_group(telegram_text)
                logger.info("Отправлено сообщение в групповой чат (режим GROUP)")
            except Exception as e:
                logger.error(
                    f"Ошибка при отправке в групповой чат: {e}", exc_info=True
                )

        # Опционально отправляем пользователям (без группировки для личных сообщений)
        if self.send_to_users and notify_user_ids:
            telegram_text = message.format_for_telegram(
                node_cache_service=self.node_cache_service
            )
            for user_id in notify_user_ids:
                if telegram_repo.is_user_allowed(user_id):
                    try:
                        await telegram_repo.send_to_user(user_id, telegram_text)
                        logger.debug(
                            f"Отправлено сообщение пользователю {user_id} (режим GROUP)"
                        )
                    except Exception as e:
                        logger.error(
                            f"Ошибка при отправке пользователю {user_id}: {e}",
                            exc_info=True,
                        )


class AllModeStrategy(MessageProcessingStrategy):
    """Режим ALL: все пакеты (включая не-текстовые)."""

    async def should_process(self, message: MeshtasticMessage) -> bool:
        """Обрабатываем все типы сообщений."""
        return True

    async def process_message(
        self,
        message: MeshtasticMessage,
        telegram_repo: TelegramRepository,
        topic: str,
        tg_id: Optional[int] = None,
        notify_user_ids: Optional[List[int]] = None,
    ) -> None:
        """
        Отправляет сообщения в группу и пользователям.
        
        В группу отправляются только текстовые сообщения.
        Служебные сообщения (nodeinfo, position, telemetry и т.д.) отправляются только в личные чаты пользователей.

        Args:
            message: Сообщение для обработки
            telegram_repo: Репозиторий Telegram
            topic: MQTT топик сообщения
            tg_id: Telegram ID пользователя (опционально)
            notify_user_ids: Список user_id для уведомлений
        """
        # Для текстовых - обычное форматирование
        if message.message_type == "text":
            telegram_text = message.format_for_telegram(
                node_cache_service=self.node_cache_service
            )
            
            # Текстовые сообщения отправляем в группу
            try:
                await telegram_repo.send_to_group(telegram_text)
                logger.info(
                    f"Отправлено текстовое сообщение в группу (режим ALL)"
                )
            except Exception as e:
                logger.error(
                    f"Ошибка при отправке в группу: {e}", exc_info=True
                )
        else:
            # Для служебных сообщений - специальное форматирование
            telegram_text = self._format_non_text_message(message)
            # Служебные сообщения НЕ отправляем в группу

        # Отправляем пользователям (и текстовые, и служебные)
        if notify_user_ids:
            for user_id in notify_user_ids:
                if telegram_repo.is_user_allowed(user_id):
                    try:
                        await telegram_repo.send_to_user(user_id, telegram_text)
                        logger.debug(
                            f"Отправлено сообщение типа {message.message_type} пользователю {user_id} (режим ALL)"
                        )
                    except Exception as e:
                        logger.error(
                            f"Ошибка при отправке пользователю {user_id}: {e}",
                            exc_info=True,
                        )

    def _format_non_text_message(self, message: MeshtasticMessage) -> str:
        """
        Форматирует не-текстовые сообщения.

        Args:
            message: Сообщение для форматирования

        Returns:
            Отформатированный текст для Telegram
        """
        import html
        from datetime import datetime

        parts = []

        # Заголовок с типом сообщения
        message_type_names = {
            "nodeinfo": "📋 Информация о ноде",
            "position": "📍 Позиция",
            "telemetry": "📊 Телеметрия",
            "routing": "🔄 Маршрутизация",
            "admin": "⚙️ Админ",
            "paxcounter": "👥 Счетчик людей",
            "waypoint": "🗺️ Точка маршрута",
            "audio": "🎵 Аудио",
            "ip_tunnel": "🌐 IP туннель",
        }

        type_name = message_type_names.get(
            message.message_type, f"📦 {message.message_type}"
        )
        parts.append(f"<b>{type_name}</b>")

        # Временная метка
        if message.timestamp:
            try:
                dt = datetime.fromtimestamp(message.timestamp)
                parts.append(f"🕐 {dt.strftime('%H:%M %d.%m.%Y')}")
            except (ValueError, OSError):
                pass

        # Информация об отправителе
        if message.from_node:
            sender_info = []
            if message.from_node_name and message.from_node_short:
                escaped_name = html.escape(message.from_node_name)
                escaped_short = html.escape(message.from_node_short)
                sender_info.append(f"{escaped_name} ({escaped_short})")
            elif message.from_node_name:
                sender_info.append(html.escape(message.from_node_name))
            elif message.from_node_short:
                sender_info.append(html.escape(message.from_node_short))
            else:
                sender_info.append(html.escape(message.from_node))

            if sender_info:
                parts.append(f"📡 От: {' '.join(sender_info)}")

        # Дополнительная информация в зависимости от типа
        if message.message_type == "position" and self.node_cache_service:
            position = self.node_cache_service.get_node_position(message.from_node)
            if position:
                latitude, longitude, altitude = position
                yandex_map_url = (
                    f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=15&l=map"
                )
                parts.append(
                    f'📍 <a href="{yandex_map_url}">Показать на карте</a>'
                )

        return "\n".join(parts) if parts else f"📦 Сообщение типа: {message.message_type}"

