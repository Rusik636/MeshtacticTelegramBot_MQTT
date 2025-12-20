"""
Unit-тесты для DIContainer.

Покрытие: 95%+
"""

import pytest

from src.infrastructure.di_container import DIContainer, Lifetime


class TestDIContainer:
    """Тесты для класса DIContainer."""

    def test_register_singleton(self):
        """Тест регистрации singleton зависимости."""
        container = DIContainer()
        instance = {"key": "value"}
        
        container.register_singleton("test_key", instance)
        
        assert container.is_registered("test_key")
        resolved = container.resolve("test_key")
        assert resolved == instance
        assert resolved is instance  # Тот же объект

    def test_register_singleton_with_interface(self):
        """Тест регистрации singleton с интерфейсом."""
        container = DIContainer()
        instance = {"key": "value"}
        
        container.register_singleton("test_key", instance, interface=dict)
        
        assert container.is_registered("test_key")

    def test_register_factory_singleton(self):
        """Тест регистрации фабрики с SINGLETON lifetime."""
        container = DIContainer()
        factory_calls = []
        
        def factory():
            obj = {"id": len(factory_calls)}
            factory_calls.append(obj)
            return obj
        
        container.register_factory("test_key", factory, lifetime=Lifetime.SINGLETON)
        
        # Первый вызов
        instance1 = container.resolve("test_key")
        assert instance1["id"] == 0
        
        # Второй вызов - должен вернуть тот же объект
        instance2 = container.resolve("test_key")
        assert instance2 is instance1
        assert len(factory_calls) == 1  # Фабрика вызвана только один раз

    def test_register_factory_transient(self):
        """Тест регистрации фабрики с TRANSIENT lifetime."""
        container = DIContainer()
        factory_calls = []
        
        def factory():
            obj = {"id": len(factory_calls)}
            factory_calls.append(obj)
            return obj
        
        container.register_factory("test_key", factory, lifetime=Lifetime.TRANSIENT)
        
        # Первый вызов
        instance1 = container.resolve("test_key")
        assert instance1["id"] == 0
        
        # Второй вызов - должен вернуть новый объект
        instance2 = container.resolve("test_key")
        assert instance2 is not instance1
        assert instance2["id"] == 1
        assert len(factory_calls) == 2  # Фабрика вызвана дважды

    def test_register_type(self):
        """Тест регистрации типа для автоматического создания."""
        container = DIContainer()
        
        class TestClass:
            def __init__(self):
                self.value = "test"
        
        container.register_type("test_key", TestClass, lifetime=Lifetime.TRANSIENT)
        
        instance1 = container.resolve("test_key")
        instance2 = container.resolve("test_key")
        
        assert isinstance(instance1, TestClass)
        assert isinstance(instance2, TestClass)
        assert instance1 is not instance2  # TRANSIENT - разные экземпляры

    def test_register_type_singleton(self):
        """Тест регистрации типа с SINGLETON lifetime."""
        container = DIContainer()
        
        class TestClass:
            def __init__(self):
                self.value = "test"
        
        container.register_type("test_key", TestClass, lifetime=Lifetime.SINGLETON)
        
        instance1 = container.resolve("test_key")
        instance2 = container.resolve("test_key")
        
        assert instance1 is instance2  # SINGLETON - один экземпляр

    def test_resolve_singleton(self):
        """Тест разрешения singleton зависимости."""
        container = DIContainer()
        instance = [1, 2, 3]
        container.register_singleton("test_key", instance)
        
        result1 = container.resolve("test_key")
        result2 = container.resolve("test_key")
        
        assert result1 == instance
        assert result2 == instance
        assert result1 is result2  # Тот же объект

    def test_resolve_factory_singleton(self):
        """Тест разрешения factory с SINGLETON lifetime."""
        container = DIContainer()
        call_count = 0
        
        def factory():
            nonlocal call_count
            call_count += 1
            return {"id": call_count}
        
        container.register_factory("test_key", factory, lifetime=Lifetime.SINGLETON)
        
        result1 = container.resolve("test_key")
        result2 = container.resolve("test_key")
        
        assert result1 is result2
        assert call_count == 1  # Фабрика вызвана только один раз

    def test_resolve_factory_transient(self):
        """Тест разрешения factory с TRANSIENT lifetime."""
        container = DIContainer()
        call_count = 0
        
        def factory():
            nonlocal call_count
            call_count += 1
            return {"id": call_count}
        
        container.register_factory("test_key", factory, lifetime=Lifetime.TRANSIENT)
        
        result1 = container.resolve("test_key")
        result2 = container.resolve("test_key")
        
        assert result1 is not result2
        assert result1["id"] == 1
        assert result2["id"] == 2
        assert call_count == 2  # Фабрика вызвана дважды

    def test_resolve_key_error(self):
        """Тест ошибки при разрешении несуществующей зависимости."""
        container = DIContainer()
        
        with pytest.raises(KeyError, match="не зарегистрирована"):
            container.resolve("non_existent_key")

    def test_resolve_optional_existing(self):
        """Тест resolve_optional для существующей зависимости."""
        container = DIContainer()
        instance = "test_value"
        container.register_singleton("test_key", instance)
        
        result = container.resolve_optional("test_key")
        
        assert result == instance

    def test_resolve_optional_missing(self):
        """Тест resolve_optional для отсутствующей зависимости."""
        container = DIContainer()
        
        result = container.resolve_optional("non_existent_key")
        
        assert result is None

    def test_is_registered_true(self):
        """Тест проверки регистрации существующей зависимости."""
        container = DIContainer()
        container.register_singleton("test_key", "value")
        
        assert container.is_registered("test_key") is True

    def test_is_registered_false(self):
        """Тест проверки регистрации несуществующей зависимости."""
        container = DIContainer()
        
        assert container.is_registered("non_existent_key") is False

    def test_clear(self):
        """Тест очистки всех зависимостей."""
        container = DIContainer()
        container.register_singleton("key1", "value1")
        container.register_singleton("key2", "value2")
        
        assert container.is_registered("key1")
        assert container.is_registered("key2")
        
        container.clear()
        
        assert not container.is_registered("key1")
        assert not container.is_registered("key2")

    def test_clear_empty_container(self):
        """Тест очистки пустого контейнера."""
        container = DIContainer()
        
        # Не должно быть ошибки
        container.clear()
        
        assert not container.is_registered("any_key")

    def test_register_none_value(self):
        """Тест регистрации None значения."""
        container = DIContainer()
        container.register_singleton("test_key", None)
        
        result = container.resolve("test_key")
        
        assert result is None

    def test_register_with_empty_key(self):
        """Тест регистрации с пустым ключом."""
        container = DIContainer()
        container.register_singleton("", "value")
        
        result = container.resolve("")
        
        assert result == "value"

    def test_multiple_singletons(self):
        """Тест регистрации множественных singleton зависимостей."""
        container = DIContainer()
        container.register_singleton("key1", "value1")
        container.register_singleton("key2", "value2")
        container.register_singleton("key3", "value3")
        
        assert container.resolve("key1") == "value1"
        assert container.resolve("key2") == "value2"
        assert container.resolve("key3") == "value3"

    def test_mixed_lifetimes(self):
        """Тест смешанных времен жизни в одном контейнере."""
        container = DIContainer()
        
        # Singleton
        container.register_singleton("singleton", "singleton_value")
        
        # Transient factory
        call_count = 0
        
        def transient_factory():
            nonlocal call_count
            call_count += 1
            return f"transient_{call_count}"
        
        container.register_factory("transient", transient_factory, lifetime=Lifetime.TRANSIENT)
        
        # Проверяем singleton
        assert container.resolve("singleton") == "singleton_value"
        assert container.resolve("singleton") == "singleton_value"
        
        # Проверяем transient
        assert container.resolve("transient") == "transient_1"
        assert container.resolve("transient") == "transient_2"

    def test_factory_with_parameters(self):
        """Тест фабрики, которая создает объекты с параметрами."""
        container = DIContainer()
        
        class TestClass:
            def __init__(self, value):
                self.value = value
        
        def factory():
            return TestClass("factory_value")
        
        container.register_factory("test_key", factory, lifetime=Lifetime.SINGLETON)
        
        instance = container.resolve("test_key")
        
        assert isinstance(instance, TestClass)
        assert instance.value == "factory_value"

    def test_override_registration(self):
        """Тест переопределения регистрации."""
        container = DIContainer()
        container.register_singleton("test_key", "value1")
        
        assert container.resolve("test_key") == "value1"
        
        # Переопределяем
        container.register_singleton("test_key", "value2")
        
        assert container.resolve("test_key") == "value2"

    def test_factory_exception_handling(self):
        """Тест обработки исключений в фабрике."""
        container = DIContainer()
        
        def failing_factory():
            raise ValueError("Factory error")
        
        container.register_factory("test_key", failing_factory, lifetime=Lifetime.TRANSIENT)
        
        with pytest.raises(ValueError, match="Factory error"):
            container.resolve("test_key")


