"""
Сервис для работы с файловой системой.

Абстракция над файловыми операциями для обеспечения тестируемости и гибкости.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class FileStorage(ABC):
    """Абстрактный интерфейс для работы с файловым хранилищем."""

    @abstractmethod
    def read_json(self, file_path: Path) -> Dict[str, Any]:
        """
        Читает JSON файл.

        Args:
            file_path: Путь к файлу

        Returns:
            Словарь с данными из файла

        Raises:
            FileNotFoundError: Если файл не найден
            json.JSONDecodeError: Если файл невалидный JSON
        """
        pass

    @abstractmethod
    def write_json(self, file_path: Path, data: Dict[str, Any]) -> None:
        """
        Записывает данные в JSON файл.

        Args:
            file_path: Путь к файлу
            data: Данные для записи

        Raises:
            IOError: Если не удалось записать файл
        """
        pass

    @abstractmethod
    def exists(self, file_path: Path) -> bool:
        """
        Проверяет существование файла.

        Args:
            file_path: Путь к файлу

        Returns:
            True, если файл существует
        """
        pass

    @abstractmethod
    def ensure_directory(self, directory_path: Path) -> None:
        """
        Создает директорию, если она не существует.

        Args:
            directory_path: Путь к директории
        """
        pass


class LocalFileStorage(FileStorage):
    """Реализация файлового хранилища для локальной файловой системы."""

    def read_json(self, file_path: Path) -> Dict[str, Any]:
        """
        Читает JSON файл.

        Args:
            file_path: Путь к файлу

        Returns:
            Словарь с данными из файла

        Raises:
            FileNotFoundError: Если файл не найден
            json.JSONDecodeError: Если файл невалидный JSON
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.debug(f"Прочитан JSON файл: {file_path}")
                return data
        except FileNotFoundError:
            logger.warning(f"Файл не найден: {file_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON файла {file_path}: {e}")
            raise

    def write_json(self, file_path: Path, data: Dict[str, Any]) -> None:
        """
        Записывает данные в JSON файл.

        Args:
            file_path: Путь к файлу
            data: Данные для записи

        Raises:
            IOError: Если не удалось записать файл
        """
        try:
            # Создаем директорию, если не существует
            self.ensure_directory(file_path.parent)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                logger.debug(f"Записан JSON файл: {file_path}")
        except IOError as e:
            logger.error(f"Ошибка записи JSON файла {file_path}: {e}")
            raise

    def exists(self, file_path: Path) -> bool:
        """
        Проверяет существование файла.

        Args:
            file_path: Путь к файлу

        Returns:
            True, если файл существует
        """
        return file_path.exists()

    def ensure_directory(self, directory_path: Path) -> None:
        """
        Создает директорию, если она не существует.

        Args:
            directory_path: Путь к директории
        """
        if not directory_path.exists():
            directory_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Создана директория: {directory_path}")

