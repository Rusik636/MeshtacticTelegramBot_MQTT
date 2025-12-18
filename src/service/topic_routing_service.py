"""
Сервис для определения режима обработки сообщений по MQTT топику.

Поддерживает гибридный подход:
- Определение режима из структуры топика
- Переопределение режима через настройки пользователя
"""

import logging
import re
from enum import Enum
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


class RoutingMode(str, Enum):
    """Режимы маршрутизации сообщений."""

    ALL = "all"  # Все пакеты (msh/#)
    PRIVATE = "private"  # Только личные (msh/private/{tg_id}/#)
    GROUP = "group"  # Только группа (msh/group/#)
    PRIVATE_GROUP = "private_group"  # Личные + группа (msh/private/{tg_id}/group/#)


class TopicRoutingService:
    """
    Сервис для определения режима обработки по топику.

    Поддерживает паттерны топиков:
    - msh/# - режим ALL (все пакеты)
    - msh/private/{tg_id}/# - режим PRIVATE (только личные)
    - msh/group/# - режим GROUP (только группа)
    - msh/private/{tg_id}/group/# - режим PRIVATE_GROUP (личные + группа)
    """

    def __init__(self, default_mode: RoutingMode = RoutingMode.ALL):
        """
        Создает сервис роутинга.

        Args:
            default_mode: Режим по умолчанию для топиков, которые не соответствуют паттернам
        """
        self.default_mode = default_mode
        self._user_modes: Dict[int, RoutingMode] = {}  # tg_id -> mode (для переопределения)

        # Паттерны топиков (проверяются в порядке приоритета)
        # Более специфичные паттерны должны быть первыми
        self._topic_patterns = [
            (
                RoutingMode.PRIVATE_GROUP,
                re.compile(
                    r"^msh/private/(\d+)/group/(\d+/)?(json|e)/"
                ),  # msh/private/{tg_id}/group/{version}/json/#
            ),
            (
                RoutingMode.PRIVATE,
                re.compile(
                    r"^msh/private/(\d+)/(\d+/)?(json|e)/"
                ),  # msh/private/{tg_id}/{version}/json/#
            ),
            (
                RoutingMode.GROUP,
                re.compile(r"^msh/group/(\d+/)?(json|e)/"),  # msh/group/{version}/json/#
            ),
            (
                RoutingMode.ALL,
                re.compile(r"^msh/(\d+/)?(json|e)/"),  # msh/{version}/json/#
            ),
        ]

    def detect_mode_from_topic(self, topic: str) -> Tuple[RoutingMode, Optional[int]]:
        """
        Определяет режим обработки и tg_id из топика.

        Args:
            topic: MQTT топик сообщения

        Returns:
            Кортеж (режим, tg_id или None)
        """
        # Проверяем паттерны в порядке приоритета (от более специфичных к общим)
        for mode, pattern in self._topic_patterns:
            match = pattern.match(topic)
            if match:
                # Извлекаем tg_id из топика (если есть)
                tg_id = None
                if mode in (RoutingMode.PRIVATE, RoutingMode.PRIVATE_GROUP):
                    tg_id = int(match.group(1))
                logger.debug(
                    f"Определен режим из топика: topic={topic}, mode={mode}, tg_id={tg_id}"
                )
                return mode, tg_id

        # Если не соответствует ни одному паттерну - используем режим по умолчанию
        logger.debug(
            f"Топик не соответствует паттернам, используется режим по умолчанию: topic={topic}, default_mode={self.default_mode}"
        )
        return self.default_mode, None

    def set_user_mode(self, tg_id: int, mode: RoutingMode) -> None:
        """
        Устанавливает режим для конкретного пользователя (переопределяет топик).

        Это позволяет пользователю менять режим через команды бота,
        даже если нода публикует в другой топик.

        Args:
            tg_id: Telegram ID пользователя
            mode: Режим обработки
        """
        self._user_modes[tg_id] = mode
        logger.info(f"Установлен режим для пользователя {tg_id}: {mode}")

    def get_user_mode(self, tg_id: int) -> Optional[RoutingMode]:
        """
        Получает установленный режим для пользователя.

        Args:
            tg_id: Telegram ID пользователя

        Returns:
            Режим обработки или None, если не установлен
        """
        return self._user_modes.get(tg_id)

    def clear_user_mode(self, tg_id: int) -> None:
        """
        Сбрасывает переопределение режима для пользователя.

        После этого будет использоваться режим из топика.

        Args:
            tg_id: Telegram ID пользователя
        """
        if tg_id in self._user_modes:
            del self._user_modes[tg_id]
            logger.info(f"Сброшен режим для пользователя {tg_id}")

    def get_effective_mode(
        self, topic: str, tg_id: Optional[int] = None
    ) -> Tuple[RoutingMode, Optional[int]]:
        """
        Определяет эффективный режим обработки с учетом переопределений.

        Args:
            topic: MQTT топик
            tg_id: Telegram ID пользователя (если известен из сообщения)

        Returns:
            Кортеж (режим, tg_id)
        """
        # Сначала определяем режим из топика
        topic_mode, topic_tg_id = self.detect_mode_from_topic(topic)

        # Используем tg_id из топика, если не передан явно
        effective_tg_id = tg_id or topic_tg_id

        # Проверяем, есть ли переопределение для пользователя
        if effective_tg_id and effective_tg_id in self._user_modes:
            user_mode = self._user_modes[effective_tg_id]
            logger.debug(
                f"Используется переопределенный режим: topic={topic}, "
                f"topic_mode={topic_mode}, user_mode={user_mode}, tg_id={effective_tg_id}"
            )
            return user_mode, effective_tg_id

        logger.debug(
            f"Используется режим из топика: topic={topic}, mode={topic_mode}, tg_id={effective_tg_id}"
        )
        return topic_mode, effective_tg_id

    def get_all_user_modes(self) -> Dict[int, RoutingMode]:
        """
        Возвращает все установленные режимы пользователей.

        Returns:
            Словарь tg_id -> режим
        """
        return self._user_modes.copy()

