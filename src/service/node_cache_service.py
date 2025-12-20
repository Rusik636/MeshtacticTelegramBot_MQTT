"""
Сервис для кэширования информации о нодах Meshtastic.

Хранит имена и координаты нод в памяти и на диске.
Обновляется при получении nodeinfo и position пакетов.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.file_storage import FileStorage

logger = logging.getLogger(__name__)


class NodeInfo:
    """Информация о ноде Meshtastic."""

    def __init__(
        self,
        node_id: str,
        longname: Optional[str] = None,
        shortname: Optional[str] = None,
        last_updated: Optional[datetime] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        altitude: Optional[int] = None,
        last_position_updated: Optional[datetime] = None,
    ):
        """Создает объект с информацией о ноде."""
        self.node_id = node_id
        self.longname = longname
        self.shortname = shortname
        self.last_updated = last_updated or datetime.utcnow()
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.last_position_updated = last_position_updated

    def to_dict(self) -> Dict:
        """Конвертирует в словарь для сохранения в JSON."""
        result = {
            "node_id": self.node_id,
            "longname": self.longname,
            "shortname": self.shortname,
            "last_updated": self.last_updated.isoformat(),
        }
        if self.latitude is not None:
            result["latitude"] = self.latitude
        if self.longitude is not None:
            result["longitude"] = self.longitude
        if self.altitude is not None:
            result["altitude"] = self.altitude
        if self.last_position_updated:
            result["last_position_updated"] = self.last_position_updated.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> "NodeInfo":
        """Создает объект из словаря (при загрузке из JSON)."""
        last_updated = None
        if data.get("last_updated"):
            try:
                last_updated = datetime.fromisoformat(data["last_updated"])
            except (ValueError, TypeError):
                last_updated = datetime.utcnow()

        last_position_updated = None
        if data.get("last_position_updated"):
            try:
                last_position_updated = datetime.fromisoformat(
                    data["last_position_updated"]
                )
            except (ValueError, TypeError):
                last_position_updated = None

        return cls(
            node_id=data["node_id"],
            longname=data.get("longname"),
            shortname=data.get("shortname"),
            last_updated=last_updated,
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            altitude=data.get("altitude"),
            last_position_updated=last_position_updated,
        )

    def has_position(self) -> bool:
        """Проверяет, есть ли координаты ноды."""
        return self.latitude is not None and self.longitude is not None


class NodeCacheService:
    """Кэш информации о нодах - хранит в памяти и на диске, обновляется раз в 3 дня."""

    def __init__(
        self,
        cache_file: str = "data/nodes_cache.json",
        file_storage: Optional["FileStorage"] = None,
    ):
        """
        Создает сервис кэша и загружает данные с диска.

        Args:
            cache_file: Путь к файлу кэша
            file_storage: Сервис для работы с файловой системой (опционально)
        """
        self.cache_file = Path(cache_file)
        self._cache: Dict[str, NodeInfo] = {}
        
        # Используем переданный FileStorage или создаем LocalFileStorage по умолчанию
        if file_storage is None:
            from src.infrastructure.file_storage import LocalFileStorage
            file_storage = LocalFileStorage()
        self.file_storage = file_storage
        self.update_interval_days = 3

        # Создаем директорию для кэша, если не существует
        self.file_storage.ensure_directory(self.cache_file.parent)

        # Загружаем кэш с диска при инициализации
        self.load_cache()

    def load_cache(self) -> None:
        """Загружает кэш нод с диска."""
        if not self.file_storage.exists(self.cache_file):
            logger.info(
                f"Файл кэша не найден: {self.cache_file}. Создадим новый при первом обновлении."
            )
            return

        try:
            data = self.file_storage.read_json(self.cache_file)

            for node_data in data.get("nodes", []):
                try:
                    node_info = NodeInfo.from_dict(node_data)
                    self._cache[node_info.node_id] = node_info
                except (KeyError, ValueError) as e:
                    logger.warning(f"Ошибка при загрузке информации о ноде: {e}")
                    continue

            logger.info(f"Загружено {len(self._cache)} нод из кэша")
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Ошибка при загрузке кэша нод: {e}", exc_info=True)

    def save_cache(self) -> None:
        """Сохраняет кэш нод на диск."""
        try:
            data = {
                "nodes": [node.to_dict() for node in self._cache.values()],
                "last_saved": datetime.utcnow().isoformat(),
            }

            self.file_storage.write_json(self.cache_file, data)

            logger.debug(f"Сохранено {len(self._cache)} нод в кэш")
        except IOError as e:
            logger.error(f"Ошибка при сохранении кэша нод: {e}", exc_info=True)

    def get_node_info(self, node_id: str) -> Optional[NodeInfo]:
        """Возвращает информацию о ноде из кэша или None."""
        return self._cache.get(node_id)

    def update_node_info(
        self,
        node_id: str,
        longname: Optional[str] = None,
        shortname: Optional[str] = None,
        force: bool = False,
    ) -> bool:
        """
        Обновляет информацию о ноде.
        
        Имена всегда обновляются в памяти (если предоставлены).
        На диск сохраняется только раз в 3 дня (или при force=True).

        Args:
            node_id: ID ноды (например, !698535e0)
            longname: Полное название ноды
            shortname: Короткое имя ноды
            force: Принудительное сохранение на диск (игнорирует интервал)

        Returns:
            True, если информация была обновлена, False если пропущено сохранение на диск
        """
        existing_node = self._cache.get(node_id)

        # Определяем, нужно ли сохранять на диск
        should_save_to_disk = force

        if existing_node and not force:
            time_since_update = datetime.utcnow() - existing_node.last_updated
            if time_since_update >= timedelta(days=self.update_interval_days):
                should_save_to_disk = True
        else:
            # Если ноды еще нет, всегда сохраняем на диск
            should_save_to_disk = True

        # Обновляем или создаем новую запись
        if existing_node:
            # Обновляем существующую запись в памяти
            # Обновляем имена, если они предоставлены (даже если None - это может быть явное удаление)
            if longname is not None:
                existing_node.longname = longname
            if shortname is not None:
                existing_node.shortname = shortname
            
            # Обновляем время последнего обновления только если действительно обновили данные
            if longname is not None or shortname is not None:
                existing_node.last_updated = datetime.utcnow()
                logger.info(
                    f"Обновлена информация о ноде в кэше: {node_id} "
                    f"(longname={longname}, shortname={shortname})"
                )
        else:
            # Создаем новую запись
            new_node = NodeInfo(
                node_id=node_id,
                longname=longname,
                shortname=shortname,
                last_updated=datetime.utcnow(),
            )
            self._cache[node_id] = new_node
            logger.info(
                f"Добавлена новая нода в кэш: {node_id} ({longname or shortname or 'без имени'})"
            )
            should_save_to_disk = True

        # Сохраняем на диск, если нужно
        if should_save_to_disk:
            self.save_cache()
            logger.debug(f"Сохранена информация о ноде на диск: {node_id}")
            return True
        else:
            logger.debug(
                f"Информация о ноде обновлена только в кэше (не сохраняем на диск): {node_id}"
            )
            return False

    def update_node_position(
        self,
        node_id: str,
        latitude: float,
        longitude: float,
        altitude: Optional[int] = None,
        force_disk_update: bool = False,
    ) -> bool:
        """
        Обновляет координаты ноды (всегда в памяти, на диск - раз в 3 дня или при force_disk_update).

        Args:
            node_id: ID ноды (например, !698535e0)
            latitude: Широта (градусы)
            longitude: Долгота (градусы)
            altitude: Высота над уровнем моря (метры, опционально)
            force_disk_update: Принудительное сохранение на диск

        Returns:
            True, если координаты были обновлены, False если пропущено сохранение на диск
        """
        existing_node = self._cache.get(node_id)

        # Определяем, нужно ли сохранять на диск
        should_save_to_disk = force_disk_update

        if existing_node and not force_disk_update:
            if existing_node.last_position_updated:
                time_since_update = (
                    datetime.utcnow() - existing_node.last_position_updated
                )
                if time_since_update >= timedelta(days=self.update_interval_days):
                    should_save_to_disk = True
            else:
                # Если координат еще не было, сохраняем на диск
                should_save_to_disk = True

        # Обновляем или создаем запись
        if existing_node:
            # Обновляем существующую запись
            old_lat = existing_node.latitude
            old_lon = existing_node.longitude
            existing_node.latitude = latitude
            existing_node.longitude = longitude
            if altitude is not None:
                existing_node.altitude = altitude
            existing_node.last_position_updated = datetime.utcnow()

            if old_lat is not None and old_lon is not None:
                logger.info(
                    f"Обновлены координаты ноды в кэше: {node_id} "
                    f"({old_lat:.6f}, {old_lon:.6f}) → ({latitude:.6f}, {longitude:.6f})"
                )
            else:
                logger.info(
                    f"Добавлены координаты ноды в кэш: {node_id} ({latitude:.6f}, {longitude:.6f})"
                )
        else:
            # Создаем новую запись
            new_node = NodeInfo(
                node_id=node_id,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                last_position_updated=datetime.utcnow(),
            )
            self._cache[node_id] = new_node
            logger.info(
                f"Добавлены координаты новой ноды в кэш: {node_id} ({latitude:.6f}, {longitude:.6f})"
            )
            should_save_to_disk = True

        # Сохраняем на диск, если нужно
        if should_save_to_disk:
            self.save_cache()
            logger.info(
                f"Сохранены координаты ноды на диск: {node_id} ({latitude:.6f}, {longitude:.6f})"
            )
            return True
        else:
            logger.debug(
                f"Координаты обновлены только в кэше (не сохраняем на диск): {node_id}"
            )
            return False

    def get_node_position(
        self, node_id: str
    ) -> Optional[tuple[float, float, Optional[int]]]:
        """
        Возвращает координаты ноды из кэша.

        Args:
            node_id: ID ноды

        Returns:
            Кортеж (latitude, longitude, altitude) или None, если координаты не найдены
        """
        node_info = self.get_node_info(node_id)
        if node_info and node_info.has_position():
            return (node_info.latitude, node_info.longitude, node_info.altitude)
        return None

    def get_node_name(self, node_id: str) -> Optional[str]:
        """
        Возвращает название ноды из кэша (приоритет: longname > shortname).

        Args:
            node_id: ID ноды

        Returns:
            Название ноды или None
        """
        node_info = self.get_node_info(node_id)
        if node_info:
            return node_info.longname or node_info.shortname
        return None

    def get_node_shortname(self, node_id: str) -> Optional[str]:
        """
        Возвращает короткое имя ноды из кэша.

        Args:
            node_id: ID ноды

        Returns:
            Короткое имя ноды или None
        """
        node_info = self.get_node_info(node_id)
        if node_info:
            return node_info.shortname
        return None
