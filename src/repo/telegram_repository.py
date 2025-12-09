"""
Интерфейс и реализация репозитория для работы с Telegram.

Использует паттерн Repository для абстракции работы с Telegram Bot API.
"""
from abc import ABC, abstractmethod
from typing import Optional, List
import structlog
from telebot.async_telebot import AsyncTeleBot

from src.config import TelegramConfig


logger = structlog.get_logger()


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
        parse_mode: Optional[str] = None
    ) -> None:
        """
        Отправляет сообщение в чат.
        
        Args:
            chat_id: ID чата
            text: Текст сообщения
            parse_mode: Режим парсинга (HTML, Markdown и т.д.)
        """
        try:
            await self.bot.send_message(chat_id, text, parse_mode=parse_mode)
            logger.debug("Отправлено Telegram сообщение", chat_id=chat_id)
        except Exception as e:
            logger.error(
                "Ошибка при отправке Telegram сообщения",
                chat_id=chat_id,
                error=str(e)
            )
            raise
    
    async def send_to_group(self, text: str) -> None:
        """
        Отправляет сообщение в групповой чат.
        
        Args:
            text: Текст сообщения
        """
        if not self.config.group_chat_id:
            logger.warning("Group chat ID не настроен, пропуск отправки в группу")
            return
        
        try:
            await self.send_message(self.config.group_chat_id, text)
            logger.info("Отправлено сообщение в групповой чат")
        except Exception as e:
            logger.error(
                "Ошибка при отправке сообщения в групповой чат",
                error=str(e)
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
            logger.warning(
                "Попытка отправить сообщение неразрешенному пользователю",
                user_id=user_id
            )
            return
        
        try:
            await self.send_message(user_id, text)
            logger.info("Отправлено сообщение пользователю", user_id=user_id)
        except Exception as e:
            logger.error(
                "Ошибка при отправке сообщения пользователю",
                user_id=user_id,
                error=str(e)
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

