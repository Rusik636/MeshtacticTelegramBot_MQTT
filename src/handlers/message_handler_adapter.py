"""
Адаптер для совместимости новой архитектуры обработчиков с существующим интерфейсом.
"""

import logging
from typing import TYPE_CHECKING

from src.repo.mqtt_repository import MQTTMessageHandler
from src.handlers.message_handler_chain import MessageHandler

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MessageHandlerAdapter(MQTTMessageHandler):
    """
    Адаптер для использования новой цепочки обработчиков с существующим интерфейсом.

    Позволяет использовать MessageHandler chain там, где ожидается MQTTMessageHandler.
    """

    def __init__(self, handler_chain: MessageHandler):
        """
        Создает адаптер.

        Args:
            handler_chain: Цепочка обработчиков
        """
        self.handler_chain = handler_chain

    async def handle_message(self, topic: str, payload: bytes) -> None:
        """
        Обрабатывает сообщение через цепочку обработчиков.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах
        """
        await self.handler_chain.handle(topic, payload)

