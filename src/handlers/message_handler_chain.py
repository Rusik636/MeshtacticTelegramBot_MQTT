"""
Цепочка обработчиков сообщений (Chain of Responsibility Pattern).

Позволяет легко добавлять новые обработчики без изменения существующего кода.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HandlerConfig:
    """Конфигурация обработчика."""

    enabled: bool = True
    priority: int = 0  # Порядок выполнения (меньше = раньше)


class MessageHandler(ABC):
    """Базовый класс для обработчиков сообщений."""

    def __init__(self, config: Optional[HandlerConfig] = None):
        """
        Инициализирует обработчик.

        Args:
            config: Конфигурация обработчика
        """
        self.config = config or HandlerConfig()
        self._next_handler: Optional["MessageHandler"] = None

    def set_next(self, handler: "MessageHandler") -> "MessageHandler":
        """
        Устанавливает следующий обработчик в цепочке.

        Args:
            handler: Следующий обработчик

        Returns:
            Установленный обработчик (для цепочки вызовов)
        """
        self._next_handler = handler
        return handler

    async def handle(self, topic: str, payload: bytes) -> None:
        """
        Обрабатывает сообщение и передает следующему обработчику.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах
        """
        if self.config.enabled:
            try:
                await self._process(topic, payload)
            except Exception as e:
                logger.error(
                    f"Ошибка в обработчике {self.__class__.__name__}: {e}",
                    exc_info=True,
                )

        if self._next_handler:
            await self._next_handler.handle(topic, payload)

    @abstractmethod
    async def _process(self, topic: str, payload: bytes) -> None:
        """
        Реализуется в наследниках - здесь основная логика обработки.

        Args:
            topic: MQTT топик сообщения
            payload: Данные сообщения в байтах
        """
        pass

