"""
Главное приложение бота.

Собирает все компоненты вместе и управляет их жизненным циклом.
"""

import asyncio
import logging
import signal
from typing import Optional

from src.config import AppConfig
from src.repo.telegram_repository import AsyncTelegramRepository
from src.service.main_broker_service import MainBrokerService
from src.service.message_service import MessageService
from src.service.mqtt_proxy_service import MQTTProxyService
from src.service.node_cache_service import NodeCacheService
from src.handlers.mqtt_handler import MQTTMessageHandlerImpl
from src.handlers.proxy_status_handler import ProxyStatusHandler
from src.handlers.telegram_commands import TelegramCommandsHandler


logger = logging.getLogger(__name__)


class MeshtasticTelegramBotApp:
    """Главный класс приложения - запускает и останавливает все сервисы."""

    def __init__(self, config: AppConfig):
        """
        Создает все необходимые сервисы и обработчики.

        Args:
            config: Конфигурация приложения
        """
        self.config = config
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None

        # Инициализируем сервисы основного брокера
        self.main_broker_service = MainBrokerService(config.mqtt_source)
        self.telegram_repo = AsyncTelegramRepository(config.telegram)
        self.node_cache_service = NodeCacheService()
        self.message_service = MessageService(
            node_cache_service=self.node_cache_service,
            payload_format=config.mqtt_source.payload_format,
        )

        # Инициализируем прокси-сервис отдельно
        self.proxy_service = MQTTProxyService(
            config.mqtt_proxy_targets, source_topic=config.mqtt_source.topic
        )

        # Создаем обработчик MQTT сообщений
        notify_user_ids = config.telegram.allowed_user_ids
        self.mqtt_handler = MQTTMessageHandlerImpl(
            telegram_repo=self.telegram_repo,
            proxy_service=self.proxy_service,
            message_service=self.message_service,
            notify_user_ids=notify_user_ids,
        )

        # Создаем обработчик статуса прокси (отдельно от основного брокера)
        proxy_status_handler = ProxyStatusHandler(self.proxy_service)

        # Создаем обработчик команд Telegram
        self.telegram_commands_handler = TelegramCommandsHandler(
            bot=self.telegram_repo.bot,
            telegram_repo=self.telegram_repo,
            proxy_status_handler=proxy_status_handler,
        )

    async def start(self) -> None:
        """Запускает все сервисы и начинает обработку сообщений."""
        logger.info("Запуск Meshtastic Telegram Bot")

        self._shutdown_event = asyncio.Event()
        self._running = True
        self._subscribe_task: Optional[asyncio.Task] = None
        self._telegram_polling_task: Optional[asyncio.Task] = None

        # Настраиваем обработку сигналов для корректного завершения
        # На Windows SIGTERM может не работать
        try:
            loop = asyncio.get_event_loop()
            if hasattr(signal, "SIGTERM"):
                loop.add_signal_handler(
                    signal.SIGTERM,
                    lambda: asyncio.create_task(self._handle_shutdown(signal.SIGTERM)),
                )
            loop.add_signal_handler(
                signal.SIGINT,
                lambda: asyncio.create_task(self._handle_shutdown(signal.SIGINT)),
            )
        except (NotImplementedError, ValueError):
            # На Windows может не работать
            logger.warning(
                "Не удалось установить обработчики сигналов (возможно, Windows)"
            )

        try:
            # Запускаем прокси и основной брокер
            await self.proxy_service.start()
            await self.main_broker_service.start()

            logger.info("Приложение запущено и готово к работе")

            # Подписка на MQTT - блокирующая операция, запускаем в отдельной
            # задаче
            self._subscribe_task = asyncio.create_task(
                self.main_broker_service.subscribe(self.mqtt_handler)
            )

            # Polling для Telegram команд тоже в отдельной задаче
            self._telegram_polling_task = asyncio.create_task(
                self.telegram_commands_handler.start_polling()
            )

            # Ждем сигнала остановки
            await self._shutdown_event.wait()

        except Exception as e:
            logger.error(
                f"Критическая ошибка при запуске приложения: {e}", exc_info=True
            )
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Останавливает все сервисы и задачи."""
        if not self._running:
            return

        logger.info("Остановка Meshtastic Telegram Bot")
        self._running = False

        # Отменяем задачи
        if self._subscribe_task and not self._subscribe_task.done():
            self._subscribe_task.cancel()
            try:
                await self._subscribe_task
            except asyncio.CancelledError:
                pass

        if self._telegram_polling_task and not self._telegram_polling_task.done():
            self._telegram_polling_task.cancel()
            try:
                await self._telegram_polling_task
            except asyncio.CancelledError:
                pass

        try:
            # Отключаемся от брокеров
            await self.main_broker_service.stop()
            await self.proxy_service.stop()

            logger.info("Приложение остановлено")
        except Exception as e:
            logger.error(f"Ошибка при остановке приложения: {e}", exc_info=True)

        if self._shutdown_event:
            self._shutdown_event.set()

    async def _handle_shutdown(self, sig: signal.Signals | int) -> None:
        """
        Вызывается при получении сигнала остановки (SIGTERM/SIGINT).

        Args:
            sig: Сигнал остановки
        """
        sig_name = sig.name if hasattr(sig, "name") else str(sig)
        logger.info(f"Получен сигнал остановки: {sig_name}")
        await self.stop()

    async def run_forever(self) -> None:
        """Запускает приложение и работает до остановки."""
        try:
            await self.start()
        except KeyboardInterrupt:
            logger.info("Получен KeyboardInterrupt")
        finally:
            if self._shutdown_event:
                await self._shutdown_event.wait()
