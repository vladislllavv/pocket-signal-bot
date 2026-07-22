"""
Провайдер данных через Pocket Option WebSocket (демо-счёт).
Использует библиотеку A11ksa/API-Pocket-Option.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pandas as pd

from app.config import config

logger = logging.getLogger(__name__)

PO_ASSETS = [
    "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc",
    "BTCUSD_otc", "ETHUSD_otc",
    "GOLD_otc", "SILVER_otc",
    "AAPL_otc", "TSLA_otc",
]

SIMPLE_NAMES = {
    "EURUSD_otc": "EURUSD", "GBPUSD_otc": "GBPUSD",
    "BTCUSD_otc": "BTCUSD", "ETHUSD_otc": "ETHUSD",
    "GOLD_otc": "GOLD", "SILVER_otc": "SILVER",
    "AAPL_otc": "AAPL", "TSLA_otc": "TSLA",
}


class POProvider:
    """
    Провайдер, подключающийся к Pocket Option WebSocket (демо).
    Получает реальные свечи с платформы PO.
    """

    def __init__(self, ssid: str | None = None, is_demo: bool = True):
        self._ssid = ssid or config.PO_SSID
        self._is_demo = is_demo
        self._client: Any = None
        self._connected = False

    @property
    def name(self) -> str:
        return f"Pocket Option {'(demo)' if self._is_demo else '(live)'}"

    async def connect(self) -> bool:
        """Подключение к Pocket Option WebSocket."""
        if self._connected:
            return True

        if not self._ssid:
            logger.error("PO_SSID не задан!")
            return False

        try:
            from api_pocket.client import AsyncPocketOptionClient

            self._client = AsyncPocketOptionClient(
                ssid=self._ssid,
                is_demo=self._is_demo,
                enable_logging=False,
                auto_reconnect=False,
            )

            connected = await self._client.connect()
            if connected:
                self._connected = True
                logger.info("✅ PO WebSocket подключён (демо)")
                return True
            else:
                logger.error("❌ PO WebSocket: не удалось подключиться")
                return False

        except ImportError:
            logger.error("Библиотека api_pocket не установлена")
            return False
        except Exception as exc:
            logger.error("Ошибка подключения к PO: %s", exc)
            return False

    async def disconnect(self) -> None:
        """Отключение от WebSocket."""
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._connected = False

    async def fetch_ohlcv(
        self,
        asset: str = "EURUSD_otc",
        timeframe: str = "1m",
        limit: int = 100,
    ) -> pd.DataFrame | None:
        """Получить OHLCV свечи с Pocket Option."""
        if not self._connected or not self._client:
            return None

        tf_map = {"1m": 60, "3m": 180, "5m": 300}
        tf_seconds = tf_map.get(timeframe, 60)

        try:
            df = await self._client.get_candles_dataframe(
                asset=asset,
                timeframe=tf_seconds,
                count=limit,
            )

            if df is None or df.empty:
                return None

            required = {"open", "high", "low", "close", "volume"}
            if not required.issubset(df.columns):
                return None

            df = df[["open", "high", "low", "close", "volume"]]
            df = df.astype(float)

            logger.info("✅ PO: %s (%s) — %d свечей", asset, timeframe, len(df))
            return df

        except Exception as exc:
            logger.error("Ошибка получения свечей PO для %s: %s", asset, exc)
            return None

    async def fetch_all(
        self,
        assets: list[str] | None = None,
        timeframe: str = "1m",
        limit: int = 100,
    ) -> dict[str, pd.DataFrame]:
        """Получить данные для нескольких активов."""
        assets = assets or PO_ASSETS[:6]
        results: dict[str, pd.DataFrame] = {}

        for asset in assets:
            try:
                df = await self.fetch_ohlcv(asset, timeframe, limit)
                if df is not None and not df.empty:
                    simple_name = SIMPLE_NAMES.get(asset, asset.replace("_otc", ""))
                    results[simple_name] = df
            except Exception:
                pass

        logger.info("PO: загружены данные для %d/%d активов", len(results), len(assets))
        return results

    async def get_balance(self) -> dict | None:
        """Получить баланс демо-счёта."""
        if not self._connected or not self._client:
            return None
        try:
            balance = await self._client.get_balance()
            return {
                "balance": balance.balance,
                "currency": balance.currency,
                "is_demo": balance.is_demo,
            }
        except Exception:
            return None

    async def close(self) -> None:
        """Закрыть соединение."""
        await self.disconnect()
