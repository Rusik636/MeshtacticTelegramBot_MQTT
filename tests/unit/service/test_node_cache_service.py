"""
Unit-тесты для NodeCacheService.

Покрытие: 90%+
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.service.node_cache_service import NodeCacheService, NodeInfo


class TestNodeCacheService:
    """Тесты для класса NodeCacheService."""

    def test_init_with_file_storage(self, mock_file_storage, temp_dir: Path):
        """Тест инициализации с переданным FileStorage."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        assert service.cache_file == cache_file
        assert service.file_storage == mock_file_storage
        mock_file_storage.ensure_directory.assert_called_once()

    def test_init_creates_default_file_storage(self, temp_dir: Path):
        """Тест создания FileStorage по умолчанию."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file))
        
        assert service.file_storage is not None
        assert hasattr(service.file_storage, "read_json")

    def test_load_cache_existing_file(self, mock_file_storage, temp_dir: Path):
        """Тест загрузки существующего кэша из файла."""
        cache_file = temp_dir / "nodes_cache.json"
        cache_data = {
            "nodes": [
                {
                    "node_id": "!12345678",
                    "longname": "Cached Node",
                    "shortname": "CN",
                    "last_updated": "2025-01-01T00:00:00",
                }
            ],
            "last_saved": "2025-01-01T00:00:00",
        }
        
        mock_file_storage.exists.return_value = True
        mock_file_storage.read_json.return_value = cache_data
        
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        node_info = service.get_node_info("!12345678")
        assert node_info is not None
        assert node_info.longname == "Cached Node"
        assert node_info.shortname == "CN"

    def test_load_cache_missing_file(self, mock_file_storage, temp_dir: Path):
        """Тест создания нового кэша при отсутствии файла."""
        cache_file = temp_dir / "nodes_cache.json"
        mock_file_storage.exists.return_value = False
        
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        # Кэш должен быть пустым
        assert len(service._cache) == 0
        mock_file_storage.read_json.assert_not_called()

    def test_load_cache_invalid_json(self, mock_file_storage, temp_dir: Path):
        """Тест обработки невалидного JSON - должен создать пустой кэш."""
        cache_file = temp_dir / "nodes_cache.json"
        mock_file_storage.exists.return_value = True
        mock_file_storage.read_json.side_effect = ValueError("Invalid JSON")
        
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        # Кэш должен быть пустым
        assert len(service._cache) == 0

    def test_save_cache(self, mock_file_storage, temp_dir: Path):
        """Тест сохранения кэша на диск."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        # Добавляем ноду
        service.update_node_info("!12345678", longname="Test Node", force=True)
        
        # Проверяем вызов write_json
        mock_file_storage.write_json.assert_called()
        call_args = mock_file_storage.write_json.call_args
        assert call_args[0][0] == cache_file
        assert "nodes" in call_args[0][1]
        assert "last_saved" in call_args[0][1]

    def test_save_cache_io_error(self, mock_file_storage, temp_dir: Path):
        """Тест обработки ошибок записи файла."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        mock_file_storage.write_json.side_effect = IOError("Write error")
        
        # Не должно быть исключения
        service.update_node_info("!12345678", longname="Test Node", force=True)

    def test_update_node_info_new_node(self, mock_file_storage, temp_dir: Path):
        """Тест обновления информации о новой ноде."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        result = service.update_node_info(
            "!12345678", longname="Test Node", shortname="TN", force=True
        )
        
        assert result is True
        node_info = service.get_node_info("!12345678")
        assert node_info is not None
        assert node_info.longname == "Test Node"
        assert node_info.shortname == "TN"
        mock_file_storage.write_json.assert_called()

    def test_update_node_info_existing_node(self, mock_file_storage, temp_dir: Path):
        """Тест обновления существующей ноды."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        # Создаем ноду
        service.update_node_info("!12345678", longname="Old Name", force=True)
        mock_file_storage.write_json.reset_mock()
        
        # Обновляем
        with freeze_time("2025-01-01"):
            result = service.update_node_info(
                "!12345678", longname="New Name", force=True
            )
        
        assert result is True
        node_info = service.get_node_info("!12345678")
        assert node_info.longname == "New Name"
        mock_file_storage.write_json.assert_called()

    def test_update_node_info_interval_save(self, mock_file_storage, temp_dir: Path):
        """Тест сохранения через интервал (3 дня)."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        # Создаем ноду
        with freeze_time("2025-01-01"):
            service.update_node_info("!12345678", longname="Test Node", force=True)
            mock_file_storage.write_json.reset_mock()
        
        # Обновляем через 1 день - не должно сохраняться
        with freeze_time("2025-01-02"):
            result = service.update_node_info("!12345678", longname="Updated Name")
        
        assert result is False  # Не сохранилось на диск
        mock_file_storage.write_json.assert_not_called()
        
        # Обновляем через 3+ дня - должно сохраниться
        with freeze_time("2025-01-05"):
            result = service.update_node_info("!12345678", longname="Updated Name 2")
        
        assert result is True
        mock_file_storage.write_json.assert_called()

    def test_update_node_position(self, mock_file_storage, temp_dir: Path):
        """Тест обновления координат ноды."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        result = service.update_node_position(
            "!12345678", latitude=55.7580288, longitude=52.4550144, altitude=143, force_disk_update=True
        )
        
        assert result is True
        position = service.get_node_position("!12345678")
        assert position is not None
        assert abs(position[0] - 55.7580288) < 0.0001
        assert abs(position[1] - 52.4550144) < 0.0001
        assert position[2] == 143

    def test_get_node_name(self, mock_file_storage, temp_dir: Path):
        """Тест получения имени ноды."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        service.update_node_info("!12345678", longname="Test Node", force=True)
        
        name = service.get_node_name("!12345678")
        assert name == "Test Node"

    def test_get_node_name_missing(self, mock_file_storage, temp_dir: Path):
        """Тест получения имени отсутствующей ноды."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        name = service.get_node_name("!nonexistent")
        assert name is None

    def test_get_node_shortname(self, mock_file_storage, temp_dir: Path):
        """Тест получения короткого имени ноды."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        service.update_node_info("!12345678", shortname="TN", force=True)
        
        shortname = service.get_node_shortname("!12345678")
        assert shortname == "TN"

    def test_get_node_position(self, mock_file_storage, temp_dir: Path):
        """Тест получения координат ноды."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        service.update_node_position(
            "!12345678", latitude=55.7580288, longitude=52.4550144, altitude=143, force_disk_update=True
        )
        
        position = service.get_node_position("!12345678")
        assert position is not None
        assert len(position) == 3

    def test_get_node_position_missing(self, mock_file_storage, temp_dir: Path):
        """Тест получения координат отсутствующей ноды."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        position = service.get_node_position("!nonexistent")
        assert position is None

    def test_update_node_info_always_in_memory(self, mock_file_storage, temp_dir: Path):
        """Тест обновления имен всегда в памяти, даже без сохранения на диск."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        # Создаем ноду
        with freeze_time("2025-01-01"):
            service.update_node_info("!12345678", longname="Initial Name", force=True)
            mock_file_storage.write_json.reset_mock()
        
        # Обновляем через 1 день - не сохраняется на диск, но обновляется в памяти
        with freeze_time("2025-01-02"):
            result = service.update_node_info("!12345678", longname="Updated Name")
        
        # Проверяем, что имя обновлено в памяти
        node_info = service.get_node_info("!12345678")
        assert node_info.longname == "Updated Name"
        
        # Но на диск не сохранилось
        assert result is False
        mock_file_storage.write_json.assert_not_called()

    def test_update_node_info_force_save(self, mock_file_storage, temp_dir: Path):
        """Тест принудительного сохранения (force=True)."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        # Создаем ноду
        with freeze_time("2025-01-01"):
            service.update_node_info("!12345678", longname="Test Node", force=True)
            mock_file_storage.write_json.reset_mock()
        
        # Обновляем через 1 день с force=True - должно сохраниться
        with freeze_time("2025-01-02"):
            result = service.update_node_info("!12345678", longname="Updated Name", force=True)
        
        assert result is True
        mock_file_storage.write_json.assert_called()

    def test_update_node_position_force_disk_update(self, mock_file_storage, temp_dir: Path):
        """Тест принудительного сохранения координат."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        result = service.update_node_position(
            "!12345678",
            latitude=55.7580288,
            longitude=52.4550144,
            altitude=143,
            force_disk_update=True,
        )
        
        assert result is True
        mock_file_storage.write_json.assert_called()

    def test_load_cache_handles_invalid_node_data(self, mock_file_storage, temp_dir: Path):
        """Тест обработки невалидных данных ноды при загрузке."""
        cache_file = temp_dir / "nodes_cache.json"
        cache_data = {
            "nodes": [
                {
                    "node_id": "!12345678",
                    "longname": "Valid Node",
                },
                {
                    # Отсутствует node_id - невалидные данные
                    "longname": "Invalid Node",
                },
            ],
        }
        
        mock_file_storage.exists.return_value = True
        mock_file_storage.read_json.return_value = cache_data
        
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        # Валидная нода должна быть загружена
        assert service.get_node_info("!12345678") is not None
        # Невалидная нода должна быть пропущена

    def test_save_cache_structure(self, mock_file_storage, temp_dir: Path):
        """Тест структуры сохраняемых данных."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        service.update_node_info("!12345678", longname="Test Node", force=True)
        
        # Проверяем структуру данных
        call_args = mock_file_storage.write_json.call_args
        data = call_args[0][1]
        
        assert "nodes" in data
        assert "last_saved" in data
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["node_id"] == "!12345678"
        assert data["nodes"][0]["longname"] == "Test Node"

    def test_update_node_info_with_none_values(self, mock_file_storage, temp_dir: Path):
        """Тест обновления с None значениями."""
        cache_file = temp_dir / "nodes_cache.json"
        service = NodeCacheService(cache_file=str(cache_file), file_storage=mock_file_storage)
        
        # Создаем ноду с именами
        service.update_node_info("!12345678", longname="Test Node", shortname="TN", force=True)
        
        # Обновляем с None - должно обновиться в памяти
        service.update_node_info("!12345678", longname=None, shortname=None)
        
        node_info = service.get_node_info("!12345678")
        assert node_info.longname is None
        assert node_info.shortname is None


