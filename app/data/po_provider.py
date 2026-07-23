"""
Провайдер данных — Yahoo Finance.
Без WebSocket, без лишних зависимостей.
Работает мгновенно.
"""

from __future__ import annotations

import asyncio
import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Активы для сканирования
TRADING_ASSETS = ["EURUSD", "GBPUSD", "BTCUSD", "ETHUSD", "GOLD", "AAPL"]

# Маппинг к Yahoo Finance
YAHOO_TICKERS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "GOLD": "GC=F",
    "AAPL": "AAPL",
}


class POProvider:
    """Провайдер рыночных данных через Yahoo Finance."""

    def __init__(self, ssid: str | None = None):
        self._connected = True

    @property
    def name(self) -> str:
        return "Yahoo Finance"

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        pass

    async def fetch_ohlcv(self, asset: str = "EURUSD", timeframe: str = "1m", limit: int = 100) -> pd.DataFrame | None:
        """Получить свечи через Yahoo Finance."""
        try:
            import yfinance as yf

            ticker = YAHOO_TICKERS.get(asset, f"{asset}=X")

            def _get():
                stock = yf.Ticker(ticker)
                df = stock.history(period="1d", interval="1m")
                if df.empty or len(df) < 10:
                    df = stock.history(period="5d", interval="5m")
                return df

            df = await asyncio.to_thread(_get)

            if df is None or df.empty:
                logger.warning("Нет данных для %s", asset)
                return None

            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            })
            df = df[["open", "high", "low", "close", "volume"]]
            df = df.tail(min(limit, len(df))).astype(float)

            logger.info("✅ %s: %d свечей", asset, len(df))
            return df

        except Exception as exc:
            logger.error("Ошибка %s: %s", asset, exc)
            return None

    async def fetch_all(self, assets: list[str] | None = None, timeframe: str = "1m", limit: int = 100) -> dict[str, pd.DataFrame]:
        """Получить данные для всех активов."""
        assets = assets or TRADING_ASSETS
        results = {}

        for asset in assets:
            try:
                df = await self.fetch_ohlcv(asset, timeframe, limit)
                if df is not None and not df.empty:
                    results[asset] = df
                await asyncio.sleep(0.2)
            except Exception as exc:
                logger.error("Ошибка %s: %s", asset, exc)

        logger.info("Загружено %d/%d активов", len(results), len(assets))
        return results

    async def get_balance(self) -> dict | None:
        return None

    async def close(self) -> None:
        pass
