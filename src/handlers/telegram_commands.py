"""
Обработчики команд Telegram бота.

Обрабатывает команды, отправленные пользователями в личном чате с ботом.
"""
import asyncio
import logging
from typing import Optional
from telebot import types
from telebot.async_telebot import AsyncTeleBot

from src.repo.telegram_repository import TelegramRepository
from src.service.mqtt_proxy_service import MQTTProxyService


logger = logging.getLogger(__name__)


class TelegramCommandsHandler:
    """
    Обработчик команд Telegram бота.
    
    Обрабатывает команды в личном чате с ботом.
    """
    
    def __init__(
        self,
        bot: AsyncTeleBot,
        telegram_repo: TelegramRepository,
        proxy_service: Optional[MQTTProxyService] = None
    ):
        """
        Инициализирует обработчик команд.
        
        Args:
            bot: Экземпляр Telegram бота
            telegram_repo: Репозиторий для работы с Telegram
            proxy_service: Сервис MQTT прокси (опционально)
        """
        self.bot = bot
        self.telegram_repo = telegram_repo
        self.proxy_service = proxy_service
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        """Регистрирует обработчики команд."""
        # Команда /start
        @self.bot.message_handler(commands=['start'])
        async def handle_start(message: types.Message):
            await self._handle_start(message)
        
        # Команда /help
        @self.bot.message_handler(commands=['help'])
        async def handle_help(message: types.Message):
            await self._handle_help(message)
        
        # Команда /status
        @self.bot.message_handler(commands=['status'])
        async def handle_status(message: types.Message):
            await self._handle_status(message)
        
        # Команда /info
        @self.bot.message_handler(commands=['info'])
        async def handle_info(message: types.Message):
            await self._handle_info(message)
        
        # Команда /get_chat_id
        @self.bot.message_handler(commands=['get_chat_id'])
        async def handle_get_chat_id(message: types.Message):
            await self._handle_get_chat_id(message)
        
        # Обработка всех остальных сообщений
        @self.bot.message_handler(func=lambda m: True)
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
                "Обратитесь к администратору для получения доступа."
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
        welcome_text = (
            f"👋 Привет, {user.first_name or 'пользователь'}!\n\n"
            "🤖 Я бот для работы с Meshtastic через MQTT.\n\n"
            "📡 Я получаю сообщения от Meshtastic через MQTT брокер "
            "и публикую их в Telegram.\n\n"
            "📋 Доступные команды:\n"
            "/help - показать справку\n"
            "/status - показать статус бота\n"
            "/info - показать информацию о конфигурации"
        )
        
        await self.bot.reply_to(message, welcome_text)
        logger.info(f"Обработана команда /start, user_id={user.id}")
    
    async def _handle_help(self, message: types.Message) -> None:
        """Обрабатывает команду /help."""
        if not await self._check_user_allowed(message):
            return
        
        help_text = (
            "📚 Справка по командам бота:\n\n"
            "/start - начать работу с ботом\n"
            "/help - показать эту справку\n"
            "/status - показать статус подключений\n"
            "/info - показать информацию о конфигурации\n"
            "/get_chat_id - получить ID текущего чата\n\n"
            "ℹ️ Бот автоматически пересылает сообщения от Meshtastic "
            "в настроенные Telegram чаты и MQTT брокеры."
        )
        
        await self.bot.reply_to(message, help_text)
        logger.info(f"Обработана команда /help, user_id={message.from_user.id}")
    
    async def _handle_status(self, message: types.Message) -> None:
        """Обрабатывает команду /status."""
        if not await self._check_user_allowed(message):
            return
        
        status_parts = ["📊 Статус бота:\n"]
        
        # Статус группового чата
        if self.telegram_repo.config.group_chat_id:
            status_parts.append("✅ Групповой чат настроен")
        else:
            status_parts.append("❌ Групповой чат не настроен")
        
        # Статус MQTT прокси
        if self.proxy_service:
            targets_count = len(self.proxy_service._targets)
            if targets_count > 0:
                status_parts.append(f"✅ MQTT прокси: {targets_count} целей настроено")
            else:
                status_parts.append("❌ MQTT прокси: цели не настроены")
        else:
            status_parts.append("ℹ️ MQTT прокси: не инициализирован")
        
        # Статус пользователя
        user_id = message.from_user.id
        if self.telegram_repo.is_user_allowed(user_id):
            status_parts.append("✅ Ваш доступ: разрешен")
        else:
            status_parts.append("❌ Ваш доступ: запрещен")
        
        status_text = "\n".join(status_parts)
        await self.bot.reply_to(message, status_text)
        logger.info(f"Обработана команда /status, user_id={user_id}")
    
    async def _handle_info(self, message: types.Message) -> None:
        """Обрабатывает команду /info."""
        if not await self._check_user_allowed(message):
            return
        
        info_parts = ["ℹ️ Информация о конфигурации:\n"]
        
        # Информация о групповом чате
        if self.telegram_repo.config.group_chat_id:
            info_parts.append(f" group_chat_id: {self.telegram_repo.config.group_chat_id}")
        else:
            info_parts.append(" group_chat_id: не настроен")
        
        # Информация о разрешенных пользователях
        allowed_users = self.telegram_repo.config.allowed_user_ids
        if allowed_users:
            users_str = ", ".join(str(uid) for uid in allowed_users)
            info_parts.append(f"👥 Разрешенные пользователи: {users_str}")
        else:
            info_parts.append("👥 Разрешенные пользователи: все")
        
        # Информация о MQTT прокси
        if self.proxy_service:
            targets = self.proxy_service._targets
            if targets:
                info_parts.append(f"🔗 MQTT прокси целей: {len(targets)}")
                for target in targets:
                    status = "✅" if target._connected else "❌"
                    info_parts.append(
                        f"  {status} {target.config.name}: "
                        f"{target.config.host}:{target.config.port}"
                    )
            else:
                info_parts.append("🔗 MQTT прокси: цели не настроены")
        
        info_text = "\n".join(info_parts)
        await self.bot.reply_to(message, info_text)
        logger.info(f"Обработана команда /info, user_id={message.from_user.id}")
    
    async def _handle_get_chat_id(self, message: types.Message) -> None:
        """Обрабатывает команду /get_chat_id для получения ID чата."""
        if not await self._check_user_allowed(message):
            return
        
        chat = message.chat
        chat_info_parts = ["📋 Информация о чате:\n"]
        
        # Тип чата
        chat_type_emoji = {
            "private": "👤",
            "group": "👥",
            "supergroup": "👥",
            "channel": "📢"
        }
        chat_type = chat.type
        emoji = chat_type_emoji.get(chat_type, "❓")
        chat_info_parts.append(f"{emoji} Тип чата: {chat_type}")
        
        # ID чата
        chat_info_parts.append(f"🆔 Chat ID: `{chat.id}`")
        
        # Название чата (если есть)
        if chat.title:
            chat_info_parts.append(f"📝 Название: {chat.title}")
        
        # Username (если есть)
        if chat.username:
            chat_info_parts.append(f"🔗 Username: @{chat.username}")
        
        # Инструкция
        if chat_type in ("group", "supergroup"):
            chat_info_parts.append("\n💡 Для использования этого чата в боте:")
            chat_info_parts.append(f"Добавьте в .env файл:")
            chat_info_parts.append(f"`TELEGRAM_GROUP_CHAT_ID={chat.id}`")
        
        chat_info_text = "\n".join(chat_info_parts)
        await self.bot.reply_to(message, chat_info_text, parse_mode="Markdown")
        logger.info(f"Обработана команда /get_chat_id, chat_id={chat.id}, user_id={message.from_user.id}")
    
    async def _handle_unknown(self, message: types.Message) -> None:
        """Обрабатывает неизвестные сообщения."""
        if not await self._check_user_allowed(message):
            return
        
        # Игнорируем сообщения в группах (обрабатываем только личные чаты)
        if message.chat.type != "private":
            return
        
        reply_text = (
            "❓ Неизвестная команда.\n\n"
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
            # Используем только необходимые параметры без non_stop (передается автоматически)
            await self.bot.infinity_polling(timeout=20, skip_pending=True, request_timeout=30)
        except asyncio.CancelledError:
            logger.info("Telegram polling отменен")
            raise
        except Exception as e:
            logger.error(f"Ошибка в Telegram polling: {e}", exc_info=True)
            raise

