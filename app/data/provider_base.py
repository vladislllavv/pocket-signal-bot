"""
Абстрактный базовый класс для всех источников рыночных данных.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class MarketDataProvider(ABC):
    """
    Интерфейс провайдера данных.
    Каждый провайдер умеет подключаться, отключаться
    и возвращать OHLCV DataFrame.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Установить соединение (WebSocket / REST)."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Закрыть соединение."""
        ...

    @abstractmethod
    async def fetch_ohlcv(
        self,
        asset: str,
        timeframe: str = "1m",
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        Возвращает DataFrame с колонками:
        ['open', 'high', 'low', 'close', 'volume']
        Индекс — datetime.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Название провайдера (для логов)."""
        ...

    async def __aenter__(self) -> "MarketDataProvider":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()
