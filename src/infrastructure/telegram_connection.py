"""
Менеджер подключения к Telegram Bot API.

Отвечает только за установку и управление подключением к Telegram.
"""

import logging
from typing import Optional
from telebot.async_telebot import AsyncTeleBot

from src.config import TelegramConfig

logger = logging.getLogger(__name__)


class TelegramConnectionManager:
    """
    Менеджер подключения к Telegram Bot API.
    
    Отвечает только за создание и управление подключением к Telegram.
    Не содержит бизнес-логику работы с сообщениями.
    """

    def __init__(self, config: TelegramConfig):
        """
        Создает менеджер подключения.

        Args:
            config: Конфигурация Telegram бота
        """
        self.config = config
        self._bot: Optional[AsyncTeleBot] = None

    @property
    def bot(self) -> AsyncTeleBot:
        """
        Возвращает экземпляр бота, создавая его при первом обращении.

        Returns:
            Экземпляр AsyncTeleBot
        """
        if self._bot is None:
            self._bot = AsyncTeleBot(self.config.bot_token)
            logger.debug("Создан экземпляр Telegram бота")
        return self._bot

    async def close(self) -> None:
        """Закрывает подключение к Telegram."""
        if self._bot:
            # pyTelegramBotAPI не требует явного закрытия, но можно добавить очистку
            self._bot = None
            logger.debug("Подключение к Telegram закрыто")

