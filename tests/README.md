# Unit-тесты для Meshtastic_MQTT_bot

## Структура тестов

Тесты организованы по слоям архитектуры:

```
tests/
├── conftest.py                    # Общие фикстуры
├── unit/                          # Unit-тесты (изолированные тесты компонентов)
│   ├── domain/                    # Тесты доменного слоя
│   │   └── test_message.py
│   ├── service/                   # Тесты сервисного слоя
│   │   ├── test_message_service.py
│   │   ├── test_message_factory.py
│   │   ├── test_node_cache_updater.py
│   │   ├── test_telegram_message_formatter.py
│   │   └── test_node_cache_service.py
│   └── infrastructure/            # Тесты инфраструктурного слоя
│       └── test_di_container.py
├── integration/                   # Интеграционные тесты (проверка взаимодействия компонентов)
│   └── test_message_grouping.py  # Тест группировки сообщений от MQTT до Telegram
└── README.md
```

## Установка зависимостей

```bash
pip install -r requirements-test.txt
```

## Запуск тестов

### Все тесты
```bash
pytest tests/
```

### Конкретный файл
```bash
pytest tests/unit/domain/test_message.py
```

### Конкретный тест
```bash
pytest tests/unit/domain/test_message.py::TestMeshtasticMessage::test_create_minimal_message
```

### С покрытием кода
```bash
pytest --cov=src --cov-report=html tests/
```

### Только интеграционные тесты
```bash
pytest tests/integration/
```

### Только unit-тесты
```bash
pytest tests/unit/
```

### Только быстрые тесты (без asyncio)
```bash
pytest -m "not asyncio" tests/
```

## Покрытие кода

Целевое покрытие:
- **Domain Layer**: 100%
- **Service Layer**: 90%+
- **Handlers Layer**: 85%+
- **Repositories**: 80%+
- **Infrastructure**: 90%+

## Фикстуры

Все общие фикстуры находятся в `tests/conftest.py`:

- `mock_file_storage` - мок файлового хранилища
- `mock_node_cache_service` - мок сервиса кэша нод
- `mock_telegram_repo` - мок Telegram репозитория
- `mock_mqtt_repo` - мок MQTT репозитория
- `sample_text_message_payload` - пример payload текстового сообщения
- `sample_nodeinfo_payload` - пример payload nodeinfo
- `sample_position_payload` - пример payload position
- `sample_meshtastic_message` - пример MeshtasticMessage объекта

## Написание новых тестов

При написании новых тестов следуйте стандартам:

1. Используйте фикстуры из `conftest.py`
2. Мокируйте все внешние зависимости
3. Используйте `pytest.mark.asyncio` для async функций
4. Параметризуйте тесты для множественных сценариев
5. Группируйте связанные тесты в классы
6. Используйте понятные имена тестов

Пример:
```python
class TestMyService:
    """Тесты для MyService."""
    
    def test_my_method_success(self, mock_dependency):
        """Тест успешного выполнения метода."""
        service = MyService(mock_dependency)
        result = service.my_method()
        assert result == expected_value
```


