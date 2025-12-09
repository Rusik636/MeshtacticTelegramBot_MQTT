"""
Сервис для кэширования информации о нодах Meshtastic.

Хранит информацию о нодах в оперативной памяти и на диске.
Обновляет информацию при получении пакетов типа nodeinfo.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class NodeInfo:
    """Информация о ноде Meshtastic."""
    
    def __init__(
        self,
        node_id: str,
        longname: Optional[str] = None,
        shortname: Optional[str] = None,
        last_updated: Optional[datetime] = None
    ):
        """
        Инициализирует информацию о ноде.
        
        Args:
            node_id: ID ноды (например, !698535e0)
            longname: Полное название ноды
            shortname: Короткое имя ноды
            last_updated: Время последнего обновления
        """
        self.node_id = node_id
        self.longname = longname
        self.shortname = shortname
        self.last_updated = last_updated or datetime.utcnow()
    
    def to_dict(self) -> Dict:
        """Преобразует в словарь для сериализации."""
        return {
            "node_id": self.node_id,
            "longname": self.longname,
            "shortname": self.shortname,
            "last_updated": self.last_updated.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "NodeInfo":
        """Создает из словаря."""
        last_updated = None
        if data.get("last_updated"):
            try:
                last_updated = datetime.fromisoformat(data["last_updated"])
            except (ValueError, TypeError):
                last_updated = datetime.utcnow()
        
        return cls(
            node_id=data["node_id"],
            longname=data.get("longname"),
            shortname=data.get("shortname"),
            last_updated=last_updated
        )


class NodeCacheService:
    """
    Сервис для управления кэшем информации о нодах.
    
    Хранит информацию в оперативной памяти и на диске.
    Обновляет информацию раз в 3 дня.
    """
    
    def __init__(self, cache_file: str = "data/nodes_cache.json"):
        """
        Инициализирует сервис кэша нод.
        
        Args:
            cache_file: Путь к файлу кэша на диске
        """
        self.cache_file = Path(cache_file)
        self._cache: Dict[str, NodeInfo] = {}
        self.update_interval_days = 3
        
        # Создаем директорию для кэша, если не существует
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Загружаем кэш с диска при инициализации
        self.load_cache()
    
    def load_cache(self) -> None:
        """Загружает кэш нод с диска."""
        if not self.cache_file.exists():
            logger.info(f"Файл кэша не найден: {self.cache_file}. Создадим новый при первом обновлении.")
            return
        
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for node_data in data.get("nodes", []):
                try:
                    node_info = NodeInfo.from_dict(node_data)
                    self._cache[node_info.node_id] = node_info
                except (KeyError, ValueError) as e:
                    logger.warning(f"Ошибка при загрузке информации о ноде: {e}")
                    continue
            
            logger.info(f"Загружено {len(self._cache)} нод из кэша")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка при загрузке кэша нод: {e}", exc_info=True)
    
    def save_cache(self) -> None:
        """Сохраняет кэш нод на диск."""
        try:
            data = {
                "nodes": [node.to_dict() for node in self._cache.values()],
                "last_saved": datetime.utcnow().isoformat()
            }
            
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Сохранено {len(self._cache)} нод в кэш")
        except IOError as e:
            logger.error(f"Ошибка при сохранении кэша нод: {e}", exc_info=True)
    
    def get_node_info(self, node_id: str) -> Optional[NodeInfo]:
        """
        Получает информацию о ноде из кэша.
        
        Args:
            node_id: ID ноды (например, !698535e0)
            
        Returns:
            Информация о ноде или None, если не найдена
        """
        return self._cache.get(node_id)
    
    def update_node_info(
        self,
        node_id: str,
        longname: Optional[str] = None,
        shortname: Optional[str] = None,
        force: bool = False
    ) -> bool:
        """
        Обновляет информацию о ноде в кэше.
        
        Обновляет только если прошло более 3 дней с последнего обновления,
        или если force=True.
        
        Args:
            node_id: ID ноды (например, !698535e0)
            longname: Полное название ноды
            shortname: Короткое имя ноды
            force: Принудительное обновление (игнорирует интервал)
            
        Returns:
            True, если информация была обновлена, False если пропущена
        """
        existing_node = self._cache.get(node_id)
        
        # Проверяем, нужно ли обновлять
        if existing_node and not force:
            time_since_update = datetime.utcnow() - existing_node.last_updated
            if time_since_update < timedelta(days=self.update_interval_days):
                logger.debug(
                    f"Пропущено обновление ноды {node_id}: "
                    f"последнее обновление {time_since_update.days} дней назад"
                )
                return False
        
        # Обновляем или создаем новую запись
        if existing_node:
            # Обновляем существующую запись
            if longname:
                existing_node.longname = longname
            if shortname:
                existing_node.shortname = shortname
            existing_node.last_updated = datetime.utcnow()
            logger.info(f"Обновлена информация о ноде: {node_id} ({longname or shortname or 'без имени'})")
        else:
            # Создаем новую запись
            new_node = NodeInfo(
                node_id=node_id,
                longname=longname,
                shortname=shortname,
                last_updated=datetime.utcnow()
            )
            self._cache[node_id] = new_node
            logger.info(f"Добавлена новая нода в кэш: {node_id} ({longname or shortname or 'без имени'})")
        
        # Сохраняем на диск
        self.save_cache()
        return True
    
    def get_node_name(self, node_id: str) -> Optional[str]:
        """
        Получает название ноды из кэша (приоритет: longname > shortname).
        
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
        Получает короткое имя ноды из кэша.
        
        Args:
            node_id: ID ноды
            
        Returns:
            Короткое имя ноды или None
        """
        node_info = self.get_node_info(node_id)
        if node_info:
            return node_info.shortname
        return None

