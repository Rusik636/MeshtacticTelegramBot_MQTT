# Meshtastic MQTT Telegram Bot

Телеграм-бот для приема сообщений от Meshtastic через MQTT и их публикации в Telegram чаты. Также реализует функционал MQTT-прокси для пересылки сообщений в другие MQTT брокеры.

## Архитектура

Проект следует слоистой архитектуре и принципам SOLID:

- **Domain** (`src/domain/`) - доменные модели и бизнес-логика
- **Repository** (`src/repo/`) - интерфейсы и реализации для работы с внешними системами (MQTT, Telegram)
- **Service** (`src/service/`) - бизнес-сервисы (обработка сообщений, MQTT прокси)
- **Handlers** (`src/handlers/`) - обработчики событий
- **Application** (`src/application/`) - оркестрация компонентов приложения

## Возможности

- ✅ Прием сообщений от Meshtastic через MQTT брокер (Mosquitto)
- ✅ Публикация сообщений в групповой Telegram чат
- ✅ Отправка сообщений пользователям в личные чаты
- ✅ **Интерактивные команды бота в личном чате** (/start, /help, /status, /info)
- ✅ **Контроль доступа через разрешенные user_ids**
- ✅ MQTT прокси для пересылки сообщений в другие брокеры
- ✅ Поддержка множественных прокси-целей
- ✅ Асинхронная обработка сообщений
- ✅ Структурированное логирование
- ✅ Graceful shutdown
- ✅ Docker и Docker Compose поддержка

## Требования