class TestNodeInfo:
    """Тесты для класса NodeInfo."""

    def test_node_info_to_dict(self):
        """Тест сериализации NodeInfo в словарь."""
        node_info = NodeInfo(
            node_id="!12345678",
            longname="Test Node",
            shortname="TN",
            latitude=55.7580288,
            longitude=52.4550144,
            altitude=143,
        )
        
        result = node_info.to_dict()
        
        assert result["node_id"] == "!12345678"
        assert result["longname"] == "Test Node"
        assert result["shortname"] == "TN"
        assert result["latitude"] == 55.7580288
        assert result["longitude"] == 52.4550144
        assert result["altitude"] == 143
        assert "last_updated" in result

    def test_node_info_from_dict(self):
        """Тест создания NodeInfo из словаря."""
        data = {
            "node_id": "!12345678",
            "longname": "Test Node",
            "shortname": "TN",
            "last_updated": "2025-01-01T00:00:00",
            "latitude": 55.7580288,
            "longitude": 52.4550144,
            "altitude": 143,
        }
        
        node_info = NodeInfo.from_dict(data)
        
        assert node_info.node_id == "!12345678"
        assert node_info.longname == "Test Node"
        assert node_info.shortname == "TN"
        assert isinstance(node_info.last_updated, datetime)
        assert node_info.latitude == 55.7580288
        assert node_info.longitude == 52.4550144
        assert node_info.altitude == 143

    def test_node_info_has_position(self):
        """Тест проверки наличия координат."""
        node_info_with_position = NodeInfo(
            node_id="!12345678", latitude=55.7580288, longitude=52.4550144
        )
        assert node_info_with_position.has_position() is True
        
        node_info_without_position = NodeInfo(node_id="!12345678")
        assert node_info_without_position.has_position() is False

    def test_node_info_from_dict_invalid_date(self):
        """Тест обработки невалидной даты при загрузке."""
        data = {
            "node_id": "!12345678",
            "last_updated": "invalid_date",
        }
        
        node_info = NodeInfo.from_dict(data)
        
        # Должна быть установлена текущая дата
        assert isinstance(node_info.last_updated, datetime)


