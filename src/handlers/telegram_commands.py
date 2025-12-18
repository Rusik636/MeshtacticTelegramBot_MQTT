"""
Обработчики команд Telegram бота.

Обрабатывает команды, отправленные пользователями в личном чате с ботом.
Разделяет логику основного брокера и прокси.
"""

import asyncio
import logging
from typing import Optional
from telebot import types
from telebot.async_telebot import AsyncTeleBot

from src.repo.telegram_repository import TelegramRepository
from src.handlers.proxy_status_handler import ProxyStatusHandler
from src.service.topic_routing_service import TopicRoutingService, RoutingMode


logger = logging.getLogger(__name__)


class TelegramCommandsHandler:
    """Обрабатывает команды бота в личном чате."""

    def __init__(
        self,
        bot: AsyncTeleBot,
        telegram_repo: TelegramRepository,
        proxy_status_handler: Optional[ProxyStatusHandler] = None,
        topic_routing_service: Optional[TopicRoutingService] = None,
    ):
        """
        Регистрирует обработчики команд.

        Args:
            bot: Экземпляр Telegram бота
            telegram_repo: Репозиторий для работы с Telegram
            proxy_status_handler: Обработчик статуса прокси (опционально)
            topic_routing_service: Сервис роутинга по топикам (опционально)
        """
        self.bot = bot
        self.telegram_repo = telegram_repo
        self.proxy_status_handler = proxy_status_handler
        self.topic_routing_service = topic_routing_service
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Регистрирует обработчики команд."""

        # Команда /start
        @self.bot.message_handler(commands=["start"])
        async def handle_start(message: types.Message):
            await self._handle_start(message)

        # Команда /help
        @self.bot.message_handler(commands=["help"])
        async def handle_help(message: types.Message):
            await self._handle_help(message)

        # Команда /status
        @self.bot.message_handler(commands=["status"])
        async def handle_status(message: types.Message):
            await self._handle_status(message)

        # Команда /info
        @self.bot.message_handler(commands=["info"])
        async def handle_info(message: types.Message):
            await self._handle_info(message)

        # Команда /get_chat_id
        @self.bot.message_handler(commands=["get_chat_id"])
        async def handle_get_chat_id(message: types.Message):
            await self._handle_get_chat_id(message)

        # Команда /get_topic_id
        @self.bot.message_handler(commands=["get_topic_id"])
        async def handle_get_topic_id(message: types.Message):
            await self._handle_get_topic_id(message)

        # Команда /mode
        @self.bot.message_handler(commands=["mode"])
        async def handle_mode(message: types.Message):
            await self._handle_mode(message)

        # Команда /id
        @self.bot.message_handler(commands=["id"])
        async def handle_id(message: types.Message):
            await self._handle_id(message)

        # Обработка всех остальных сообщений (исключая команды)
        @self.bot.message_handler(
            func=lambda m: m.text is None or not m.text.startswith("/")
        )
        async def handle_unknown(message: types.Message):
            await self._handle_unknown(message)

    async def _check_user_allowed(self, message: types.Message) -> bool:
        """
        Проверяет, разрешен ли пользователь для работы с ботом.

        Args:
            message: Сообщение от пользователя

        Returns:
            True, если пользователь разрешен
        """
        user_id = message.from_user.id

        if not self.telegram_repo.is_user_allowed(user_id):
            await self.bot.reply_to(
                message,
                "❌ У вас нет доступа к этому боту.\n"
                "Обратитесь к администратору для получения доступа.",
            )
            logger.warning(
                f"Попытка использования бота неразрешенным пользователем: user_id={user_id}, "
                f"username={message.from_user.username}"
            )
            return False

        return True

    async def _handle_start(self, message: types.Message) -> None:
        """Обрабатывает команду /start."""
        if not await self._check_user_allowed(message):
            return

        user = message.from_user
        logger.info(
            f"Команда /start от пользователя: user_id={user.id}, "
            f"username=@{user.username if user.username else 'N/A'}, "
            f"first_name={user.first_name or 'N/A'}"
        )

    async def _handle_help(self, message: types.Message) -> None:
        """Обрабатывает команду /help."""
        if not await self._check_user_allowed(message):
            return

        logger.info(
            f"Команда /help от пользователя: user_id={message.from_user.id}, "
            f"username=@{message.from_user.username if message.from_user.username else 'N/A'}"
        )
        help_text = (
            "📋 <b>Доступные команды:</b>\n\n"
            "/start - Начать работу с ботом\n"
            "/help - Показать эту справку\n"
            "/id - Показать ваш Telegram ID\n"
            "/status - Статус бота и подключений\n"
            "/info - Подробная информация о конфигурации\n"
            "/get_chat_id - Получить ID чата\n"
            "/get_topic_id - Получить ID темы форума\n"
            "/mode - Управление режимом обработки сообщений\n\n"
            "Используйте /mode для настройки режима работы бота."
        )
        await self.bot.reply_to(message, help_text, parse_mode="HTML")

    async def _handle_status(self, message: types.Message) -> None:
        """Обрабатывает команду /status."""
        if not await self._check_user_allowed(message):
            return

        user_id = message.from_user.id

        # Формируем информацию о статусе для логов
        status_info = []

        # Статус группового чата
        if self.telegram_repo.config.group_chat_id:
            status_info.append(
                f"Групповой чат: настроен (ID={self.telegram_repo.config.group_chat_id})"
            )
            if self.telegram_repo.config.group_topic_id:
                status_info.append(
                    f"Тема форума: настроена (ID={self.telegram_repo.config.group_topic_id})"
                )
            else:
                status_info.append("Тема форума: не настроена")
        else:
            status_info.append("Групповой чат: не настроен")

        # Статус MQTT прокси (через отдельный обработчик)
        if self.proxy_status_handler:
            proxy_status = self.proxy_status_handler.get_status_info()
            status_info.extend(proxy_status)
        else:
            status_info.append("MQTT прокси: не инициализирован")

        # Статус пользователя
        if self.telegram_repo.is_user_allowed(user_id):
            status_info.append("Доступ пользователя: разрешен")
        else:
            status_info.append("Доступ пользователя: запрещен")

        status_text = " | ".join(status_info)
        logger.info(f"Команда /status от user_id={user_id}: {status_text}")

    async def _handle_info(self, message: types.Message) -> None:
        """Обрабатывает команду /info."""
        if not await self._check_user_allowed(message):
            return

        user_id = message.from_user.id

        # Формируем информацию о конфигурации для логов
        info_parts = []

        # Информация о групповом чате
        if self.telegram_repo.config.group_chat_id:
            info_parts.append(
                f"Групповой чат ID: {self.telegram_repo.config.group_chat_id}"
            )
            if self.telegram_repo.config.group_topic_id:
                info_parts.append(
                    f"Тема форума ID: {self.telegram_repo.config.group_topic_id}"
                )
            else:
                info_parts.append("Тема форума: не настроена")
        else:
            info_parts.append("Групповой чат: не настроен")

        # Информация о разрешенных пользователях
        allowed_users = self.telegram_repo.config.allowed_user_ids
        if allowed_users:
            users_str = ", ".join(str(uid) for uid in allowed_users)
            info_parts.append(f"Разрешенные пользователи: {users_str}")
        else:
            info_parts.append("Разрешенные пользователи: все")

        # Информация о MQTT прокси (через отдельный обработчик)
        if self.proxy_status_handler:
            proxy_info = self.proxy_status_handler.get_detailed_info()
            info_parts.extend(proxy_info)
        else:
            info_parts.append("MQTT прокси: не инициализирован")

        info_text = " | ".join(info_parts)
        logger.info(f"Команда /info от user_id={user_id}: {info_text}")

    async def _handle_get_chat_id(self, message: types.Message) -> None:
        """Обрабатывает команду /get_chat_id для получения ID чата."""
        if not await self._check_user_allowed(message):
            return

        chat = message.chat
        user_id = message.from_user.id

        # Формируем информацию о чате для логов
        chat_info_parts = []
        chat_info_parts.append(f"Тип чата: {chat.type}")
        chat_info_parts.append(f"Chat ID: {chat.id}")

        if chat.title:
            chat_info_parts.append(f"Название: {chat.title}")

        if chat.username:
            chat_info_parts.append(f"Username: @{chat.username}")

        # ID темы (если команда отправлена из темы форума)
        if hasattr(message, "message_thread_id") and message.message_thread_id:
            chat_info_parts.append(f"Topic ID: {message.message_thread_id}")
            logger.info(
                f"Команда /get_chat_id от user_id={user_id} в теме форума: "
                f"chat_id={chat.id}, topic_id={message.message_thread_id}"
            )
            logger.info(
                f"Для настройки добавьте в .env: "
                f"TELEGRAM_GROUP_CHAT_ID={chat.id}, "
                f"TELEGRAM_GROUP_TOPIC_ID={message.message_thread_id}"
            )
        else:
            chat_info_text = " | ".join(chat_info_parts)
            logger.info(f"Команда /get_chat_id от user_id={user_id}: {chat_info_text}")
            if chat.type in ("group", "supergroup"):
                logger.info(
                    f"Для настройки добавьте в .env: TELEGRAM_GROUP_CHAT_ID={chat.id}"
                )

    async def _handle_get_topic_id(self, message: types.Message) -> None:
        """Обрабатывает команду /get_topic_id для получения ID темы форума."""
        if not await self._check_user_allowed(message):
            return

        user_id = message.from_user.id

        # Проверяем, отправлена ли команда из темы форума
        if not hasattr(message, "message_thread_id") or not message.message_thread_id:
            logger.warning(
                f"Команда /get_topic_id от user_id={user_id} отправлена не из темы форума. "
                f"chat_id={message.chat.id}, chat_type={message.chat.type}"
            )
            return

        topic_id = message.message_thread_id
        chat = message.chat

        logger.info(
            f"Команда /get_topic_id от user_id={user_id}: "
            f"chat_id={chat.id}, topic_id={topic_id}, "
            f"chat_title={chat.title or 'N/A'}"
        )
        logger.info(
            f"Для настройки добавьте в .env: "
            f"TELEGRAM_GROUP_CHAT_ID={chat.id}, "
            f"TELEGRAM_GROUP_TOPIC_ID={topic_id}"
        )

    async def _handle_mode(self, message: types.Message) -> None:
        """Обрабатывает команду /mode для управления режимом обработки сообщений."""
        if not await self._check_user_allowed(message):
            return

        if not self.topic_routing_service:
            await self.bot.reply_to(
                message,
                "❌ Сервис роутинга не инициализирован. "
                "Обратитесь к администратору.",
            )
            return

        user_id = message.from_user.id
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []

        if not args:
            # Показываем текущий режим
            current_mode = self.topic_routing_service.get_user_mode(user_id)
            if current_mode:
                mode_name = {
                    RoutingMode.ALL: "Все пакеты",
                    RoutingMode.PRIVATE: "Только личные",
                    RoutingMode.GROUP: "Только группа",
                    RoutingMode.PRIVATE_GROUP: "Личные + группа",
                }.get(current_mode, current_mode.value)
                mode_text = f"Текущий режим: <b>{mode_name}</b> (переопределен)"
            else:
                mode_text = "Текущий режим: <b>по умолчанию</b> (определяется из топика MQTT)"

            help_text = (
                f"{mode_text}\n\n"
                "📋 <b>Доступные режимы:</b>\n\n"
                "/mode all - Все пакеты (включая прокси и все типы сообщений)\n"
                "/mode private - Только личные сообщения в чат с ботом\n"
                "/mode group - Только сообщения в групповой чат\n"
                "/mode both - Личные сообщения + групповой чат\n"
                "/mode reset - Сбросить переопределение (использовать режим из топика)\n\n"
                "💡 <b>Примечание:</b> Режим из топика MQTT имеет приоритет, "
                "если не установлено переопределение через команду.\n\n"
                "📡 <b>Структура топиков:</b>\n"
                "• msh/# - режим ALL\n"
                "• msh/private/{ваш_tg_id}/# - режим PRIVATE\n"
                "• msh/group/# - режим GROUP\n"
                "• msh/private/{ваш_tg_id}/group/# - режим PRIVATE_GROUP"
            )
            await self.bot.reply_to(message, help_text, parse_mode="HTML")
            logger.info(f"Команда /mode (просмотр) от user_id={user_id}")
            return

        mode_str = args[0].lower()
        mode_map = {
            "all": RoutingMode.ALL,
            "private": RoutingMode.PRIVATE,
            "group": RoutingMode.GROUP,
            "both": RoutingMode.PRIVATE_GROUP,
            "reset": None,  # Специальное значение для сброса
        }

        if mode_str not in mode_map:
            await self.bot.reply_to(
                message,
                "❌ Неизвестный режим.\n\n"
                "Используйте: all, private, group, both или reset",
            )
            return

        if mode_str == "reset":
            # Сбрасываем переопределение
            self.topic_routing_service.clear_user_mode(user_id)
            await self.bot.reply_to(
                message,
                "✅ Переопределение режима сброшено.\n\n"
                "Теперь будет использоваться режим из топика MQTT.",
            )
            logger.info(f"Сброшен режим для user_id={user_id}")
        else:
            # Устанавливаем режим
            mode = mode_map[mode_str]
            self.topic_routing_service.set_user_mode(user_id, mode)
            mode_name = {
                RoutingMode.ALL: "Все пакеты",
                RoutingMode.PRIVATE: "Только личные",
                RoutingMode.GROUP: "Только группа",
                RoutingMode.PRIVATE_GROUP: "Личные + группа",
            }.get(mode, mode.value)

            await self.bot.reply_to(
                message,
                f"✅ Режим изменен на: <b>{mode_name}</b>\n\n"
                "Этот режим будет использоваться для всех ваших сообщений, "
                "независимо от топика, в который публикует нода.\n\n"
                "Используйте /mode reset для возврата к режиму из топика.",
                parse_mode="HTML",
            )
            logger.info(f"Установлен режим {mode} для user_id={user_id}")

    async def _handle_id(self, message: types.Message) -> None:
        """Обрабатывает команду /id для отображения Telegram ID пользователя."""
        if not await self._check_user_allowed(message):
            return

        user = message.from_user
        user_id = user.id

        # Формируем информацию о пользователе
        user_info_parts = []
        user_info_parts.append(f"🆔 <b>Ваш Telegram ID:</b> <code>{user_id}</code>")

        if user.username:
            user_info_parts.append(f"👤 <b>Username:</b> @{user.username}")

        if user.first_name:
            user_info_parts.append(f"📝 <b>Имя:</b> {user.first_name}")
            if user.last_name:
                user_info_parts[-1] += f" {user.last_name}"

        user_info_parts.append("")

        # Информация о приватных топиках
        user_info_parts.append(
            "📡 <b>Для приватных топиков используйте:</b>\n"
            f"<code>msh/private/{user_id}/#</code>"
        )

        user_info_parts.append("")

        # Информация о режиме (если установлен)
        if self.topic_routing_service:
            current_mode = self.topic_routing_service.get_user_mode(user_id)
            if current_mode:
                mode_name = {
                    RoutingMode.ALL: "Все пакеты",
                    RoutingMode.PRIVATE: "Только личные",
                    RoutingMode.GROUP: "Только группа",
                    RoutingMode.PRIVATE_GROUP: "Личные + группа",
                }.get(current_mode, current_mode.value)
                user_info_parts.append(
                    f"⚙️ <b>Текущий режим:</b> {mode_name} (переопределен)"
                )
            else:
                user_info_parts.append(
                    "⚙️ <b>Текущий режим:</b> по умолчанию (из топика)"
                )

        user_info_text = "\n".join(user_info_parts)

        await self.bot.reply_to(message, user_info_text, parse_mode="HTML")
        logger.info(
            f"Команда /id от user_id={user_id}, "
            f"username=@{user.username if user.username else 'N/A'}"
        )

    async def _handle_unknown(self, message: types.Message) -> None:
        """Обрабатывает неизвестные сообщения."""
        if not await self._check_user_allowed(message):
            return

        # Игнорируем сообщения в группах (обрабатываем только личные чаты)
        if message.chat.type != "private":
            return

        # Игнорируем команды (они обрабатываются специальными обработчиками)
        if message.text and message.text.startswith("/"):
            # Команда должна была быть обработана специальным обработчиком
            # Если мы здесь, значит команда не распознана, но не будем отвечать,
            # чтобы не дублировать ответы
            logger.debug(
                f"Неизвестная команда от user_id={message.from_user.id}: {message.text}"
            )
            return

        reply_text = (
            "❓ Неизвестное сообщение.\n\n"
            "Используйте /help для просмотра доступных команд."
        )

        await self.bot.reply_to(message, reply_text)
        text_preview = message.text[:50] if message.text else None
        logger.debug(
            f"Обработано неизвестное сообщение: user_id={message.from_user.id}, "
            f"text={text_preview}"
        )

    async def start_polling(self) -> None:
        """
        Запускает polling для получения обновлений от Telegram.

        Обрабатывает отмену задачи для graceful shutdown.
        """
        logger.info("Запуск Telegram polling для обработки команд")
        try:
            # В pyTelegramBotAPI 4.14+ infinity_polling автоматически обрабатывает ошибки
            # Используем только необходимые параметры без non_stop (передается
            # автоматически)
            await self.bot.infinity_polling(
                timeout=20, skip_pending=True, request_timeout=30
            )
        except asyncio.CancelledError:
            logger.info("Telegram polling отменен")
            raise
        except Exception as e:
            logger.error(f"Ошибка в Telegram polling: {e}", exc_info=True)
            raise
