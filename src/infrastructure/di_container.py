"""
DI-контейнер для управления зависимостями.

Обеспечивает централизованное управление зависимостями и их жизненным циклом.
"""

import logging
from typing import Dict, Any, Optional, Callable, TypeVar, Type
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Lifetime(Enum):
    """Время жизни зависимости."""

    SINGLETON = "singleton"  # Один экземпляр на все приложение
    TRANSIENT = "transient"  # Новый экземпляр при каждом запросе


class DIContainer:
    """
    Простой DI-контейнер для управления зависимостями.
    
    Поддерживает:
    - Регистрацию зависимостей с различными временами жизни
    - Автоматическое разрешение зависимостей
    - Фабрики для создания объектов
    """

    def __init__(self):
        """Создает пустой контейнер."""
        self._singletons: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._lifetimes: Dict[str, Lifetime] = {}
        self._types: Dict[str, Type] = {}

    def register_singleton(
        self,
        key: str,
        instance: Any,
        interface: Optional[Type] = None,
    ) -> None:
        """
        Регистрирует singleton зависимость.

        Args:
            key: Ключ зависимости
            instance: Экземпляр объекта
            interface: Интерфейс/тип (опционально)
        """
        self._singletons[key] = instance
        self._lifetimes[key] = Lifetime.SINGLETON
        if interface:
            self._types[key] = interface
        logger.debug(f"Зарегистрирован singleton: {key}")

    def register_factory(
        self,
        key: str,
        factory: Callable[[], Any],
        lifetime: Lifetime = Lifetime.TRANSIENT,
        interface: Optional[Type] = None,
    ) -> None:
        """
        Регистрирует фабрику для создания зависимости.

        Args:
            key: Ключ зависимости
            factory: Функция-фабрика для создания объекта
            lifetime: Время жизни зависимости
            interface: Интерфейс/тип (опционально)
        """
        self._factories[key] = factory
        self._lifetimes[key] = lifetime
        if interface:
            self._types[key] = interface
        logger.debug(f"Зарегистрирована фабрика: {key} (lifetime={lifetime.value})")

    def register_type(
        self,
        key: str,
        cls: Type[T],
        lifetime: Lifetime = Lifetime.TRANSIENT,
        interface: Optional[Type] = None,
    ) -> None:
        """
        Регистрирует тип для автоматического создания.

        Args:
            key: Ключ зависимости
            cls: Класс для создания
            lifetime: Время жизни зависимости
            interface: Интерфейс/тип (опционально)
        """
        self._factories[key] = lambda: cls()
        self._lifetimes[key] = lifetime
        self._types[key] = cls
        if interface:
            self._types[f"{key}_interface"] = interface
        logger.debug(f"Зарегистрирован тип: {key} (lifetime={lifetime.value})")

    def resolve(self, key: str) -> Any:
        """
        Разрешает зависимость по ключу.

        Args:
            key: Ключ зависимости

        Returns:
            Экземпляр зависимости

        Raises:
            KeyError: Если зависимость не зарегистрирована
        """
        if key in self._singletons:
            return self._singletons[key]

        if key in self._factories:
            factory = self._factories[key]
            lifetime = self._lifetimes.get(key, Lifetime.TRANSIENT)

            if lifetime == Lifetime.SINGLETON:
                # Создаем singleton при первом запросе
                if key not in self._singletons:
                    self._singletons[key] = factory()
                return self._singletons[key]
            else:
                # TRANSIENT - создаем новый экземпляр каждый раз
                return factory()

        raise KeyError(f"Зависимость '{key}' не зарегистрирована")

    def resolve_optional(self, key: str) -> Optional[Any]:
        """
        Разрешает зависимость по ключу, возвращая None если не найдена.

        Args:
            key: Ключ зависимости

        Returns:
            Экземпляр зависимости или None
        """
        try:
            return self.resolve(key)
        except KeyError:
            return None

    def is_registered(self, key: str) -> bool:
        """
        Проверяет, зарегистрирована ли зависимость.

        Args:
            key: Ключ зависимости

        Returns:
            True, если зависимость зарегистрирована
        """
        return key in self._singletons or key in self._factories

    def clear(self) -> None:
        """Очищает все зарегистрированные зависимости."""
        self._singletons.clear()
        self._factories.clear()
        self._lifetimes.clear()
        self._types.clear()
        logger.debug("Контейнер очищен")

