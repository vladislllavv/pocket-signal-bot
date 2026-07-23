"""
Провайдер данных через Pocket Option WebSocket.
Прямое подключение к Socket.IO серверу PO через SSID.
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
    Провайдер данных через WebSocket Pocket Option.
    Подключается напрямую к Socket.IO серверу PO используя SSID.
    """

    def __init__(self, ssid: str | None = None):
        self._ssid = ssid or config.PO_SSID
        self._ws = None
        self._connected = False
        self._sid = None
        self._ping_interval = 25
        self._last_pong = 0

    @property
    def name(self) -> str:
        return "Pocket Option (WebSocket)"

    async def connect(self) -> bool:
        """Подключение к Pocket Option через WebSocket."""
        if self._connected:
            return True

        if not self._ssid:
            logger.error("PO_SSID не задан!")
            return False

        try:
            import websockets

            uri = (
                f"wss://demo-api-eu.po.market/socket.io/"
                f"?token={self._ssid}&EIO=4&transport=websocket"
            )

            logger.info("Подключаюсь к Pocket Option WebSocket...")
            self._ws = await websockets.connect(
                uri, ping_interval=None, close_timeout=10, max_size=2**20,
            )

            msg = await self._ws.recv()
            if msg.startswith("0"):
                data = json.loads(msg[1:])
                self._sid = data.get("sid")
                self._ping_interval = data.get("pingInterval", 25) / 1000
                await self._ws.send("40")

                auth_packet = json.dumps(["auth", {"token": self._ssid, "name": "auth"}])
                await self._ws.send(f"42{auth_packet}")

                self._connected = True
                self._last_pong = time.time()
                asyncio.create_task(self._keep_alive())
                await asyncio.sleep(1)

                logger.info("✅ PO WebSocket подключён! SID=%s", self._sid)
                return True
            else:
                logger.error("PO: неожиданный ответ")
                return False

        except ImportError:
            logger.error("websockets не установлен")
            return False
        except Exception as exc:
            logger.error("Ошибка подключения PO: %s", exc)
            return False

    async def _keep_alive(self):
        while self._connected and self._ws:
            try:
                msg = await asyncio.wait_for(self._ws.recv(), timeout=30)
                if msg == "2":
                    await self._ws.send("3")
            except asyncio.TimeoutError:
                break
            except Exception:
                break

    async def disconnect(self) -> None:
        self._connected = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def fetch_ohlcv(
        self, asset: str = "EURUSD_otc", timeframe: str = "1m", limit: int = 100,
    ) -> pd.DataFrame | None:
        if not self._connected or not self._ws:
            return None

        tf_map = {"1m": 60, "3m": 180, "5m": 300}
        tf_seconds = tf_map.get(timeframe, 60)

        try:
            request_id = random.randint(100000, 999999)
            request = json.dumps(["candles", {
                "asset": asset, "timeframe": tf_seconds,
                "count": limit, "id": request_id,
            }])
            await self._ws.send(f"42{request}")

            candles_data = None
            start = time.time()
            while time.time() - start < 10:
                try:
                    msg = await asyncio.wait_for(self._ws.recv(), timeout=10)
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
                            event_name = data[0]
                            event_data = data[1]
                            if event_name == "candles":
                                candles_data = event_data
                                break
                    except (json.JSONDecodeError, IndexError):
                        continue

            if not candles_data:
                return None

            raw = candles_data.get("data") if isinstance(candles_data, dict) else candles_data
            if not raw or not isinstance(raw, list):
                return None

            rows = []
            for c in raw:
                if isinstance(c, dict):
                    rows.append({
                        "open": float(c.get("open", 0)),
                        "high": float(c.get("high", 0)),
                        "low": float(c.get("low", 0)),
                        "close": float(c.get("close", 0)),
                        "volume": float(c.get("volume", 0)),
                    })
                elif isinstance(c, (list, tuple)) and len(c) >= 5:
                    rows.append({
                        "open": float(c[1]), "high": float(c[2]),
                        "low": float(c[3]), "close": float(c[4]),
                        "volume": float(c[5]) if len(c) > 5 else 0,
                    })

            if not rows:
                return None

            df = pd.DataFrame(rows)
            df = df.astype(float)
            logger.info("✅ PO: %s (%s) — %d свечей", asset, timeframe, len(df))
            return df

        except Exception as exc:
            logger.error("Ошибка PO свечей для %s: %s", asset, exc)
            return None

    async def fetch_all(
        self, assets: list[str] | None = None,
        timeframe: str = "1m", limit: int = 100,
    ) -> dict[str, pd.DataFrame]:
        assets = assets or PO_ASSETS[:6]
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

    async def get_balance(self) -> dict | None:
        return {"balance": 10000.0, "currency": "USD", "is_demo": True}

    async def close(self) -> None:
        await self.disconnect()
