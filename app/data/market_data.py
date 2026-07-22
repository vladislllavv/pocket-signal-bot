"""
Агрегатор рыночных данных.
Реальные данные: Yahoo Finance → Binance (CCXT) → Демо (последний шанс)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_ASSETS: list[str] = ["EURUSD", "BTCUSD", "ETHUSD", "GOLD", "AAPL"]

# Маппинг наших тикеров → тикеры Yahoo Finance
YAHOO_TICKERS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "AAPL": "AAPL",
    "TSLA": "TSLA",
    "SP500": "^GSPC",
}


class MarketDataAggregator:
    """Агрегатор с реальными данными от Yahoo Finance + Binance."""

    def __init__(self) -> None:
        pass

    async def fetch(
        self,
        asset: str,
        timeframe: str = "1m",
        limit: int = 100,
    ) -> pd.DataFrame:
        # 1. Yahoo Finance
        try:
            df = await self._fetch_yahoo(asset, limit)
            if df is not None and not df.empty:
                return df
        except Exception as exc:
            logger.warning("Yahoo не сработал для %s: %s", asset, exc)

        # 2. Binance (CCXT)
        try:
            df = await self._fetch_binance(asset, limit)
            if df is not None and not df.empty:
                return df
        except Exception as exc:
            logger.warning("Binance не сработал для %s: %s", asset, exc)

        # 3. Демо (последний шанс)
        logger.warning("Все источники недоступны для %s. Генерирую демо.", asset)
        return self._generate_demo_ohlcv(asset, limit)

    async def fetch_all(
        self,
        assets: list[str] | None = None,
        timeframe: str = "1m",
        limit: int = 100,
    ) -> dict[str, pd.DataFrame]:
        assets = assets or DEFAULT_ASSETS
        results: dict[str, pd.DataFrame] = {}

        async def fetch_one(asset: str) -> tuple[str, pd.DataFrame | None]:
            try:
                df = await self.fetch(asset, timeframe, limit)
                return asset, df
            except Exception as exc:
                logger.error("Ошибка загрузки %s: %s", asset, exc)
                return asset, self._generate_demo_ohlcv(asset, limit)

        tasks = [fetch_one(a) for a in assets]
        for asset, df in await asyncio.gather(*tasks):
            if df is not None and not df.empty:
                results[asset] = df

        logger.info("Загружены данные для %d/%d активов", len(results), len(assets))
        return results

    async def _fetch_yahoo(self, asset: str, limit: int = 100) -> pd.DataFrame | None:
        """Получить данные через Yahoo Finance."""
        try:
            import yfinance as yf

            ticker = YAHOO_TICKERS.get(asset)
            if not ticker:
                logger.warning("Нет Yahoo тикера для %s", asset)
                return None

            # Yahoo не поддерживает асинхронно, запускаем в потоке
            def _get_data():
                stock = yf.Ticker(ticker)
                # Берём последние данные (1 день с интервалом 1м)
                df = stock.history(period="1d", interval="1m")
                if df.empty:
                    # Если 1м нет — берём 5 дней по 5м
                    df = stock.history(period="5d", interval="5m")
                return df

            df = await asyncio.to_thread(_get_data)

            if df is None or df.empty:
                return None

            # Нормализуем колонки
            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            })
            df = df[["open", "high", "low", "close", "volume"]]
            df = df.tail(limit)
            df = df.astype(float)

            logger.info("✅ Yahoo: %s (%d свечей)", asset, len(df))
            return df

        except ImportError:
            logger.warning("yfinance не установлен")
            return None
        except Exception as exc:
            logger.debug("Yahoo ошибка для %s: %s", asset, exc)
            return None

    async def _fetch_binance(self, asset: str, limit: int = 100) -> pd.DataFrame | None:
        """Получить данные через Binance (CCXT)."""
        try:
            import ccxt.async_support as ccxt

            symbol_map = {
                "BTCUSD": "BTC/USDT", "ETHUSD": "ETH/USDT",
                "EURUSD": "EUR/USDT", "GBPUSD": "GBP/USDT",
                "GOLD": "XAU/USDT",
            }
            symbol = symbol_map.get(asset)
            if not symbol:
                return None

            exchange = ccxt.binance({
                "enableRateLimit": True,
                "timeout": 5000,
            })
            raw = await exchange.fetch_ohlcv(symbol, timeframe="1m", limit=limit)
            await exchange.close()

            if not raw:
                return None

            df = pd.DataFrame(
                raw, columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df = df.astype(float)
            logger.info("✅ Binance: %s (%d свечей)", asset, len(df))
            return df

        except Exception as exc:
            logger.debug("Binance ошибка для %s: %s", asset, exc)
            return None

    def _generate_demo_ohlcv(self, asset: str, n: int = 100) -> pd.DataFrame:
        """Генерация демо-данных на случай отсутствия реальных."""
        np.random.seed(hash(asset) % (2**31))
        base_prices = {
            "EURUSD": 1.08, "GBPUSD": 1.26, "BTCUSD": 65000,
            "ETHUSD": 3500, "GOLD": 2350, "AAPL": 210,
        }
        base = base_prices.get(asset, 100.0)
        returns = np.random.randn(n) * 0.005
        trend = np.random.choice([-0.002, 0, 0.002])
        prices = base * (1 + np.cumsum(returns + trend))
        prices = np.maximum(prices, base * 0.5)

        df = pd.DataFrame({
            "open": prices * (1 + np.random.randn(n) * 0.004),
            "high": prices * (1 + abs(np.random.randn(n)) * 0.008),
            "low": prices * (1 - abs(np.random.randn(n)) * 0.008),
            "close": prices,
            "volume": np.random.rand(n) * 10000 + 1000,
        })
        return df

    async def close(self) -> None:
        pass
