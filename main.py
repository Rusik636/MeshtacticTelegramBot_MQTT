"""
Точка входа приложения Meshtastic Telegram Bot.

Инициализирует конфигурацию и запускает приложение.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Добавляем src в путь для импортов
sys.path.insert(0, str(Path(__file__).parent))

from src.config import AppConfig, setup_basic_logging
from src.application.app import MeshtasticTelegramBotApp

# Логирование настраивается автоматически при загрузке конфигурации
logger = logging.getLogger(__name__)


async def main() -> None:
    """Главная функция приложения."""
    # Настраиваем базовое логирование для отображения ошибок конфигурации
    setup_basic_logging()
    
    try:
        # Проверяем наличие .env файла (опционально, так как переменные могут быть в окружении)
        env_file = Path(".env")
        if not env_file.exists():
            logger.warning(
                "Файл .env не найден. "
                "Убедитесь, что переменные окружения заданы через env_file в docker-compose.yml "
                "или через переменные окружения системы."
            )
        
        # Загружаем конфигурацию (сначала из YAML, затем из .env для обратной совместимости)
        try:
            config = AppConfig.load_from_yaml()
        except ValueError as e:
            # Ошибки валидации конфигурации
            logger.error(f"Ошибка конфигурации: {e}")
            print("\n❌ ОШИБКА КОНФИГУРАЦИИ:")
            print(str(e))
            print("\nПроверьте файл .env и убедитесь, что все обязательные переменные заданы.")
            sys.exit(1)
        except Exception as e:
            error_msg = str(e)
            if "telegram" in error_msg.lower() or "bot_token" in error_msg.lower():
                logger.error(f"Ошибка загрузки конфигурации Telegram: {error_msg}")
                print("\n❌ ОШИБКА: Не задан TELEGRAM_BOT_TOKEN")
                print("Убедитесь, что в файле .env задана переменная:")
                print("TELEGRAM_BOT_TOKEN=your_bot_token_here")
                print("\nИли проверьте, что переменные окружения правильно передаются в контейнер.")
                sys.exit(1)
            raise
        
        # Настраиваем полное логирование через конфигурацию
        config.setup_logging()
        logger.info("Инициализация Meshtastic Telegram Bot")
        
        # Создаем и запускаем приложение
        app = MeshtasticTelegramBotApp(config)
        await app.run_forever()
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске приложения: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

