"""
Главное приложение.

Оркестрирует работу всех компонентов системы.
"""
import asyncio
import logging
import signal
from typing import Optional

from src.config import AppConfig
from src.repo.mqtt_repository import AsyncMQTTRepository
from src.repo.telegram_repository import AsyncTelegramRepository
from src.service.message_service import MessageService
from src.service.mqtt_proxy_service import MQTTProxyService
from src.handlers.mqtt_handler import MQTTMessageHandlerImpl
from src.handlers.telegram_commands import TelegramCommandsHandler


logger = logging.getLogger(__name__)


class MeshtasticTelegramBotApp:
    """
    Главное приложение Meshtastic Telegram Bot.
    
    Управляет жизненным циклом приложения и координирует работу компонентов.
    """
    
    def __init__(self, config: AppConfig):
        """
        Инициализирует приложение.
        
        Args:
            config: Конфигурация приложения
        """
        self.config = config
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None
        
        # Инициализируем компоненты
        self.mqtt_repo = AsyncMQTTRepository(config.mqtt_source)
        self.telegram_repo = AsyncTelegramRepository(config.telegram)
        self.message_service = MessageService()
        self.proxy_service = MQTTProxyService(config.mqtt_proxy_targets)
        
        # Создаем обработчик MQTT сообщений
        notify_user_ids = config.telegram.allowed_user_ids
        self.mqtt_handler = MQTTMessageHandlerImpl(
            telegram_repo=self.telegram_repo,
            proxy_service=self.proxy_service,
            message_service=self.message_service,
            notify_user_ids=notify_user_ids
        )
        
        # Создаем обработчик команд Telegram
        self.telegram_commands_handler = TelegramCommandsHandler(
            bot=self.telegram_repo.bot,
            telegram_repo=self.telegram_repo,
            proxy_service=self.proxy_service
        )
    
    async def start(self) -> None:
        """Запускает приложение."""
        logger.info("Запуск Meshtastic Telegram Bot")
        
        self._shutdown_event = asyncio.Event()
        self._running = True
        self._subscribe_task: Optional[asyncio.Task] = None
        self._telegram_polling_task: Optional[asyncio.Task] = None
        
        # Настраиваем обработчики сигналов для graceful shutdown
        # На Windows signal.SIGTERM может не работать, поэтому используем только SIGINT
        try:
            loop = asyncio.get_event_loop()
            if hasattr(signal, 'SIGTERM'):
                loop.add_signal_handler(
                    signal.SIGTERM,
                    lambda: asyncio.create_task(self._handle_shutdown(signal.SIGTERM))
                )
            loop.add_signal_handler(
                signal.SIGINT,
                lambda: asyncio.create_task(self._handle_shutdown(signal.SIGINT))
            )
        except (NotImplementedError, ValueError):
            # На Windows add_signal_handler может не работать
            logger.warning("Обработчики сигналов не могут быть установлены (возможно, Windows)")
        
        try:
            # Запускаем MQTT прокси
            await self.proxy_service.start()
            
            # Подключаемся к MQTT брокеру
            await self.mqtt_repo.connect()
            
            logger.info("Приложение запущено и готово к работе")
            
            # Запускаем подписку на MQTT в отдельной задаче (блокирующая операция)
            self._subscribe_task = asyncio.create_task(
                self.mqtt_repo.subscribe(
                    self.config.mqtt_source.topic,
                    self.mqtt_handler
                )
            )
            
            # Запускаем polling для Telegram команд в отдельной задаче
            self._telegram_polling_task = asyncio.create_task(
                self.telegram_commands_handler.start_polling()
            )
            
            # Ждем завершения задач или сигнала остановки
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Критическая ошибка при запуске приложения: {e}", exc_info=True)
            raise
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Останавливает приложение."""
        if not self._running:
            return
        
        logger.info("Остановка Meshtastic Telegram Bot")
        self._running = False
        
        # Отменяем задачу подписки на MQTT, если она запущена
        if self._subscribe_task and not self._subscribe_task.done():
            self._subscribe_task.cancel()
            try:
                await self._subscribe_task
            except asyncio.CancelledError:
                pass
        
        # Останавливаем polling Telegram
        if self._telegram_polling_task and not self._telegram_polling_task.done():
            self._telegram_polling_task.cancel()
            try:
                await self._telegram_polling_task
            except asyncio.CancelledError:
                pass
        
        try:
            # Отключаемся от MQTT брокера
            await self.mqtt_repo.disconnect()
            
            # Останавливаем прокси
            await self.proxy_service.stop()
            
            logger.info("Приложение остановлено")
        except Exception as e:
            logger.error(f"Ошибка при остановке приложения: {e}", exc_info=True)
        
        if self._shutdown_event:
            self._shutdown_event.set()
    
    async def _handle_shutdown(self, sig: signal.Signals | int) -> None:
        """Обрабатывает сигнал остановки."""
        sig_name = sig.name if hasattr(sig, 'name') else str(sig)
        logger.info(f"Получен сигнал остановки: {sig_name}")
        await self.stop()
    
    async def run_forever(self) -> None:
        """Запускает приложение и ждет завершения."""
        try:
            await self.start()
        except KeyboardInterrupt:
            logger.info("Получен KeyboardInterrupt")
        finally:
            if self._shutdown_event:
                await self._shutdown_event.wait()