- Python 3.11+
- Docker и Docker Compose (для запуска через Docker)
- Telegram Bot Token (получить у [@BotFather](https://t.me/BotFather))
- MQTT брокер (Mosquitto включен в docker-compose)

## Установка и запуск

### Через Docker Compose (рекомендуется)

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd Meshtastic_MQTT_bot
```

2. Создайте файл `.env` на основе `env.example`:
```bash
cp env.example .env
```

3. Настройте переменные окружения в `.env`:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_GROUP_CHAT_ID=your_group_chat_id_here
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321

MQTT_SOURCE_HOST=mosquitto
MQTT_SOURCE_PORT=1883
MQTT_SOURCE_TOPIC=msh/2/json/#
```

4. Запустите через Docker Compose:
```bash
docker-compose up -d
```

5. Просмотр логов:
```bash
docker-compose logs -f telegram-bot
```

Пересборка образов
1. Пересобрать все образы (с кэшем)
docker-compose build
2. Пересобрать без кэша (полная пересборка)
docker-compose build --no-cache
Полезно, если нужно гарантировать свежую сборку.
3. Пересобрать и запустить
docker-compose up --build
Или в фоновом режиме:
docker-compose up --build -d
4. Пересобрать только конкретный сервис
docker-compose build telegram-bot
5. Остановить, пересобрать и запустить заново
docker-compose downdocker-compose build --no-cachedocker-compose up -d
Рекомендуемый workflow
После изменений в коде:
# 1. Остановить контейнеры 
docker-compose down

# 2. Пересобрать образ бота (mosquitto не нужно пересобирать)
docker-compose build telegram-bot

# 3. Запустить заново
docker-compose up -d

# 4. Проверить логи
docker-compose logs -f telegram-bot

Или одной командой:
docker-compose up --build -d


### Локальная установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Настройте `.env` файл (см. выше)

3. Запустите приложение:
```bash
python main.py
```

## Конфигурация

### Переменные окружения

#### Telegram
- `TELEGRAM_BOT_TOKEN` - токен бота (обязательно)
- `TELEGRAM_GROUP_CHAT_ID` - ID группового чата (опционально)
- `TELEGRAM_ALLOWED_USER_IDS` - список разрешенных user_id через запятую (опционально, если не задан - все пользователи)

#### MQTT Source (источник данных)
- `MQTT_SOURCE_HOST` - хост MQTT брокера (по умолчанию: localhost)
- `MQTT_SOURCE_PORT` - порт MQTT брокера (по умолчанию: 1883)
- `MQTT_SOURCE_USERNAME` - имя пользователя (опционально)
- `MQTT_SOURCE_PASSWORD` - пароль (опционально)
- `MQTT_SOURCE_TOPIC` - топик для подписки (по умолчанию: msh/2/json/#)
- `MQTT_SOURCE_CLIENT_ID` - MQTT client ID (по умолчанию: meshtastic-telegram-bot)
- `MQTT_SOURCE_QOS` - QoS уровень (0, 1 или 2, по умолчанию: 1)

#### MQTT Proxy (прокси в другие брокеры)
Для каждого прокси-цели используйте префикс `MQTT_PROXY_TARGET_`:
- `MQTT_PROXY_TARGET_NAME` - имя прокси-цели (для логирования)
- `MQTT_PROXY_TARGET_HOST` - хост целевого брокера
- `MQTT_PROXY_TARGET_PORT` - порт (по умолчанию: 1883)
- `MQTT_PROXY_TARGET_USERNAME` - имя пользователя (опционально)
- `MQTT_PROXY_TARGET_PASSWORD` - пароль (опционально)
- `MQTT_PROXY_TARGET_TOPIC_PREFIX` - префикс для топика (опционально)
- `MQTT_PROXY_TARGET_ENABLED` - включен ли прокси (по умолчанию: true)
- `MQTT_PROXY_TARGET_QOS` - QoS уровень (по умолчанию: 1)

**Примечание**: Для нескольких прокси-целей используйте разные префиксы или настройте через код.

#### Логирование
- `LOG_LEVEL` - уровень логирования (DEBUG, INFO, WARNING, ERROR, по умолчанию: INFO)
- `LOG_FORMAT` - формат логов (json или text, по умолчанию: json)

### Получение Telegram Chat ID

1. Добавьте бота в группу
2. Отправьте сообщение в группу
3. Используйте API: `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
4. Найдите `chat.id` в ответе

Или используйте бота [@userinfobot](https://t.me/userinfobot) для получения вашего user_id.

## Команды бота

Бот поддерживает интерактивные команды в личном чате. Для работы с командами:

1. Найдите вашего бота в Telegram
2. Начните личный чат с ботом
3. Отправьте команду `/start`

### Доступные команды

- `/start` - начать работу с ботом, получить приветственное сообщение
- `/help` - показать справку по всем доступным командам
- `/status` - показать текущий статус бота (подключения, настройки)
- `/info` - показать детальную информацию о конфигурации (групповой чат, разрешенные пользователи, MQTT прокси)

### Контроль доступа

Бот проверяет разрешения пользователя перед обработкой команд:

- Если `TELEGRAM_ALLOWED_USER_IDS` не задан (или пуст) - **все пользователи** могут использовать команды
- Если `TELEGRAM_ALLOWED_USER_IDS` задан - только указанные пользователи могут использовать команды

**Пример настройки:**
```env
# Разрешить доступ только двум пользователям
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321

# Или оставить пустым для доступа всем
TELEGRAM_ALLOWED_USER_IDS=
```

**Важно:** 
- Команды работают только в **личном чате** с ботом
- Сообщения от Meshtastic отправляются в групповой чат и разрешенным пользователям в личные чаты
- Неразрешенные пользователи получат сообщение об отказе в доступе

## Структура проекта

```
Meshtastic_MQTT_bot/
├── src/
│   ├── application/      # Слой приложения (оркестрация)
│   ├── config.py         # Конфигурация
│   ├── connection/       # Подключения (зарезервировано)
│   ├── domain/           # Доменные модели
│   ├── handlers/         # Обработчики событий
│   ├── repo/             # Репозитории (MQTT, Telegram)
│   └── service/          # Бизнес-сервисы
├── mosquitto/            # Конфигурация Mosquitto
│   ├── config/
│   ├── data/
│   └── log/
├── main.py               # Точка входа
├── Dockerfile            # Docker образ
├── docker-compose.yml    # Docker Compose конфигурация
├── requirements.txt      # Python зависимости
├── env.example           # Пример конфигурации
└── README.md             # Документация
```

## Разработка

### Запуск тестов

```bash
# TODO: добавить тесты
pytest
```

### Линтинг

```bash
# TODO: добавить линтеры
ruff check .
mypy src/
```

## Безопасность

- ✅ Не храните секреты в репозитории
- ✅ Используйте переменные окружения для конфигурации
- ✅ Применяйте `.env` файл локально и secret management в продакшене
- ✅ Валидация входных данных через Pydantic
- ✅ Безопасная обработка исключений

## Логирование

Приложение использует структурированное логирование через `structlog`:
- JSON формат для продакшена
- Text формат для разработки
- Корреляционные ID для трейсинга
- Уровни логирования: DEBUG, INFO, WARNING, ERROR

## Мониторинг

Health checks настроены в Docker Compose:
- Mosquitto: проверка подключения через `mosquitto_sub`
- Telegram Bot: проверка доступности Python процесса

## Troubleshooting

Подробная инструкция по решению проблем доступна в файле [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Частые проблемы

#### Ошибка: "telegram Field required" или "TELEGRAM_BOT_TOKEN не задан"

**Решение:**
1. Убедитесь, что файл `.env` существует в корне проекта
2. Проверьте, что в `.env` задана переменная `TELEGRAM_BOT_TOKEN=your_actual_token`
3. Пересоберите контейнер: `docker-compose build telegram-bot && docker-compose up -d`

#### Бот не получает сообщения

1. Проверьте, что бот добавлен в группу
2. Убедитесь, что `TELEGRAM_GROUP_CHAT_ID` настроен правильно
3. Проверьте логи: `docker-compose logs telegram-bot`

#### MQTT подключение не работает

1. Проверьте, что Mosquitto запущен: `docker-compose ps`
2. Убедитесь, что `MQTT_SOURCE_HOST` указывает на `mosquitto` (в Docker) или `localhost` (локально)
3. Проверьте логи Mosquitto: `docker-compose logs mosquitto`

#### Прокси не работает

1. Проверьте, что `MQTT_PROXY_TARGET_ENABLED=true`
2. Убедитесь, что целевой брокер доступен
3. Проверьте логи на ошибки подключения

## Лицензия

См. файл [LICENSE](LICENSE)

## Вклад

1. Fork проекта
2. Создайте feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'feat: add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

## TODO

- [ ] Добавить unit-тесты
- [ ] Добавить интеграционные тесты
- [ ] Настроить CI/CD (GitHub Actions / GitLab CI)
- [ ] Добавить метрики (Prometheus)
- [ ] Реализовать retry механизм для прокси
- [ ] Добавить поддержку аутентификации в Mosquitto
- [ ] Реализовать фильтрацию сообщений
- [ ] Добавить команды бота для управления

