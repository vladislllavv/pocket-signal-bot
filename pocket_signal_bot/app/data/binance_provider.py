"""
Провайдер данных Binance (REST + WebSocket).
Используется как основной источник для крипто-пар
и как fallback, если Pocket Option WebSocket недоступен.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import ccxt.async_support as ccxt

from app.data.provider_base import MarketDataProvider

logger = logging.getLogger(__name__)

# Маппинг наших названий активов к тикерам Binance
ASSET_MAP: dict[str, str] = {
    "BTCUSD": "BTC/USDT",
    "ETHUSD": "ETH/USDT",
    "EURUSD": "EUR/USDT",  # на Binance есть только фьючерсы
    "GBPUSD": "GBP/USDT",
    "AAPL": "AAPL/USD",  # токенизированные акции
    "TSLA": "TSLA/USD",
    "SP500": "SPX/USD",
    "GOLD": "XAU/USDT",
    "SILVER": "XAG/USDT",
}

TIMEFRAME_MAP: dict[str, str] = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
}


class BinanceProvider(MarketDataProvider):
    """
    Провайдер через CCXT (Binance).
    Поддержка асинхронных запросов.
    """

    def __init__(self) -> None:
        self._exchange: ccxt.binance | None = None
        self._connected = False

    @property
    def name(self) -> str:
        return "Binance (CCXT)"

    async def connect(self) -> None:
        if self._connected:
            return
        self._exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        self._connected = True
        logger.info("BinanceProvider: подключён")

    async def disconnect(self) -> None:
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
        self._connected = False
        logger.info("BinanceProvider: отключён")

    async def fetch_ohlcv(
        self,
        asset: str,
        timeframe: str = "1m",
        limit: int = 100,
    ) -> pd.DataFrame:
        if not self._exchange:
            raise RuntimeError("BinanceProvider не подключён. Вызови connect()")

        symbol = ASSET_MAP.get(asset, asset)
        tf = TIMEFRAME_MAP.get(timeframe, "1m")

        try:
            raw = await self._exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
        except ccxt.BadSymbol:
            logger.warning("Binance: символ %s не найден, пробуем с /USDT", symbol)
            # Fallback: если нет точного совпадения, пробуем /USDT
            base = asset.replace("USD", "").replace("USDT", "")
            symbol = f"{base}/USDT"
            raw = await self._exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
        except Exception as exc:
            logger.error("Binance fetch_ohlcv ошибка для %s: %s", asset, exc)
            raise

        df = pd.DataFrame(
            raw,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        df = df.astype(float)

        logger.debug(
            "Binance: %s (%s) — %d свечей, последняя close=%.5f",
            asset, tf, len(df), df["close"].iloc[-1],
        )
        return df

    async def fetch_multiple(
        self,
        assets: list[str],
        timeframe: str = "1m",
        limit: int = 100,
    ) -> dict[str, pd.DataFrame]:
        """Загрузить данные для нескольких активов параллельно."""
        import asyncio

        async def fetch_one(asset: str) -> tuple[str, pd.DataFrame]:
            try:
                df = await self.fetch_ohlcv(asset, timeframe, limit)
                return asset, df
            except Exception as exc:
                logger.error("Ошибка загрузки %s: %s", asset, exc)
                return asset, pd.DataFrame()

        tasks = [fetch_one(a) for a in assets]
        results = await asyncio.gather(*tasks)

        return {asset: df for asset, df in results if not df.empty}
