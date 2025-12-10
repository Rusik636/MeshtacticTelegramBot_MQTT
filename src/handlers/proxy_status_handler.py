"""
Обработчик статуса прокси-брокеров.

Получает информацию о состоянии подключений к прокси-брокерам.
"""

import logging
from typing import List, Optional

from src.service.mqtt_proxy_service import MQTTProxyService


logger = logging.getLogger(__name__)


class ProxyStatusHandler:
    """Получает информацию о статусе прокси-брокеров для команд бота."""

    def __init__(self, proxy_service: Optional[MQTTProxyService] = None):
        """
        Сохраняет ссылку на прокси-сервис.

        Args:
            proxy_service: Сервис MQTT прокси (опционально)
        """
        self.proxy_service = proxy_service

    def get_status_info(self) -> List[str]:
        """
        Возвращает краткую информацию о статусе прокси-брокеров.

        Returns:
            Список строк с краткой информацией о статусе
        """
        status_info = []

        if not self.proxy_service:
            status_info.append("MQTT прокси: не инициализирован")
            return status_info

        targets = self.proxy_service._targets
        if not targets:
            status_info.append("MQTT прокси: цели не настроены")
            return status_info

        connected_count = sum(1 for t in targets if t._connected)
        status_info.append(
            f"MQTT прокси: {len(targets)} целей (подключено: {connected_count})"
        )

        return status_info

    def get_detailed_info(self) -> List[str]:
        """
        Возвращает детальную информацию о каждом прокси-брокере.

        Returns:
            Список строк с детальной информацией о каждом брокере
        """
        info_parts = []

        if not self.proxy_service:
            info_parts.append("MQTT прокси: не инициализирован")
            return info_parts

        targets = self.proxy_service._targets
        if not targets:
            info_parts.append("MQTT прокси: цели не настроены")
            return info_parts

        info_parts.append(f"MQTT прокси целей: {len(targets)}")
        for target in targets:
            status = "подключен" if target._connected else "не подключен"
            info_parts.append(
                f"  - {target.config.name} ({target.config.host}:{target.config.port}): {status}"
            )

        return info_parts
