"""
WebSocket клиент для Pocket Option через неофициальную библиотеку pocketoptionapi.

ВАЖНО: Использование WebSocket для парсинга котировок PO может нарушать
их ToS. Данный код предоставлен для образовательных целей.
Рекомендуется использовать с осторожностью и прокси.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pandas as pd

from app.data.provider_base import MarketDataProvider
from app.config import config

logger = logging.getLogger(__name__)


class POWebSocketProvider(MarketDataProvider):
    """
    Провайдер данных через Pocket Option WebSocket API.

    Использует библиотеку pocketoptionapi.
    Требует email/password или SSID для аутентификации.
    """

    def __init__(self) -> None:
        self._api: Any = None  # pocketoptionapi object
        self._connected = False
        self._candle_buffer: dict[str, list[dict[str, Any]]] = {}

    @property
    def name(self) -> str:
        return "Pocket Option WS"

    async def connect(self) -> None:
        if self._connected:
            return

        try:
            from pocketoptionapi import PocketOptionAPI
        except ImportError:
            raise ImportError(
                "Установи pocketoptionapi: pip install pocketoptionapi"
            )

        self._api = PocketOptionAPI(
            email=config.PO_EMAIL,
            password=config.PO_PASSWORD,
            # ssid=config.PO_SSID,  # альтернатива
        )

        try:
            await self._api.connect()
            self._connected = True
            logger.info("PO WebSocket: подключён успешно")
        except Exception as exc:
            logger.error("PO WebSocket: ошибка подключения: %s", exc)
            # Пробуем через SSID
            if config.PO_SSID:
                try:
                    self._api = PocketOptionAPI(ssid=config.PO_SSID)
                    await self._api.connect()
                    self._connected = True
                    logger.info("PO WebSocket: подключён через SSID")
                except Exception as exc2:
                    logger.error("PO WebSocket: SSID тоже не сработал: %s", exc2)
                    raise
            else:
                raise

    async def disconnect(self) -> None:
        if self._api:
            try:
                await self._api.disconnect()
            except Exception:
                pass
            self._api = None
        self._connected = False
        logger.info("PO WebSocket: отключён")

    async def subscribe_candles(
        self,
        asset: str,
        timeframe: int = 60,  # секунды (60 = 1m, 180 = 3m, 300 = 5m)
    ) -> None:
        """Подписаться на свечи актива в реальном времени."""
        if not self._api:
            raise RuntimeError("PO WebSocket не подключён")

        try:
            await self._api.subscribe_to_candles(asset, timeframe)
            logger.info("PO: подписка на %s (tf=%ds)", asset, timeframe)
        except Exception as exc:
            logger.error("PO: ошибка подписки на %s: %s", asset, exc)
            raise

    async def fetch_ohlcv(
        self,
        asset: str,
        timeframe: str = "1m",
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        Получает исторические свечи через PO API.
        timeframe: '1m', '3m', '5m'
        """
        if not self._api:
            raise RuntimeError("PO WebSocket не подключён")

        tf_map = {"1m": 60, "3m": 180, "5m": 300}
        tf_seconds = tf_map.get(timeframe, 60)

        try:
            # В библиотеке pocketoptionapi обычно есть метод get_candles
            candles = await self._api.get_candles(asset, tf_seconds, limit)
        except AttributeError:
            # Если метода нет — используем альтернативный
            logger.warning(
                "PO: get_candles не найден, пробуем альтернативный метод"
            )
            candles = await self._fetch_candles_fallback(asset, tf_seconds, limit)
        except Exception as exc:
            logger.error("PO: ошибка получения свечей %s: %s", asset, exc)
            raise

        if not candles:
            return pd.DataFrame()

        df = pd.DataFrame(candles)
        # Нормализация колонок
        df.rename(
            columns={
                "time": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            },
            inplace=True,
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
        df.set_index("timestamp", inplace=True)
        df = df.astype(float)

        logger.debug(
            "PO: %s (%s) — %d свечей, close=%.5f",
            asset, timeframe, len(df), df["close"].iloc[-1],
        )
        return df

    async def _fetch_candles_fallback(
        self,
        asset: str,
        timeframe: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        """
        Fallback: пробуем получить свечи через прямой WebSocket запрос.
        """
        # Заглушка — в реальном проекте здесь был бы прямой WS-запрос
        logger.warning("Fallback fetch candles — заглушка")
        return []

    async def listen_real_time(
        self,
        assets: list[str],
        timeframe: int = 60,
        callback=None,
    ) -> None:
        """
        Слушает свечи в реальном времени для списка активов.
        При поступлении новой свечи вызывает callback.
        """
        if not self._api:
            raise RuntimeError("PO WebSocket не подключён")

        for asset in assets:
            await self.subscribe_candles(asset, timeframe)

        logger.info("PO: запущен слушатель для %d активов", len(assets))

        # Цикл прослушивания
        while self._connected:
            try:
                # pocketoptionapi обычно предоставляет очередь сообщений
                # или on_candle колбэк
                msg = await self._api.get_next_message(timeout=5)
                if msg and callback:
                    await callback(msg)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.error("PO: ошибка в listen_real_time: %s", exc)
                await asyncio.sleep(5)
