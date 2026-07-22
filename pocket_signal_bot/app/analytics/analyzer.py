#!/usr/bin/env python3
"""
SignalAnalyzer — ядро аналитической системы.

Принимает OHLCV-данные, вычисляет конъюнктуру (схождение)
индикаторов RSI, MACD, Bollinger Bands, Stochastic + ATR-фильтр.

Генерирует сигнал только при достаточной уверенности (confluence score).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.indicators import (
    compute_atr,
    compute_bollinger_bands,
    compute_macd,
    compute_rsi,
    compute_stochastic,
)
from app.analytics.filters import volatility_filter
from app.config import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class IndicatorSnapshot:
    """Срез показаний всех индикаторов на момент анализа."""
    rsi: float | None = None
    rsi_signal: str | None = None  # overbought | oversold | neutral

    macd_histogram: float | None = None
    macd_signal: str | None = None
    macd_cross: str | None = None

    bb_position: str | None = None
    bb_width: float | None = None
    bb_percent_b: float | None = None

    stoch_k: float | None = None
    stoch_d: float | None = None
    stoch_signal: str | None = None
    stoch_cross: str | None = None

    atr: float | None = None
    atr_ratio: float | None = None

    # Цена закрытия последней свечи
    last_close: float | None = None


@dataclass
class SignalResult:
    """Результат анализа — готовый торговый сигнал или None."""
    asset: str
    direction: str  # UP | DOWN
    expiry: str  # 1m | 3m | 5m
    entry_price: float
    confidence: float  # 0.0 — 1.0
    confluence_score: float
    indicators: IndicatorSnapshot = field(default_factory=IndicatorSnapshot)
    is_valid: bool = False
    reason: str | None = None


# ---------------------------------------------------------------------------
# SignalAnalyzer
# ---------------------------------------------------------------------------

class SignalAnalyzer:
    """
    Анализатор рыночных данных.

    Usage:
        analyzer = SignalAnalyzer(asset="EURUSD")
        df = pd.DataFrame({...})  # OHLCV данные
        signal = analyzer.analyze(df)

    Логика:
        1. Вычисляем все индикаторы
        2. Каждый индикатор голосует UP / DOWN / нейтрально
        3. Считаем confluence score (доля совпавших голосов)
        4. Если score >= порога и ATR-фильтр пройден → сигнал
    """

    # Веса индикаторов в confluence (сумма не обязана быть = 1,
    # используется нормализация)
    INDICATOR_WEIGHTS: dict[str, float] = {
        "rsi": 0.25,
        "macd": 0.30,
        "bollinger": 0.20,
        "stochastic": 0.25,
    }

    def __init__(
        self,
        asset: str,
        expiry: str = "1m",
        min_confluence: float | None = None,
    ):
        self.asset = asset
        self.expiry = expiry
        self.min_confluence = min_confluence or config.MIN_CONFLUENCE_SCORE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, ohlcv: pd.DataFrame) -> SignalResult:
        """
        Главный метод. Принимает DataFrame с колонками:
        ['open', 'high', 'low', 'close', 'volume']
        Возвращает SignalResult.
        """
        # Валидация входных данных
        if not self._validate_data(ohlcv):
            return SignalResult(
                asset=self.asset,
                direction="NONE",
                expiry=self.expiry,
                entry_price=0.0,
                confidence=0.0,
                confluence_score=0.0,
                is_valid=False,
                reason="Недостаточно данных для анализа",
            )

        close = ohlcv["close"].astype(float)
        high = ohlcv["high"].astype(float)
        low = ohlcv["low"].astype(float)
        volume = ohlcv["volume"].astype(float)

        # 1. Снимок индикаторов
        snap = self._compute_indicators(high, low, close, volume)

        # 2. Фильтр волатильности (ATR)
        vol_ok = self._check_volatility(close, snap)
        if not vol_ok:
            return SignalResult(
                asset=self.asset,
                direction="NONE",
                expiry=self.expiry,
                entry_price=snap.last_close or 0.0,
                confidence=0.0,
                confluence_score=0.0,
                indicators=snap,
                is_valid=False,
                reason="Недостаточная волатильность (флэт)",
            )

        # 3. Голосование индикаторов
        up_votes, down_votes, total_weight = self._vote(snap)

        # 4. Confluence score
        if up_votes > down_votes:
            direction = "UP"
            confluence_score = up_votes / total_weight if total_weight > 0 else 0.0
        elif down_votes > up_votes:
            direction = "DOWN"
            confluence_score = down_votes / total_weight if total_weight > 0 else 0.0
        else:
            # Ничья — нет сигнала
            return SignalResult(
                asset=self.asset,
                direction="NONE",
                expiry=self.expiry,
                entry_price=snap.last_close or 0.0,
                confidence=0.0,
                confluence_score=0.0,
                indicators=snap,
                is_valid=False,
                reason="Нет явного перевеса индикаторов",
            )

        # 5. Проверка порога уверенности
        if confluence_score < self.min_confluence:
            return SignalResult(
                asset=self.asset,
                direction="NONE",
                expiry=self.expiry,
                entry_price=snap.last_close or 0.0,
                confidence=0.0,
                confluence_score=confluence_score,
                indicators=snap,
                is_valid=False,
                reason=f"Confluence score {confluence_score:.2f} ниже порога {self.min_confluence}",
            )

        # 6. УСПЕХ — валидный сигнал
        # Конвертируем confluence_score в confidence с учётом
        # дополнительных факторов
        confidence = self._compute_confidence(confluence_score, snap)

        logger.info(
            "СИГНАЛ | %s | %s | expiry=%s | entry=%.5f | conf=%.2f%% | score=%.2f",
            self.asset, direction, self.expiry,
            snap.last_close, confidence * 100, confluence_score,
        )

        return SignalResult(
            asset=self.asset,
            direction=direction,
            expiry=self.expiry,
            entry_price=snap.last_close or 0.0,
            confidence=round(confidence, 4),
            confluence_score=round(confluence_score, 4),
            indicators=snap,
            is_valid=True,
        )

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _validate_data(self, df: pd.DataFrame) -> bool:
        """Проверка, что данных достаточно для анализа."""
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            logger.warning("DataFrame не содержит всех OHLCV колонок")
            return False
        if len(df) < 30:  # минимум для индикаторов
            logger.warning("Слишком мало свечей: %d", len(df))
            return False
        if df["close"].isna().any():
            logger.warning("DataFrame содержит NaN в close")
            return False
        return True

    def _compute_indicators(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
    ) -> IndicatorSnapshot:
        """Вычисляет все индикаторы и возвращает снимок."""
        snap = IndicatorSnapshot()
        snap.last_close = float(close.iloc[-1])

        # --- RSI ---
        rsi_val = compute_rsi(close)
        if rsi_val is not None:
            snap.rsi = rsi_val
            if rsi_val > 70:
                snap.rsi_signal = "overbought"
            elif rsi_val < 30:
                snap.rsi_signal = "oversold"
            else:
                snap.rsi_signal = "neutral"

        # --- MACD ---
        macd = compute_macd(close)
        snap.macd_histogram = macd.get("histogram")
        snap.macd_signal = macd.get("signal")
        snap.macd_cross = macd.get("cross")

        # --- Bollinger Bands ---
        bb = compute_bollinger_bands(close)
        snap.bb_position = bb.get("position")
        snap.bb_width = bb.get("width")
        snap.bb_percent_b = bb.get("percent_b")

        # --- Stochastic ---
        stoch = compute_stochastic(high, low, close)
        snap.stoch_k = stoch.get("k")
        snap.stoch_d = stoch.get("d")
        snap.stoch_signal = stoch.get("signal")
        snap.stoch_cross = stoch.get("cross")

        # --- ATR ---
        atr_val = compute_atr(high, low, close)
        if atr_val is not None and snap.last_close and snap.last_close > 0:
            snap.atr = atr_val
            snap.atr_ratio = atr_val / snap.last_close

        return snap

    def _check_volatility(self, close: pd.Series, snap: IndicatorSnapshot) -> bool:
        """Проверка, что волатильность достаточна для торговли."""
        return volatility_filter(close, snap.atr)

    def _vote(self, snap: IndicatorSnapshot) -> tuple[float, float, float]:
        """
        Голосование индикаторов.

        Returns:
            (up_weight, down_weight, total_weight)
        """
        up_weight = 0.0
        down_weight = 0.0
        total_weight = 0.0

        # --- RSI голос ---
        w = self.INDICATOR_WEIGHTS["rsi"]
        total_weight += w
        if snap.rsi_signal == "oversold":
            up_weight += w
        elif snap.rsi_signal == "overbought":
            down_weight += w
        # нейтральный RSI — не голосует

        # --- MACD голос ---
        w = self.INDICATOR_WEIGHTS["macd"]
        total_weight += w
        if snap.macd_cross == "up":
            up_weight += w
        elif snap.macd_cross == "down":
            down_weight += w
        elif snap.macd_signal and "bullish" in snap.macd_signal:
            up_weight += w * 0.5  # мягкий сигнал
        elif snap.macd_signal and "bearish" in snap.macd_signal:
            down_weight += w * 0.5

        # --- Bollinger Bands голос ---
        w = self.INDICATOR_WEIGHTS["bollinger"]
        total_weight += w
        if snap.bb_position == "below_lower":
            # Цена ниже нижней полосы — перепроданность → отскок UP
            up_weight += w
        elif snap.bb_position == "above_upper":
            # Цена выше верхней полосы — перекупленность → откат DOWN
            down_weight += w
        # Если внутри — используем %B
        elif snap.bb_percent_b is not None:
            if snap.bb_percent_b < 0.2:
                up_weight += w * 0.5
            elif snap.bb_percent_b > 0.8:
                down_weight += w * 0.5

        # --- Stochastic голос ---
        w = self.INDICATOR_WEIGHTS["stochastic"]
        total_weight += w
        if snap.stoch_signal == "oversold" and snap.stoch_cross == "up":
            up_weight += w  # пересечение в зоне перепроданности — сильный UP
        elif snap.stoch_signal == "overbought" and snap.stoch_cross == "down":
            down_weight += w  # пересечение в зоне перекупленности — сильный DOWN
        elif snap.stoch_signal == "oversold":
            up_weight += w * 0.6
        elif snap.stoch_signal == "overbought":
            down_weight += w * 0.6

        return up_weight, down_weight, total_weight

    def _compute_confidence(
        self,
        confluence_score: float,
        snap: IndicatorSnapshot,
    ) -> float:
        """
        Финальный рассчёт уверенности сигнала.
        Базовая = confluence_score.
        Модификаторы:
          - Если RSI экстремальный (< 25 или > 75) → +5%
          - Если MACD пересечение + BB экстремум → +10%
          - Если Stochastic и RSI совпадают → +5%
        """
        confidence = confluence_score

        # Бонус за экстремальный RSI
        if snap.rsi is not None:
            if snap.rsi < 25 or snap.rsi > 75:
                confidence = min(1.0, confidence + 0.05)

        # Бонус за совпадение MACD cross + BB
        if snap.macd_cross is not None and snap.bb_position is not None:
            if snap.macd_cross == "up" and snap.bb_position == "below_lower":
                confidence = min(1.0, confidence + 0.10)
            elif snap.macd_cross == "down" and snap.bb_position == "above_upper":
                confidence = min(1.0, confidence + 0.10)

        # Бонус за совпадение RSI + Stochastic
        if snap.rsi_signal and snap.stoch_signal:
            if snap.rsi_signal == snap.stoch_signal:
                confidence = min(1.0, confidence + 0.05)

        # Не допускаем > 1.0
        return min(confidence, 1.0)

    # ------------------------------------------------------------------
    # Batch анализ (много активов)
    # ------------------------------------------------------------------

    def analyze_batch(
        self,
        data_map: dict[str, pd.DataFrame],
    ) -> dict[str, SignalResult]:
        """
        Анализирует несколько активов за раз.
        data_map: { "EURUSD": DataFrame, "BTCUSD": DataFrame, ... }
        Returns: { "EURUSD": SignalResult, ... }
        """
        results: dict[str, SignalResult] = {}
        for asset, df in data_map.items():
            try:
                # Создаём временный анализатор для каждого актива
                sub = SignalAnalyzer(asset=asset, expiry=self.expiry)
                results[asset] = sub.analyze(df)
            except Exception as exc:
                logger.exception("Ошибка анализа %s: %s", asset, exc)
                results[asset] = SignalResult(
                    asset=asset,
                    direction="NONE",
                    expiry=self.expiry,
                    entry_price=0.0,
                    confidence=0.0,
                    confluence_score=0.0,
                    is_valid=False,
                    reason=str(exc),
                )
        return results
