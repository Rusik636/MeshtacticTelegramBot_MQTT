# Решение проблем

## Проблема: "telegram Field required" или "TELEGRAM_BOT_TOKEN не задан"

### Причина
Переменные окружения из файла `.env` не загружаются в контейнер.

### Решение

1. **Убедитесь, что файл `.env` существует в корне проекта:**
   ```bash
   ls -la .env
   ```

2. **Проверьте содержимое `.env` файла:**
   ```bash
   cat .env
   ```
   
   Должна быть строка:
   ```
   TELEGRAM_BOT_TOKEN=your_actual_bot_token_here
   ```
   
   **Важно:** Замените `your_actual_bot_token_here` на реальный токен от @BotFather!

3. **Проверьте, что файл `.env` не в `.gitignore` (если нужно):**
   ```bash
   cat .gitignore | grep .env
   ```

4. **Пересоберите и перезапустите контейнеры:**
   ```bash
   docker-compose down
   docker-compose build telegram-bot
   docker-compose up -d
   ```

5. **Проверьте логи на наличие ошибок:**
   ```bash
   docker-compose logs telegram-bot
   ```

### Альтернативное решение: переменные окружения напрямую

Если файл `.env` не работает, можно задать переменные напрямую в `docker-compose.yml`:

```yaml
telegram-bot:
  environment:
    - TELEGRAM_BOT_TOKEN=your_bot_token_here
    - TELEGRAM_GROUP_CHAT_ID=your_chat_id
    # ... другие переменные
```

## Проблема: "chown: /mosquitto/config: Read-only file system"

### Решение
Эта проблема уже исправлена в `docker-compose.yml` - убран флаг `:ro` из монтирования конфига.

Если проблема сохраняется:
```bash
docker-compose down
docker-compose up --build -d
```

## Проверка конфигурации

Для проверки, что все переменные загружены правильно:

```bash
# Войдите в контейнер
docker-compose exec telegram-bot bash

# Проверьте переменные окружения
env | grep TELEGRAM
env | grep MQTT
```

## Получение Telegram Bot Token

1. Найдите [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте команду `/newbot`
3. Следуйте инструкциям
4. Скопируйте полученный токен в файл `.env`

## Получение Chat ID

1. Добавьте бота [@userinfobot](https://t.me/userinfobot) в Telegram
2. Отправьте команду `/start`
3. Скопируйте ваш `Id` (это ваш user_id)
4. Для получения group_chat_id:
   - Добавьте бота в группу
   - Отправьте сообщение в группу
   - Используйте API: `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
   - Найдите `chat.id` в ответе

