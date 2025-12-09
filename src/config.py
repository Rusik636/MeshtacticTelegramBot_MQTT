"""
Конфигурация приложения.

Использует Pydantic Settings для валидации и загрузки из переменных окружения.
"""
import os
import logging
from typing import List, Optional
import structlog
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MQTTBrokerConfig(BaseSettings):
    """Конфигурация MQTT брокера (источник данных)."""
    
    model_config = SettingsConfigDict(env_prefix="MQTT_SOURCE_")
    
    host: str = Field(default="localhost", description="Хост MQTT брокера")
    port: int = Field(default=1883, description="Порт MQTT брокера")
    username: Optional[str] = Field(default=None, description="Имя пользователя")
    password: Optional[str] = Field(default=None, description="Пароль")
    topic: str = Field(default="msh/2/json/#", description="Топик для подписки")
    client_id: str = Field(default="meshtastic-telegram-bot", description="MQTT client ID")
    keepalive: int = Field(default=60, description="Keepalive интервал в секундах")
    qos: int = Field(default=1, description="QoS уровень подписки")
    
    @field_validator("qos")
    @classmethod
    def validate_qos(cls, v: int) -> int:
        """Валидация QoS: должен быть 0, 1 или 2."""
        if v not in (0, 1, 2):
            raise ValueError("QoS должен быть 0, 1 или 2")
        return v


class MQTTProxyTargetConfig(BaseSettings):
    """Конфигурация целевого MQTT сервера для прокси."""
    
    model_config = SettingsConfigDict(env_prefix="MQTT_PROXY_TARGET_")
    
    name: str = Field(description="Имя прокси-цели (для логирования)")
    host: str = Field(description="Хост целевого MQTT брокера")
    port: int = Field(default=1883, description="Порт целевого MQTT брокера")
    username: Optional[str] = Field(default=None, description="Имя пользователя")
    password: Optional[str] = Field(default=None, description="Пароль")
    topic_prefix: Optional[str] = Field(default=None, description="Префикс для топика (если нужен)")
    client_id: Optional[str] = Field(default=None, description="MQTT client ID (опционально)")
    enabled: bool = Field(default=True, description="Включен ли этот прокси")
    qos: int = Field(default=1, description="QoS уровень публикации")
    
    @field_validator("qos")
    @classmethod
    def validate_qos(cls, v: int) -> int:
        """Валидация QoS: должен быть 0, 1 или 2."""
        if v not in (0, 1, 2):
            raise ValueError("QoS должен быть 0, 1 или 2")
        return v


class TelegramConfig(BaseSettings):
    """Конфигурация Telegram бота."""
    
    model_config = SettingsConfigDict(env_prefix="TELEGRAM_")
    
    bot_token: str = Field(description="Токен Telegram бота")
    group_chat_id: Optional[int] = Field(default=None, description="ID группового чата")
    allowed_user_ids: Optional[List[int]] = Field(
        default=None,
        description="Список разрешенных user_id для личных сообщений (None = все)"
    )
    
    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, v: str | List[int] | None) -> List[int] | None:
        """
        Парсит список разрешенных user_id из строки или списка.
        
        Поддерживает формат: "123,456,789" или [123, 456, 789]
        
        Args:
            v: Значение из переменной окружения или конфигурации
            
        Returns:
            Список целых чисел или None
        """
        if v is None:
            return None
        
        if isinstance(v, list):
            return v
        
        if isinstance(v, str):
            # Удаляем пробелы и разбиваем по запятым
            v = v.strip()
            if not v:
                return None
            
            try:
                return [int(uid.strip()) for uid in v.split(",") if uid.strip()]
            except ValueError:
                raise ValueError(f"Некорректный формат allowed_user_ids: {v}")
        
        return None


class AppConfig(BaseSettings):
    """Основная конфигурация приложения."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__"  # Для вложенных конфигураций
    )
    
    # MQTT источник
    mqtt_source: MQTTBrokerConfig = Field(default_factory=MQTTBrokerConfig)
    
    # Telegram
    telegram: TelegramConfig = Field(description="Конфигурация Telegram бота")
    
    # MQTT прокси (список целей)
    # По умолчанию загружается одна цель из переменных окружения с префиксом MQTT_PROXY_TARGET_
    # Для множественных целей используйте метод load_proxy_targets_from_env()
    mqtt_proxy_targets: List[MQTTProxyTargetConfig] = Field(
        default_factory=list,
        description="Список целевых MQTT серверов для прокси"
    )
    
    # Логирование
    log_level: str = Field(default="INFO", description="Уровень логирования")
    log_format: str = Field(
        default="json",
        description="Формат логов: json или text"
    )
    
    @model_validator(mode="after")
    def load_proxy_targets(self) -> "AppConfig":
        """
        Загружает прокси-цели из переменных окружения.
        
        Поддерживает загрузку одной цели с префиксом MQTT_PROXY_TARGET_.
        Если заданы переменные окружения, но список пуст, пытается загрузить конфигурацию.
        """
        # Если уже есть цели, не перезаписываем
        if self.mqtt_proxy_targets:
            return self
        
        # Проверяем, есть ли переменные с префиксом MQTT_PROXY_TARGET_
        env_vars = {k: v for k, v in os.environ.items() if k.startswith("MQTT_PROXY_TARGET_")}
        
        if not env_vars:
            return self
        
        # Пробуем загрузить одну цель (базовая поддержка)
        # Для множественных целей можно расширить функционал позже
        try:
            target_config = MQTTProxyTargetConfig()
            if target_config.enabled and target_config.host:
                self.mqtt_proxy_targets = [target_config]
        except Exception:
            # Если не удалось загрузить, оставляем пустой список
            pass
        
        return self
    
    def setup_logging(self) -> None:
        """
        Настраивает структурированное логирование на основе конфигурации.
        
        Использует structlog для структурированного логирования с поддержкой
        JSON и текстового форматов.
        """
        # Устанавливаем уровень логирования для стандартного logging
        log_level = getattr(logging, self.log_level.upper(), logging.INFO)
        logging.basicConfig(level=log_level)
        
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]
        
        if self.log_format == "json":
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.append(structlog.processors.KeyValueRenderer())
        
        structlog.configure(
            processors=processors,
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )

