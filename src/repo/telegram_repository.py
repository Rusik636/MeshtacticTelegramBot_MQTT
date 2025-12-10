"""
Интерфейс и реализация репозитория для работы с Telegram.

Использует паттерн Repository для абстракции работы с Telegram Bot API.
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional, List
from telebot.async_telebot import AsyncTeleBot

from src.config import TelegramConfig


logger = logging.getLogger(__name__)


class TelegramRepository(ABC):
    """Абстрактный репозиторий для работы с Telegram."""
    
    @abstractmethod
    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = None
    ) -> None:
        """
        Отправляет сообщение в чат.
        
        Args:
            chat_id: ID чата
            text: Текст сообщения
            parse_mode: Режим парсинга (HTML, Markdown и т.д.)
        """
        ...
    
    @abstractmethod
    async def send_to_group(self, text: str) -> None:
        """
        Отправляет сообщение в групповой чат.
        
        Args:
            text: Текст сообщения
        """
        ...
    
    @abstractmethod
    async def send_to_user(self, user_id: int, text: str) -> None:
        """
        Отправляет сообщение пользователю.
        
        Args:
            user_id: ID пользователя
            text: Текст сообщения
        """
        ...
    
    @abstractmethod
    def is_user_allowed(self, user_id: int) -> bool:
        """
        Проверяет, разрешено ли пользователю получать сообщения.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            True, если пользователь разрешен
        """
        ...


class AsyncTelegramRepository(TelegramRepository):
    """
    Реализация Telegram репозитория на основе pyTelegramBotAPI.
    
    Использует асинхронный клиент для работы с Telegram Bot API.
    """
    
    def __init__(self, config: TelegramConfig):
        """
        Инициализирует репозиторий.
        
        Args:
            config: Конфигурация Telegram бота
        """
        self.config = config
        self.bot = AsyncTeleBot(config.bot_token)
        self._allowed_user_ids: Optional[List[int]] = config.allowed_user_ids
    
    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = "HTML",
        message_thread_id: Optional[int] = None
    ) -> None:
        """
        Отправляет сообщение в чат.
        
        Args:
            chat_id: ID чата
            text: Текст сообщения
            parse_mode: Режим парсинга (HTML, Markdown и т.д.). По умолчанию HTML для поддержки ссылок.
            message_thread_id: ID темы (для форумов). Если None - отправляется в общий чат.
        """
        try:
            message_params = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True  # Отключаем предпросмотр ссылок
            }
            
            # Добавляем message_thread_id только если указан
            if message_thread_id is not None:
                message_params["message_thread_id"] = message_thread_id
            
            await self.bot.send_message(**message_params)
            if message_thread_id:
                logger.debug(f"Отправлено Telegram сообщение: chat_id={chat_id}, thread_id={message_thread_id}")
            else:
                logger.debug(f"Отправлено Telegram сообщение: chat_id={chat_id}")
        except Exception as e:
            logger.error(
                f"Ошибка при отправке Telegram сообщения: chat_id={chat_id}, thread_id={message_thread_id}, error={e}",
                exc_info=True
            )
            raise
    
    async def send_to_group(self, text: str) -> None:
        """
        Отправляет сообщение в групповой чат (или в тему, если настроено).
        
        Args:
            text: Текст сообщения
        """
        if not self.config.group_chat_id:
            logger.warning("Group chat ID не настроен, пропуск отправки в группу")
            return
        
        try:
            await self.send_message(
                self.config.group_chat_id,
                text,
                message_thread_id=self.config.group_topic_id
            )
            if self.config.group_topic_id:
                logger.info(f"Отправлено сообщение в тему группы (thread_id={self.config.group_topic_id})")
            else:
                logger.info("Отправлено сообщение в групповой чат")
        except Exception as e:
            logger.error(
                f"Ошибка при отправке сообщения в групповой чат: {e}",
                exc_info=True
            )
            raise
    
    async def send_to_user(self, user_id: int, text: str) -> None:
        """
        Отправляет сообщение пользователю.
        
        Args:
            user_id: ID пользователя
            text: Текст сообщения
        """
        if not self.is_user_allowed(user_id):
            logger.warning(f"Попытка отправить сообщение неразрешенному пользователю: user_id={user_id}")
            return
        
        try:
            await self.send_message(user_id, text)
            logger.info(f"Отправлено сообщение пользователю: user_id={user_id}")
        except Exception as e:
            logger.error(
                f"Ошибка при отправке сообщения пользователю: user_id={user_id}, error={e}",
                exc_info=True
            )
            raise
    
    def is_user_allowed(self, user_id: int) -> bool:
        """
        Проверяет, разрешено ли пользователю получать сообщения.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            True, если пользователь разрешен или список разрешенных не задан
        """
        if self._allowed_user_ids is None:
            return True
        return user_id in self._allowed_user_ids

