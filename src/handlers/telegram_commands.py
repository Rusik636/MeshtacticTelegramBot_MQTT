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
        
        # Команда /get_topic_id
        @self.bot.message_handler(commands=['get_topic_id'])
        async def handle_get_topic_id(message: types.Message):
            await self._handle_get_topic_id(message)
        
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
        logger.info(
            "Доступные команды: /start, /help, /status, /info, /get_chat_id, /get_topic_id"
        )
    
    async def _handle_status(self, message: types.Message) -> None:
        """Обрабатывает команду /status."""
        if not await self._check_user_allowed(message):
            return
        
        user_id = message.from_user.id
        
        # Формируем информацию о статусе для логов
        status_info = []
        
        # Статус группового чата
        if self.telegram_repo.config.group_chat_id:
            status_info.append(f"Групповой чат: настроен (ID={self.telegram_repo.config.group_chat_id})")
            if self.telegram_repo.config.group_topic_id:
                status_info.append(f"Тема форума: настроена (ID={self.telegram_repo.config.group_topic_id})")
            else:
                status_info.append("Тема форума: не настроена")
        else:
            status_info.append("Групповой чат: не настроен")
        
        # Статус MQTT прокси
        if self.proxy_service:
            targets_count = len(self.proxy_service._targets)
            if targets_count > 0:
                connected_count = sum(1 for t in self.proxy_service._targets if t._connected)
                status_info.append(f"MQTT прокси: {targets_count} целей (подключено: {connected_count})")
            else:
                status_info.append("MQTT прокси: цели не настроены")
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
            info_parts.append(f"Групповой чат ID: {self.telegram_repo.config.group_chat_id}")
            if self.telegram_repo.config.group_topic_id:
                info_parts.append(f"Тема форума ID: {self.telegram_repo.config.group_topic_id}")
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
        
        # Информация о MQTT прокси
        if self.proxy_service:
            targets = self.proxy_service._targets
            if targets:
                info_parts.append(f"MQTT прокси целей: {len(targets)}")
                for target in targets:
                    status = "подключен" if target._connected else "не подключен"
                    info_parts.append(
                        f"  - {target.config.name} ({target.config.host}:{target.config.port}): {status}"
                    )
            else:
                info_parts.append("MQTT прокси: цели не настроены")
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
        if hasattr(message, 'message_thread_id') and message.message_thread_id:
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
                logger.info(f"Для настройки добавьте в .env: TELEGRAM_GROUP_CHAT_ID={chat.id}")
    
    async def _handle_get_topic_id(self, message: types.Message) -> None:
        """Обрабатывает команду /get_topic_id для получения ID темы форума."""
        if not await self._check_user_allowed(message):
            return
        
        user_id = message.from_user.id
        
        # Проверяем, отправлена ли команда из темы форума
        if not hasattr(message, 'message_thread_id') or not message.message_thread_id:
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

