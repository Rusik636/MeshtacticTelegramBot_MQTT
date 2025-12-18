"""
Реестр обработчиков (Registry Pattern).

Позволяет легко регистрировать и создавать обработчики по имени.
"""

import logging
from typing import Dict, Type, Optional, List

from src.handlers.message_handler_chain import MessageHandler, HandlerConfig

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """Реестр обработчиков для легкого добавления новых."""

    def __init__(self):
        """Создает пустой реестр."""
        self._handlers: Dict[str, Type[MessageHandler]] = {}
        self._default_configs: Dict[str, HandlerConfig] = {}

    def register(
        self,
        name: str,
        handler_class: Type[MessageHandler],
        default_config: Optional[HandlerConfig] = None,
    ) -> None:
        """
        Регистрирует новый обработчик.

        Args:
            name: Имя обработчика
            handler_class: Класс обработчика
            default_config: Конфигурация по умолчанию
        """
        self._handlers[name] = handler_class
        self._default_configs[name] = default_config or HandlerConfig()
        logger.debug(f"Зарегистрирован обработчик: {name}")

    def create_handler(
        self,
        name: str,
        config: Optional[HandlerConfig] = None,
        **kwargs,
    ) -> MessageHandler:
        """
        Создает обработчик по имени.

        Args:
            name: Имя обработчика
            config: Конфигурация (если не указана, используется по умолчанию)
            **kwargs: Дополнительные параметры для конструктора обработчика

        Returns:
            Созданный обработчик

        Raises:
            ValueError: Если обработчик не зарегистрирован
        """
        handler_class = self._handlers.get(name)
        if not handler_class:
            raise ValueError(f"Handler '{name}' not registered")

        handler_config = config or self._default_configs[name]
        return handler_class(config=handler_config, **kwargs)

    def list_handlers(self) -> List[str]:
        """
        Возвращает список зарегистрированных обработчиков.

        Returns:
            Список имен обработчиков
        """
        return list(self._handlers.keys())

    def is_registered(self, name: str) -> bool:
        """
        Проверяет, зарегистрирован ли обработчик.

        Args:
            name: Имя обработчика

        Returns:
            True, если обработчик зарегистрирован
        """
        return name in self._handlers


# Глобальный реестр
registry = HandlerRegistry()

