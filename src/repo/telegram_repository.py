"""
Репозиторий для работы с Telegram Bot API.

Абстрагирует отправку сообщений в группы и пользователям.
Отвечает только за работу с данными, не за подключение.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, TYPE_CHECKING
from telebot.async_telebot import AsyncTeleBot

from src.config import TelegramConfig

if TYPE_CHECKING:
    from src.infrastructure.telegram_connection import TelegramConnectionManager

logger = logging.getLogger(__name__)


class TelegramRepository(ABC):
    """Абстрактный репозиторий для работы с Telegram."""

    @abstractmethod
    async def send_message(
        self, chat_id: int, text: str, parse_mode: Optional[str] = None
    ) -> None:
        """Отправляет сообщение в чат."""
        ...

    @abstractmethod
    async def send_to_group(self, text: str) -> Optional[int]:
        """
        Отправляет сообщение в групповой чат.

        Returns:
            ID отправленного сообщения в Telegram или None, если отправка не удалась
        """
        ...

    @abstractmethod
    async def send_to_user(self, user_id: int, text: str) -> None:
        """Отправляет сообщение пользователю."""
        ...

    @abstractmethod
    def is_user_allowed(self, user_id: int) -> bool:
        """Проверяет, разрешен ли пользователь."""
        ...

    @abstractmethod
    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: Optional[str] = None,
    ) -> None:
        """Редактирует существующее сообщение в чате."""
        ...


class AsyncTelegramRepository(TelegramRepository):
    """
    Реализация Telegram репозитория через pyTelegramBotAPI.
    
    Отвечает только за работу с данными (отправка/редактирование сообщений).
    Подключение управляется через TelegramConnectionManager.
    """

    def __init__(
        self,
        config: TelegramConfig,
        connection_manager: Optional["TelegramConnectionManager"] = None,
    ):
        """
        Создает репозиторий.

        Args:
            config: Конфигурация Telegram бота
            connection_manager: Менеджер подключения (опционально, создастся автоматически)
        """
        self.config = config
        
        # Используем переданный менеджер или создаем новый
        if connection_manager is None:
            from src.infrastructure.telegram_connection import TelegramConnectionManager
            connection_manager = TelegramConnectionManager(config)
        self.connection_manager = connection_manager
        
        self._allowed_user_ids: Optional[List[int]] = config.allowed_user_ids

    @property
    def bot(self) -> AsyncTeleBot:
        """
        Возвращает экземпляр бота через менеджер подключения.

        Returns:
            Экземпляр AsyncTeleBot
        """
        return self.connection_manager.bot

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = "HTML",
        message_thread_id: Optional[int] = None,
    ) -> None:
        """
        Отправляет сообщение в чат (или в тему, если указан thread_id).

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
                "disable_web_page_preview": True,  # Отключаем предпросмотр ссылок
            }

            # Добавляем message_thread_id только если указан
            if message_thread_id is not None:
                message_params["message_thread_id"] = message_thread_id

            await self.bot.send_message(**message_params)
            if message_thread_id:
                logger.debug(
                    f"Отправлено Telegram сообщение: chat_id={chat_id}, thread_id={message_thread_id}"
                )
            else:
                logger.debug(f"Отправлено Telegram сообщение: chat_id={chat_id}")
        except Exception as e:
            logger.error(
                f"Ошибка при отправке Telegram сообщения: chat_id={chat_id}, thread_id={message_thread_id}, error={e}",
                exc_info=True,
            )
            raise

    async def send_to_group(self, text: str) -> Optional[int]:
        """
        Отправляет сообщение в групповой чат (или в тему, если настроено).

        Args:
            text: Текст сообщения

        Returns:
            ID отправленного сообщения в Telegram или None, если отправка не удалась
        """
        if not self.config.group_chat_id:
            logger.warning("Group chat ID не настроен, пропуск отправки в группу")
            return None

        try:
            message_params = {
                "chat_id": self.config.group_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }

            if self.config.group_topic_id is not None:
                message_params["message_thread_id"] = self.config.group_topic_id

            sent_message = await self.bot.send_message(**message_params)
            message_id = sent_message.message_id if sent_message else None

            if self.config.group_topic_id:
                logger.info(
                    f"Отправлено сообщение в тему группы (thread_id={self.config.group_topic_id}, message_id={message_id})"
                )
            else:
                logger.info(f"Отправлено сообщение в групповой чат (message_id={message_id})")

            return message_id
        except Exception as e:
            logger.error(
                f"Ошибка при отправке сообщения в групповой чат: {e}", exc_info=True
            )
            raise

    async def send_to_user(self, user_id: int, text: str) -> None:
        """Отправляет сообщение пользователю."""
        if not self.is_user_allowed(user_id):
            logger.warning(
                f"Попытка отправить сообщение неразрешенному пользователю: user_id={user_id}"
            )
            return

        try:
            await self.send_message(user_id, text)
            logger.info(f"Отправлено сообщение пользователю: user_id={user_id}")
        except Exception as e:
            logger.error(
                f"Ошибка при отправке сообщения пользователю: user_id={user_id}, error={e}",
                exc_info=True,
            )
            raise

    def is_user_allowed(self, user_id: int) -> bool:
        """
        Проверяет, разрешен ли пользователь (или все разрешены, если список пуст).

        Args:
            user_id: ID пользователя

        Returns:
            True, если пользователь разрешен или список разрешенных не задан
        """
        if self._allowed_user_ids is None:
            return True
        return user_id in self._allowed_user_ids

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: Optional[str] = "HTML",
    ) -> None:
        """
        Редактирует существующее сообщение в чате.

        Args:
            chat_id: ID чата
            message_id: ID сообщения для редактирования
            text: Новый текст сообщения
            parse_mode: Режим парсинга (HTML, Markdown и т.д.). По умолчанию HTML.
        """
        try:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
            )
            logger.debug(
                f"Отредактировано Telegram сообщение: chat_id={chat_id}, message_id={message_id}"
            )
        except Exception as e:
            logger.error(
                f"Ошибка при редактировании Telegram сообщения: chat_id={chat_id}, message_id={message_id}, error={e}",
                exc_info=True,
            )
            raise

    async def edit_group_message(
        self,
        message_id: int,
        text: str,
        parse_mode: Optional[str] = "HTML",
    ) -> None:
        """
        Редактирует сообщение в групповом чате (или в теме, если настроено).

        Args:
            message_id: ID сообщения для редактирования
            text: Новый текст сообщения
            parse_mode: Режим парсинга (HTML, Markdown и т.д.). По умолчанию HTML.
        """
        if not self.config.group_chat_id:
            logger.warning("Group chat ID не настроен, пропуск редактирования сообщения")
            return

        try:
            await self.edit_message(
                self.config.group_chat_id,
                message_id,
                text,
                parse_mode,
            )
            logger.info(f"Отредактировано сообщение в групповом чате: message_id={message_id}")
        except Exception as e:
            logger.error(
                f"Ошибка при редактировании сообщения в групповом чате: {e}",
                exc_info=True,
            )
            raise
