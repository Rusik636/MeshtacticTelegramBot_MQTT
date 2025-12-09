"""
Обработчик входящих MQTT сообщений.

Обрабатывает сообщения от Meshtastic и координирует их отправку в Telegram и прокси.
"""
import logging
from typing import List

from src.domain.message import MeshtasticMessage
from src.repo.mqtt_repository import MQTTMessageHandler
from src.repo.telegram_repository import TelegramRepository
from src.service.message_service import MessageService
from src.service.mqtt_proxy_service import MQTTProxyService


logger = logging.getLogger(__name__)


class MQTTMessageHandlerImpl(MQTTMessageHandler):
    """
    Реализация обработчика MQTT сообщений.
    
    Координирует обработку входящих сообщений:
    1. Парсит сообщение
    2. Отправляет в Telegram (группу и пользователей)
    3. Проксирует в другие MQTT брокеры
    """
    
    def __init__(
        self,
        telegram_repo: TelegramRepository,
        proxy_service: MQTTProxyService,
        message_service: MessageService,
        notify_user_ids: List[int] | None = None
    ):
        """
        Инициализирует обработчик.
        
        Args:
            telegram_repo: Репозиторий для работы с Telegram
            proxy_service: Сервис MQTT прокси
            message_service: Сервис обработки сообщений
            notify_user_ids: Список user_id для уведомлений (None = все разрешенные)
        """
        self.telegram_repo = telegram_repo
        self.proxy_service = proxy_service
        self.message_service = message_service
        self.notify_user_ids = notify_user_ids
    
    async def handle_message(self, topic: str, payload: bytes) -> None:
        """
        Обрабатывает входящее MQTT сообщение.
        
        Args:
            topic: MQTT топик
            payload: Данные сообщения
        """
        try:
            # Пропускаем protobuf сообщения (топики с /e/), так как они дублируют JSON сообщения
            # Meshtastic публикует сообщения в двух форматах:
            # - msh/2/json/2/e/... - protobuf (бинарный формат)
            # - msh/2/json/2/json/... - JSON (текстовый формат)
            # Обрабатываем только JSON формат, чтобы избежать ошибок парсинга
            if "/e/" in topic and "/json/" not in topic:
                logger.debug(f"Пропущено protobuf сообщение (дубликат JSON): topic={topic}")
                return
            
            logger.info(f"Получено MQTT сообщение: topic={topic}, payload_size={len(payload)}")
            
            # Парсим сообщение
            message: MeshtasticMessage = self.message_service.parse_mqtt_message(topic, payload)
            
            # Пропускаем сообщения типа nodeinfo и position (они обрабатываются для обновления кэша)
            if message.message_type in ("nodeinfo", "position"):
                logger.debug(f"Пропущено сообщение типа {message.message_type} (используется только для обновления кэша)")
                return
            
            # Отправляем только текстовые сообщения в Telegram
            if message.message_type != "text":
                logger.debug(f"Пропущено сообщение типа {message.message_type}")
                return
            
            # Форматируем для Telegram
            telegram_text = message.format_for_telegram()
            
            # Отправляем в групповой чат
            try:
                await self.telegram_repo.send_to_group(telegram_text)
            except Exception as e:
                logger.error(f"Ошибка при отправке в группу: {e}", exc_info=True)
            
            # Отправляем пользователям
            if self.notify_user_ids:
                for user_id in self.notify_user_ids:
                    if self.telegram_repo.is_user_allowed(user_id):
                        try:
                            await self.telegram_repo.send_to_user(user_id, telegram_text)
                        except Exception as e:
                            logger.error(
                                f"Ошибка при отправке пользователю: user_id={user_id}, error={e}",
                                exc_info=True
                            )
            
            # Проксируем в другие MQTT брокеры
            try:
                await self.proxy_service.proxy_message(message)
            except Exception as e:
                logger.error(f"Ошибка при проксировании сообщения: {e}", exc_info=True)
            
            logger.info(f"Успешно обработано MQTT сообщение: topic={topic}")
        except Exception as e:
            logger.error(
                f"Критическая ошибка при обработке MQTT сообщения: topic={topic}, error={e}",
                exc_info=True
            )

