"""
Конфигурация приложения.
Загружает переменные окружения из .env файла и/или YAML файла.

Использует Pydantic Settings для валидации и загрузки из переменных окружения.
Поддерживает загрузку MQTT конфигурации из YAML файла с обратной совместимостью.
"""
import os
import sys
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# Загружаем переменные окружения из .env
load_dotenv()


def setup_logging(level: Optional[str] = None, format_string: Optional[str] = None) -> None:
    """
    Настройка логирования приложения.
    
    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Если не указан, берется из переменной окружения LOG_LEVEL или INFO.
        format_string: Формат строки логирования. Если не указан, используется стандартный.
    """
    log_level = level or os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = format_string or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Преобразуем строку уровня в константу logging
    numeric_level = getattr(logging, log_level, logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
        force=True,  # Перезаписываем существующую конфигурацию
    )


def setup_basic_logging() -> None:
    """
    Настраивает базовое логирование для отображения ошибок конфигурации.
    
    Используется до загрузки полной конфигурации, чтобы можно было логировать
    ошибки при инициализации AppConfig.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )


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
    reply_to_message_id: Optional[int] = Field(
        default=None,
        description="ID сообщения для ответа (для создания тредов в супергруппах)"
    )
    allowed_user_ids: Optional[List[int]] = Field(
        default=None,
        description="Список разрешенных user_id для личных сообщений (None = все)"
    )
    
    @field_validator("group_chat_id", mode="before")
    @classmethod
    def parse_group_chat_id(cls, v: str | int | None) -> int | None:
        """
        Парсит group_chat_id из строки или числа.
        
        Обрабатывает пустые строки как None.
        
        Args:
            v: Значение из переменной окружения или конфигурации
            
        Returns:
            Целое число или None
        """
        if v is None:
            return None
        
        if isinstance(v, int):
            return v
        
        if isinstance(v, str):
            v = v.strip()
            if not v or v.lower() in ("none", "null", ""):
                return None
            
            try:
                return int(v)
            except ValueError:
                raise ValueError(f"Некорректный формат group_chat_id: {v}")
        
        return None
    
    @field_validator("reply_to_message_id", mode="before")
    @classmethod
    def parse_reply_to_message_id(cls, v: str | int | None) -> int | None:
        """
        Парсит reply_to_message_id из строки или числа.
        
        Обрабатывает пустые строки как None.
        Используется для создания тредов (threads) в супергруппах Telegram.
        
        Args:
            v: Значение из переменной окружения или конфигурации
            
        Returns:
            Целое число или None
        """
        if v is None:
            return None
        
        if isinstance(v, int):
            return v
        
        if isinstance(v, str):
            v = v.strip()
            if not v or v.lower() in ("none", "null", ""):
                return None
            
            try:
                return int(v)
            except ValueError:
                raise ValueError(f"Некорректный формат reply_to_message_id: {v}")
        
        return None
    
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
    # Используем default_factory для автоматической загрузки из переменных окружения
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    
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
    
    @classmethod
    def load_from_yaml(cls, yaml_path: Optional[str] = None) -> "AppConfig":
        """
        Загружает конфигурацию из YAML файла с обратной совместимостью.
        
        Если YAML файл не найден или не содержит нужных настроек,
        используются значения из переменных окружения (.env).
        
        Args:
            yaml_path: Путь к YAML файлу. По умолчанию ищет 'mqtt_config.yaml' в корне проекта.
        
        Returns:
            Экземпляр AppConfig с загруженными настройками.
        """
        if not YAML_AVAILABLE:
            logging.warning("PyYAML не установлен. Используется только конфигурация из .env")
            return cls()
        
        if yaml_path is None:
            # Ищем mqtt_config.yaml в корне проекта
            yaml_path = Path("mqtt_config.yaml")
        else:
            yaml_path = Path(yaml_path)
        
        # Создаем базовую конфигурацию из .env (для обратной совместимости)
        config = cls()
        
        # Если YAML файл не существует, возвращаем конфигурацию из .env
        if not yaml_path.exists():
            logging.info(f"YAML файл {yaml_path} не найден. Используется конфигурация из .env")
            return config
        
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)
            
            if not yaml_data:
                logging.warning(f"YAML файл {yaml_path} пуст. Используется конфигурация из .env")
                return config
            
            # Загружаем MQTT source из YAML
            if "mqtt_source" in yaml_data:
                mqtt_source_data = yaml_data["mqtt_source"]
                # Обновляем конфигурацию, используя значения из YAML
                # Переменные окружения имеют приоритет (уже загружены в config)
                for key, value in mqtt_source_data.items():
                    if hasattr(config.mqtt_source, key) and not os.getenv(f"MQTT_SOURCE_{key.upper()}"):
                        setattr(config.mqtt_source, key, value)
                logging.info("Загружена конфигурация MQTT source из YAML")
            
            # Загружаем MQTT proxy targets из YAML
            if "mqtt_proxy_targets" in yaml_data:
                proxy_targets_data = yaml_data["mqtt_proxy_targets"]
                if isinstance(proxy_targets_data, list):
                    proxy_targets = []
                    for target_data in proxy_targets_data:
                        try:
                            # Создаем конфигурацию прокси-цели
                            target_config = MQTTProxyTargetConfig(**target_data)
                            if target_config.enabled:
                                proxy_targets.append(target_config)
                        except Exception as e:
                            logging.warning(f"Ошибка при загрузке прокси-цели из YAML: {e}")
                            continue
                    
                    if proxy_targets:
                        config.mqtt_proxy_targets = proxy_targets
                        logging.info(f"Загружено {len(proxy_targets)} прокси-целей из YAML")
            
        except yaml.YAMLError as e:
            logging.error(f"Ошибка при парсинге YAML файла {yaml_path}: {e}")
            logging.info("Используется конфигурация из .env")
        except Exception as e:
            logging.error(f"Ошибка при загрузке YAML файла {yaml_path}: {e}")
            logging.info("Используется конфигурация из .env")
        
        return config
    
    @model_validator(mode="after")
    def load_proxy_targets(self) -> "AppConfig":
        """
        Загружает прокси-цели из переменных окружения (для обратной совместимости).
        
        Поддерживает загрузку одной цели с префиксом MQTT_PROXY_TARGET_.
        Если заданы переменные окружения, но список пуст, пытается загрузить конфигурацию.
        Вызывается только если прокси-цели не были загружены из YAML.
        """
        # Если уже есть цели (например, из YAML), не перезаписываем
        if self.mqtt_proxy_targets:
            return self
        
        # Проверяем, есть ли переменные с префиксом MQTT_PROXY_TARGET_
        env_vars = {k: v for k, v in os.environ.items() if k.startswith("MQTT_PROXY_TARGET_")}
        
        if not env_vars:
            return self
        
        # Пробуем загрузить одну цель (базовая поддержка)
        # Для множественных целей используйте YAML файл
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
        Настраивает логирование на основе конфигурации.
        
        Использует стандартный модуль logging Python.
        """
        setup_logging(level=self.log_level)

