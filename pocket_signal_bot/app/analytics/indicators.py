"""
Модуль индикаторов технического анализа.
Обёртка над pandas-ta с дополнительными фильтрами.
Все функции принимают pandas Series и возвращают скалярные значения
для последней завершённой свечи.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta


def compute_rsi(close: pd.Series, period: int = 14) -> float | None:
    """
    RSI (Relative Strength Index).
    Возвращает значение для последней свечи.
    > 70 — перекупленность (сигнал DOWN)
    < 30 — перепроданность (сигнал UP)
    """
    if len(close) < period + 1:
        return None
    rsi = ta.rsi(close, length=period)
    if rsi is None or rsi.empty:
        return None
    return float(rsi.iloc[-1])


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict[str, Any]:
    """
    MACD (Moving Average Convergence Divergence).
    Возвращает словарь:
      - histogram: значение гистограммы (последнее)
      - signal: 'bullish' если гистограмма > 0 и растёт, иначе 'bearish'
      - cross: 'up' | 'down' | None — пересечение линии MACD и сигнальной
    """
    if len(close) < slow + signal_period:
        return {"histogram": None, "signal": None, "cross": None}

    macd = ta.macd(close, fast=fast, slow=slow, signal=signal_period)
    if macd is None or macd.empty:
        return {"histogram": None, "signal": None, "cross": None}

    macd_line = macd.iloc[:, 0]
    signal_line = macd.iloc[:, 1]
    histogram = macd.iloc[:, 2]

    if len(histogram) < 2:
        return {"histogram": None, "signal": None, "cross": None}

    hist_val = float(histogram.iloc[-1])
    hist_prev = float(histogram.iloc[-2])

    # Определяем тренд гистограммы
    if hist_val > 0 and hist_val > hist_prev:
        trend = "bullish"
    elif hist_val < 0 and hist_val < hist_prev:
        trend = "bearish"
    elif hist_val > 0:
        trend = "weak_bullish"
    else:
        trend = "weak_bearish"

    # Пересечение MACD и сигнальной линии
    macd_curr = float(macd_line.iloc[-1])
    macd_prev = float(macd_line.iloc[-2])
    sig_curr = float(signal_line.iloc[-1])
    sig_prev = float(signal_line.iloc[-2])

    cross = None
    if macd_prev < sig_prev and macd_curr > sig_curr:
        cross = "up"  # бычье пересечение
    elif macd_prev > sig_prev and macd_curr < sig_curr:
        cross = "down"  # медвежье пересечение

    return {
        "histogram": hist_val,
        "signal": trend,
        "cross": cross,
    }


def compute_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> dict[str, Any]:
    """
    Bollinger Bands.
    Возвращает:
      - position: 'above_upper' | 'below_lower' | 'inside'
      - width: ширина канала (волатильность)
      - percent_b: %B индикатор
    """
    if len(close) < period + 1:
        return {"position": None, "width": None, "percent_b": None}

    bb = ta.bbands(close, length=period, std=std_dev)
    if bb is None or bb.empty:
        return {"position": None, "width": None, "percent_b": None}

    upper = bb.iloc[:, 0]
    middle = bb.iloc[:, 1]
    lower = bb.iloc[:, 2]

    last_close = float(close.iloc[-1])
    last_upper = float(upper.iloc[-1])
    last_lower = float(lower.iloc[-1])
    last_middle = float(middle.iloc[-1])

    if last_close > last_upper:
        position = "above_upper"
    elif last_close < last_lower:
        position = "below_lower"
    else:
        position = "inside"

    # %B = (close - lower) / (upper - lower)
    band_width = last_upper - last_lower
    percent_b = (last_close - last_lower) / band_width if band_width > 0 else 0.5

    return {
        "position": position,
        "width": band_width,
        "percent_b": round(float(percent_b), 4),
    }


def compute_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> dict[str, Any]:
    """
    Stochastic Oscillator.
    Возвращает:
      - k: %K значение
      - d: %D значение
      - signal: 'oversold' (< 20) | 'overbought' (> 80) | 'neutral'
      - cross: 'up' | 'down' | None
    """
    if len(close) < k_period + d_period:
        return {"k": None, "d": None, "signal": None, "cross": None}

    stoch = ta.stoch(high, low, close, k=k_period, d=d_period)
    if stoch is None or stoch.empty:
        return {"k": None, "d": None, "signal": None, "cross": None}

    k_line = stoch.iloc[:, 0]
    d_line = stoch.iloc[:, 1]

    if len(k_line) < 2:
        return {"k": None, "d": None, "signal": None, "cross": None}

    k_val = float(k_line.iloc[-1])
    d_val = float(d_line.iloc[-1])
    k_prev = float(k_line.iloc[-2])
    d_prev = float(d_line.iloc[-2])

    # Зона
    if k_val < 20 and d_val < 20:
        zone = "oversold"
    elif k_val > 80 and d_val > 80:
        zone = "overbought"
    else:
        zone = "neutral"

    # Пересечение
    cross = None
    if k_prev < d_prev and k_val > d_val:
        cross = "up"
    elif k_prev > d_prev and k_val < d_val:
        cross = "down"

    return {
        "k": round(k_val, 2),
        "d": round(d_val, 2),
        "signal": zone,
        "cross": cross,
    }


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> float | None:
    """
    ATR (Average True Range) — мера волатильности.
    """
    if len(close) < period + 1:
        return None
    atr = ta.atr(high, low, close, length=period)
    if atr is None or atr.empty:
        return None
    return float(atr.iloc[-1])


def compute_sma(close: pd.Series, period: int = 50) -> float | None:
    """Простое скользящее среднее."""
    if len(close) < period:
        return None
    sma = ta.sma(close, length=period)
    if sma is None or sma.empty:
        return None
    return float(sma.iloc[-1])


def compute_ema(close: pd.Series, period: int = 20) -> float | None:
    """Экспоненциальное скользящее среднее."""
    if len(close) < period:
        return None
    ema = ta.ema(close, length=period)
    if ema is None or ema.empty:
        return None
    return float(ema.iloc[-1])
