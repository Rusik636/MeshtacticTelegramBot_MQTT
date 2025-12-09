"""
Точка входа приложения Meshtastic Telegram Bot.

Инициализирует конфигурацию и запускает приложение.
"""
import asyncio
import sys
import structlog
import logging
from pathlib import Path

# Добавляем src в путь для импортов
sys.path.insert(0, str(Path(__file__).parent))

from src.config import AppConfig
from src.application.app import MeshtasticTelegramBotApp


async def main() -> None:
    """Главная функция приложения."""
    logger = None
    try:
        # Настраиваем базовое логирование для отображения ошибок конфигурации
        logging.basicConfig(level=logging.INFO)
        logger = structlog.get_logger()
        
        # Проверяем наличие .env файла (опционально, так как переменные могут быть в окружении)
        env_file = Path(".env")
        if not env_file.exists():
            logger.warning(
                "Файл .env не найден. "
                "Убедитесь, что переменные окружения заданы через env_file в docker-compose.yml "
                "или через переменные окружения системы."
            )
        
        # Загружаем конфигурацию
        try:
            config = AppConfig()
        except ValueError as e:
            # Ошибки валидации конфигурации
            logger.error("Ошибка конфигурации", error=str(e))
            print("\n❌ ОШИБКА КОНФИГУРАЦИИ:")
            print(str(e))
            print("\nПроверьте файл .env и убедитесь, что все обязательные переменные заданы.")
            sys.exit(1)
        except Exception as e:
            error_msg = str(e)
            if "telegram" in error_msg.lower() or "bot_token" in error_msg.lower():
                logger.error("Ошибка загрузки конфигурации Telegram", error=error_msg)
                print("\n❌ ОШИБКА: Не задан TELEGRAM_BOT_TOKEN")
                print("Убедитесь, что в файле .env задана переменная:")
                print("TELEGRAM_BOT_TOKEN=your_bot_token_here")
                print("\nИли проверьте, что переменные окружения правильно передаются в контейнер.")
                sys.exit(1)
            raise
        
        # Настраиваем логирование через конфигурацию
        config.setup_logging()
        logger = structlog.get_logger()
        logger.info("Инициализация Meshtastic Telegram Bot", version="1.0.0")
        
        # Создаем и запускаем приложение
        app = MeshtasticTelegramBotApp(config)
        await app.run_forever()
        
    except KeyboardInterrupt:
        if logger:
            logger.info("Получен сигнал прерывания")
        sys.exit(0)
    except Exception as e:
        if logger:
            logger.error("Критическая ошибка при запуске приложения", error=str(e), exc_info=True)
        else:
            print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

