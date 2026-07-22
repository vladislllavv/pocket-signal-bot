"""
Агрегатор рыночных данных.
Пытается получить данные через Pocket Option WebSocket,
при недоступности — через Binance (CCXT).
Может быть расширен для Yahoo Finance, TradingView и т.д.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pandas as pd

from app.config import config
from app.data.binance_provider import BinanceProvider
from app.data.po_websocket import POWebSocketProvider
from app.data.provider_base import MarketDataProvider

logger = logging.getLogger(__name__)

# Активы по умолчанию для сканирования
DEFAULT_ASSETS: list[str] = [
    "EURUSD",
    "GBPUSD",
    "BTCUSD",
    "ETHUSD",
    "GOLD",
    "AAPL",
]


class MarketDataAggregator:
    """
    Агрегатор данных с automatic failover.
    Порядок выбора источника:
      1. Pocket Option WebSocket (основной)
      2. Binance / CCXT (резервный)

    Usage:
        aggregator = MarketDataAggregator()
        df = await aggregator.fetch("EURUSD", timeframe="1m")
    """

    def __init__(self) -> None:
        self._po: POWebSocketProvider | None = None
        self._binance: BinanceProvider | None = None
        self._active_provider: MarketDataProvider | None = None

    async def _ensure_providers(self) -> None:
        """Инициализация провайдеров."""
        if self._po is None:
            self._po = POWebSocketProvider()
        if self._binance is None:
            self._binance = BinanceProvider()

    async def fetch(
        self,
        asset: str,
        timeframe: str = "1m",
        limit: int = 100,
        prefer_po: bool = True,
    ) -> pd.DataFrame:
        """
        Получить OHLCV данные.

        Args:
            asset: Тикер актива (EURUSD, BTCUSD, ...)
            timeframe: 1m, 3m, 5m
            limit: Количество свечей
            prefer_po: Если True — сначала пробуем PO, затем Binance.
                       Если False — наоборот.
        """
        await self._ensure_providers()

        if prefer_po:
            providers: list[MarketDataProvider] = [self._po, self._binance]  # type: ignore
        else:
            providers = [self._binance, self._po]  # type: ignore

        last_error: Exception | None = None

        for provider in providers:
            try:
                await provider.connect()
                df = await provider.fetch_ohlcv(asset, timeframe, limit)
                if df is not None and not df.empty:
                    self._active_provider = provider
                    logger.info(
                        "Данные получены от %s для %s (%d свечей)",
                        provider.name, asset, len(df),
                    )
                    return df
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Провайдер %s не смог отдать %s: %s",
                    provider.name, asset, exc,
                )
                continue

        # Если ни один не сработал
        error_msg = (
            f"Не удалось получить данные для {asset} ни от одного провайдера. "
            f"Последняя ошибка: {last_error}"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    async def fetch_all(
        self,
        assets: list[str] | None = None,
        timeframe: str = "1m",
        limit: int = 100,
    ) -> dict[str, pd.DataFrame]:
        """
        Загрузить данные для всех указанных активов (параллельно).
        """
        assets = assets or DEFAULT_ASSETS
        await self._ensure_providers()

        results: dict[str, pd.DataFrame] = {}

        async def fetch_one(asset: str) -> tuple[str, pd.DataFrame | None]:
            try:
                df = await self.fetch(asset, timeframe, limit)
                return asset, df
            except Exception as exc:
                logger.error("Ошибка fetch_all для %s: %s", asset, exc)
                return asset, None

        tasks = [fetch_one(a) for a in assets]
        for asset, df in await asyncio.gather(*tasks):
            if df is not None and not df.empty:
                results[asset] = df

        logger.info(
            "Загружены данные для %d/%d активов",
            len(results), len(assets),
        )
        return results

    async def close(self) -> None:
        """Закрыть все соединения."""
        if self._po:
            await self._po.disconnect()
        if self._binance:
            await self._binance.disconnect()
        self._active_provider = None
        logger.info("MarketDataAggregator: все соединения закрыты")
