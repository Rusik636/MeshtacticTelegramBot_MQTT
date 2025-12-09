# Настройка Meshtastic ноды для отправки данных в MQTT

## Обзор

Для отправки данных с ноды Meshtastic на ваш MQTT брокер нужно настроить ноду на публикацию сообщений в MQTT. Нода и сервер находятся в одной локальной WiFi сети.

## Шаг 1: Определение IP адреса сервера

### На Windows:
```powershell
ipconfig
```
Найдите IPv4 адрес вашего компьютера (например: `192.168.1.100`)

### На Linux/Mac:
```bash
ip addr show
# или
ifconfig
```

### Через Docker:
Если Mosquitto запущен в Docker, используйте IP адрес хоста, а не контейнера.

## Шаг 2: Проверка доступности MQTT брокера

Убедитесь, что порт 1883 открыт и доступен из локальной сети:

```bash
# Проверка с другого устройства в сети
mosquitto_pub -h <IP_АДРЕС_СЕРВЕРА> -p 1883 -t test -m "test message"
```

Или используйте MQTT клиент для проверки подключения.

## Шаг 3: Настройка Meshtastic ноды

### Вариант 1: Через приложение Meshtastic (Android/iOS)

1. Откройте приложение Meshtastic
2. Перейдите в **Settings** → **MQTT**
3. Включите **MQTT Enabled**
4. Заполните настройки:
   - **MQTT Server**: `tcp://<IP_АДРЕС_СЕРВЕРА>:1883`
     - Пример: `tcp://192.168.1.100:1883`
   - **MQTT Username**: (оставьте пустым, если не требуется)
   - **MQTT Password**: (оставьте пустым, если не требуется)
   - **MQTT Topic**: `msh/2/json/#` (стандартный топик Meshtastic)
   - **MQTT Client ID**: (опционально, можно оставить пустым)

5. Сохраните настройки

### Вариант 2: Через веб-интерфейс (если доступен)

1. Подключитесь к веб-интерфейсу ноды (обычно `http://meshtastic.local` или IP адрес ноды)
2. Перейдите в раздел **MQTT Settings**
3. Введите те же настройки, что указаны выше

### Вариант 3: Через Serial/CLI

Если у вас есть доступ к Serial порту или CLI:

```bash
# Подключитесь к ноде через Serial
# Затем выполните команды:

prefs set mqtt.enabled true
prefs set mqtt.address <IP_АДРЕС_СЕРВЕРА>
prefs set mqtt.port 1883
prefs set mqtt.username ""
prefs set mqtt.password ""
prefs set mqtt.root msh/2/json/#
```

## Шаг 4: Проверка работы

### Проверка через mosquitto_sub:

```bash
# На сервере с MQTT брокером
docker-compose exec mosquitto mosquitto_sub -h localhost -t "msh/2/json/#" -v
```

**Что должно произойти:**
- Команда выполнится и будет ждать сообщений (курсор мигает)
- Когда нода отправит сообщение, вы увидите вывод в формате:
  ```
  msh/2/json/!12345678 {"id":12345678,"rx_time":1234567890,...}
  ```
- Для выхода нажмите `Ctrl+C`

**Если ничего не происходит** - это нормально, команда ждет сообщений. Проверьте:
1. Что нода подключена к MQTT (см. логи: `docker-compose logs mosquitto`)
2. Что нода отправляет сообщения (отправьте тестовое сообщение через Meshtastic)

Подробнее о тестировании MQTT см. [MQTT_TESTING.md](MQTT_TESTING.md)

Или если mosquitto установлен локально:
```bash
mosquitto_sub -h localhost -t "msh/2/json/#" -v
```

### Проверка через логи бота:

```bash
docker-compose logs -f telegram-bot
```

Вы должны увидеть сообщения о получении MQTT сообщений.

## Важные моменты

### 1. IP адрес сервера

- Используйте **статический IP** адрес или настройте резервацию DHCP
- Если IP меняется, нода не сможет подключиться

### 2. Firewall

Убедитесь, что порт 1883 открыт в файрволе:

**Windows:**
```powershell
# Разрешить входящие подключения на порт 1883
New-NetFirewallRule -DisplayName "MQTT" -Direction Inbound -LocalPort 1883 -Protocol TCP -Action Allow
```

**Linux:**
```bash
sudo ufw allow 1883/tcp
```

### 3. Формат адреса MQTT

Meshtastic поддерживает следующие форматы:
- `tcp://192.168.1.100:1883` (рекомендуется)
- `192.168.1.100:1883` (без префикса)
- `mqtt://192.168.1.100:1883` (альтернативный формат)

### 4. Топики Meshtastic

Стандартные топики:
- `msh/2/json/#` - все сообщения в формате JSON
- `msh/2/text/#` - текстовые сообщения
- `msh/2/stat/#` - статусные сообщения

Ваш бот настроен на `msh/2/json/#` - это правильный выбор.

## Устранение проблем

### Нода не подключается к MQTT

1. Проверьте, что Mosquitto запущен:
   ```bash
   docker-compose ps mosquitto
   ```

2. Проверьте логи Mosquitto:
   ```bash
   docker-compose logs mosquitto
   ```

3. Проверьте доступность порта:
   ```bash
   telnet <IP_АДРЕС_СЕРВЕРА> 1883
   ```

4. Проверьте настройки ноды - убедитесь, что адрес указан правильно

### Сообщения не приходят

1. Проверьте топик в настройках ноды (должен быть `msh/2/json/#`)
2. Проверьте логи бота на наличие ошибок
3. Убедитесь, что нода отправляет сообщения (проверьте через mosquitto_sub)

### Безопасность (опционально)

Для повышения безопасности можно настроить аутентификацию в Mosquitto:

1. Создайте файл паролей:
   ```bash
   docker-compose exec mosquitto mosquitto_passwd -c /mosquitto/config/passwd meshtastic_user
   ```

2. Обновите `mosquitto.conf`:
   ```
   allow_anonymous false
   password_file /mosquitto/config/passwd
   ```

3. Укажите username/password в настройках ноды

## Пример конфигурации

**Настройки ноды Meshtastic:**
```
MQTT Enabled: ✓
MQTT Server: tcp://192.168.1.100:1883
MQTT Username: (пусто)
MQTT Password: (пусто)
MQTT Topic: msh/2/json/#
```

**Настройки бота (.env):**
```env
MQTT_SOURCE_HOST=mosquitto  # Для Docker
MQTT_SOURCE_PORT=1883
MQTT_SOURCE_TOPIC=msh/2/json/#
```

После настройки нода начнет публиковать все сообщения в ваш MQTT брокер, и бот автоматически перешлет их в Telegram.

