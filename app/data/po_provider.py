"""
Провайдер данных через Pocket Option WebSocket (демо).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any

import pandas as pd

from app.config import config

logger = logging.getLogger(__name__)

PO_ASSETS = [
    "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc",
    "BTCUSD_otc", "ETHUSD_otc",
    "GOLD_otc", "AAPL_otc",
]

SIMPLE_NAMES = {
    "EURUSD_otc": "EURUSD", "GBPUSD_otc": "GBPUSD",
    "BTCUSD_otc": "BTCUSD", "ETHUSD_otc": "ETHUSD",
    "GOLD_otc": "GOLD", "AAPL_otc": "AAPL",
}

# Пробуем разные серверы PO
PO_SERVERS = [
    "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://demo-api-eu.po.market/socket.io/",
    "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
]


class POProvider:
    """Провайдер данных через WebSocket Pocket Option (демо-счёт)."""

    def __init__(self, ssid: str | None = None):
        self._ssid = ssid or config.PO_SSID
        self._ws = None
        self._connected = False
        self._ping_task = None

    @property
    def name(self) -> str:
        return "Pocket Option (демо)"

    async def connect(self) -> bool:
        """Подключение к Pocket Option WebSocket."""
        if self._connected:
            return True
        if not self._ssid:
            logger.error("PO_SSID не задан!")
            return False

        try:
            import websockets
        except ImportError:
            logger.error("websockets не установлен")
            return False

        # Пробуем подключиться к разным серверам
        last_error = ""
        uri = f"wss://demo-api-eu.po.market/socket.io/?token={self._ssid}&EIO=4&transport=websocket"

        try:
            logger.info("Подключаюсь к PO WebSocket...")

            self._ws = await websockets.connect(
                uri,
                ping_interval=None,
                close_timeout=15,
                max_size=10*1024*1024,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                origin="https://pocketoption.com",
                extra_headers={
                    "Cookie": f"u_sclid={self._ssid}",
                },
            )

            logger.info("✅ WebSocket открыт, жду приветствие...")

            # Читаем все доступные сообщения
            messages = []
            for _ in range(20):
                try:
                    msg = await asyncio.wait_for(self._ws.recv(), timeout=3)
                    messages.append(msg)
                    logger.info("PO -> %s", msg[:120])
                except asyncio.TimeoutError:
                    break

            if not messages:
                logger.error("PO: нет ответа от сервера")
                await self.disconnect()
                return False

            # Анализируем первое сообщение
            first = messages[0]
            if first.startswith("0"):
                # Socket.IO - отправляем 40
                await self._ws.send("40")
                await asyncio.sleep(1)

                # Отправляем авторизацию
                auth = json.dumps(["auth", {"token": self._ssid, "name": "auth"}])
                await self._ws.send(f"42{auth}")
                logger.info("PO: авторизация отправлена")
                await asyncio.sleep(2)

                # Читаем ответы на авторизацию
                for _ in range(10):
                    try:
                        msg = await asyncio.wait_for(self._ws.recv(), timeout=2)
                        logger.info("PO auth -> %s", msg[:120])
                    except asyncio.TimeoutError:
                        break

                self._connected = True
                logger.info("✅ PO: подключён и авторизован!")
                self._ping_task = asyncio.create_task(self._ping_loop())
                return True

            elif "auth" in str(first).lower() or "success" in str(first).lower():
                # Уже авторизованы
                self._connected = True
                logger.info("✅ PO: уже авторизован!")
                self._ping_task = asyncio.create_task(self._ping_loop())
                return True

            else:
                logger.error("PO: неизвестный ответ: %s", first[:100])
                await self.disconnect()
                return False

        except asyncio.TimeoutError:
            logger.error("PO: таймаут подключения")
            await self.disconnect()
            return False
        except Exception as exc:
            logger.error("PO: ошибка: %s", exc)
            await self.disconnect()
            return False

    async def _ping_loop(self):
        """Поддержание соединения."""
        while self._connected and self._ws:
            try:
                msg = await asyncio.wait_for(self._ws.recv(), timeout=30)
                if msg == "2":
                    await self._ws.send("3")
            except asyncio.TimeoutError:
                logger.warning("PO: таймаут ping")
                break
            except Exception as exc:
                logger.warning("PO: ошибка ping: %s", exc)
                break

    async def disconnect(self) -> None:
        self._connected = False
        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def fetch_ohlcv(self, asset="EURUSD_otc", timeframe="1m", limit=100):
        if not self._connected or not self._ws:
            return None

        tf_map = {"1m": 60, "3m": 180, "5m": 300}
        tf_seconds = tf_map.get(timeframe, 60)

        try:
            req_id = random.randint(10000, 99999)
            payload = json.dumps(["candles", {
                "asset": asset,
                "timeframe": tf_seconds,
                "count": limit,
                "id": req_id,
            }])
            await self._ws.send(f"42{payload}")
            logger.info("PO: запрос свечей %s", asset)

            # Собираем ответ
            start = time.time()
            while time.time() - start < 15:
                try:
                    msg = await asyncio.wait_for(self._ws.recv(), timeout=15)
                except asyncio.TimeoutError:
                    break
                if not msg:
                    continue
                if msg == "2":
                    await self._ws.send("3")
                    continue
                if msg.startswith("42"):
                    try:
                        data = json.loads(msg[2:])
                        if isinstance(data, list) and len(data) >= 2:
                            event, event_data = data[0], data[1]
                            if event in ("candles", "candle", "candles_data"):
                                return self._parse_candles(event_data, asset, limit)
                            if isinstance(event_data, dict):
                                inner = event_data.get("data") or event_data.get("candles")
                                if isinstance(inner, list) and len(inner) > 0:
                                    first = inner[0]
                                    if isinstance(first, dict) and ("open" in first or "o" in first or "c" in first):
                                        return self._parse_candles(event_data, asset, limit)
                    except (json.JSONDecodeError, IndexError):
                        continue

            logger.warning("PO: нет данных для %s", asset)
            return None

        except Exception as exc:
            logger.error("PO ошибка для %s: %s", asset, exc)
            return None

    def _parse_candles(self, candles_data, asset, limit):
        """Парсит свечи из ответа PO."""
        raw = candles_data.get("data") if isinstance(candles_data, dict) else candles_data
        if not isinstance(raw, list) or len(raw) == 0:
            return None

        rows = []
        for c in raw:
            if isinstance(c, dict):
                rows.append({
                    "open": float(c.get("open", c.get("o", 0))),
                    "high": float(c.get("high", c.get("h", 0))),
                    "low": float(c.get("low", c.get("l", 0))),
                    "close": float(c.get("close", c.get("c", 0))),
                    "volume": float(c.get("volume", c.get("v", 0))),
                })
            elif isinstance(c, (list, tuple)) and len(c) >= 5:
                rows.append({
                    "open": float(c[1]), "high": float(c[2]),
                    "low": float(c[3]), "close": float(c[4]),
                    "volume": float(c[5]) if len(c) > 5 else 0,
                })

        if not rows:
            return None

        df = pd.DataFrame(rows).astype(float).tail(limit)
        logger.info("✅ PO: %s — %d свечей", asset, len(df))
        return df

    async def fetch_all(self, assets=None, timeframe="1m", limit=100):
        assets = assets or PO_ASSETS[:4]
        results = {}
        for asset in assets:
            try:
                df = await self.fetch_ohlcv(asset, timeframe, limit)
                if df is not None and not df.empty:
                    name = SIMPLE_NAMES.get(asset, asset.replace("_otc", ""))
                    results[name] = df
                await asyncio.sleep(0.5)
            except Exception:
                pass
        return results

    async def get_balance(self):
        return {"balance": 10000.0, "currency": "USD", "is_demo": True}

    async def close(self):
        await self.disconnect()
