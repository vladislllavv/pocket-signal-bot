"""
Агрегатор рыночных данных.
Сначала пытается получить реальные данные (Binance),
при неудаче — генерирует демо-данные для демонстрации.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_ASSETS: list[str] = ["EURUSD", "BTCUSD", "ETHUSD", "GOLD", "AAPL"]


def _generate_demo_ohlcv(asset: str, n: int = 100) -> pd.DataFrame:
    """
    Генерирует синтетические OHLCV данные для демо-режима.
    Похоже на реальные рыночные движения.
    """
    np.random.seed(hash(asset) % (2**31))
    
    # Базовая цена для каждого актива
    base_prices = {
        "EURUSD": 1.08, "GBPUSD": 1.26, "BTCUSD": 65000,
        "ETHUSD": 3500, "GOLD": 2350, "AAPL": 210,
        "TSLA": 240, "SP500": 5300, "SILVER": 28,
    }
    base = base_prices.get(asset, 100.0)
    
    # Генерируем случайное блуждание с трендом
    returns = np.random.randn(n) * 0.005  # 0.5% волатильность
    # Иногда добавляем тренд
    trend = np.random.choice([-0.002, 0, 0.002]) 
    prices = base * (1 + np.cumsum(returns + trend))
    prices = np.maximum(prices, base * 0.5)  # не ниже 50% от базы
    
    close = prices
    high = close * (1 + abs(np.random.randn(n)) * 0.008)
    low = close * (1 - abs(np.random.randn(n)) * 0.008)
    open_p = close * (1 + np.random.randn(n) * 0.004)
    volume = np.random.rand(n) * 10000 + 1000
    
    df = pd.DataFrame({
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


class MarketDataAggregator:
    """
    Агрегатор данных. Если реальные данные недоступны — 
    использует демо-данные.
    """

    def __init__(self) -> None:
        self._use_demo = False

    async def fetch(
        self,
        asset: str,
        timeframe: str = "1m",
        limit: int = 100,
    ) -> pd.DataFrame:
        """Получить OHLCV данные (реальные или демо)."""
        # Сначала пробуем реальные данные
        if not self._use_demo:
            try:
                df = await self._fetch_real(asset, limit)
                if df is not None and not df.empty:
                    return df
            except Exception as exc:
                logger.warning(
                    "Реальные данные недоступны для %s: %s. Включаю демо-режим.",
                    asset, exc,
                )
                self._use_demo = True

        # Демо-данные
        logger.info("Генерирую демо-данные для %s", asset)
        df = _generate_demo_ohlcv(asset, n=limit)
        return df

    async def fetch_all(
        self,
        assets: list[str] | None = None,
        timeframe: str = "1m",
        limit: int = 100,
    ) -> dict[str, pd.DataFrame]:
        """Загрузить данные для всех активов (параллельно)."""
        assets = assets or DEFAULT_ASSETS
        results: dict[str, pd.DataFrame] = {}

        async def fetch_one(asset: str) -> tuple[str, pd.DataFrame | None]:
            try:
                df = await self.fetch(asset, timeframe, limit)
                return asset, df
            except Exception as exc:
                logger.error("Ошибка загрузки %s: %s", asset, exc)
                return asset, None

        tasks = [fetch_one(a) for a in assets]
        for asset, df in await asyncio.gather(*tasks):
            if df is not None and not df.empty:
                results[asset] = df

        logger.info("Загружены данные для %d/%d активов", len(results), len(assets))
        return results

    async def _fetch_real(self, asset: str, limit: int = 100) -> pd.DataFrame | None:
        """Пытается получить реальные данные через ccxt (Binance)."""
        try:
            import ccxt.async_support as ccxt
            
            symbol_map = {
                "BTCUSD": "BTC/USDT", "ETHUSD": "ETH/USDT",
                "EURUSD": "EUR/USDT", "GBPUSD": "GBP/USDT",
                "GOLD": "XAU/USDT", "AAPL": "AAPL/USD",
            }
            symbol = symbol_map.get(asset, asset + "/USDT")
            
            exchange = ccxt.binance({
                "enableRateLimit": True,
                "timeout": 5000,
            })
            
            raw = await exchange.fetch_ohlcv(symbol, timeframe="1m", limit=limit)
            await exchange.close()
            
            if not raw:
                return None
                
            df = pd.DataFrame(
                raw,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df = df.astype(float)
            logger.info("Реальные данные получены для %s (%d свечей)", asset, len(df))
            return df
            
        except Exception as exc:
            logger.debug("Реальные данные не получены для %s: %s", asset, exc)
            return None

    async def close(self) -> None:
        """Закрыть соединения."""
        pass
