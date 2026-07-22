"""
Модуль индикаторов технического анализа.
Чистый pandas/numpy — БЕЗ pandas-ta.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> float | None:
    """RSI (Relative Strength Index) через pandas."""
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    if rsi.empty or rsi.isna().all():
        return None
    return float(rsi.iloc[-1])


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict:
    """MACD через EMA."""
    if len(close) < slow + signal_period:
        return {"histogram": None, "signal": None, "cross": None}
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    if len(histogram) < 2:
        return {"histogram": None, "signal": None, "cross": None}

    hist_val = float(histogram.iloc[-1])
    hist_prev = float(histogram.iloc[-2])

    if hist_val > 0 and hist_val > hist_prev:
        trend = "bullish"
    elif hist_val < 0 and hist_val < hist_prev:
        trend = "bearish"
    elif hist_val > 0:
        trend = "weak_bullish"
    else:
        trend = "weak_bearish"

    macd_curr = float(macd_line.iloc[-1])
    macd_prev = float(macd_line.iloc[-2])
    sig_curr = float(signal_line.iloc[-1])
    sig_prev = float(signal_line.iloc[-2])

    cross = None
    if macd_prev < sig_prev and macd_curr > sig_curr:
        cross = "up"
    elif macd_prev > sig_prev and macd_curr < sig_curr:
        cross = "down"

    return {"histogram": hist_val, "signal": trend, "cross": cross}


def compute_bollinger_bands(
    close: pd.Series, period: int = 20, std_dev: float = 2.0
) -> dict:
    """Bollinger Bands."""
    if len(close) < period + 1:
        return {"position": None, "width": None, "percent_b": None}
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std

    last_close = float(close.iloc[-1])
    last_upper = float(upper.iloc[-1])
    last_lower = float(lower.iloc[-1])

    if last_close > last_upper:
        position = "above_upper"
    elif last_close < last_lower:
        position = "below_lower"
    else:
        position = "inside"

    band_width = last_upper - last_lower
    percent_b = (last_close - last_lower) / band_width if band_width > 0 else 0.5

    return {"position": position, "width": band_width, "percent_b": round(float(percent_b), 4)}


def compute_stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series,
    k_period: int = 14, d_period: int = 3,
) -> dict:
    """Stochastic Oscillator."""
    if len(close) < k_period + d_period:
        return {"k": None, "d": None, "signal": None, "cross": None}

    low_min = low.rolling(window=k_period).min()
    high_max = high.rolling(window=k_period).max()
    k_line = 100 * (close - low_min) / (high_max - low_min).replace(0, np.nan)
    d_line = k_line.rolling(window=d_period).mean()

    if len(k_line) < 2:
        return {"k": None, "d": None, "signal": None, "cross": None}

    k_val = float(k_line.iloc[-1])
    d_val = float(d_line.iloc[-1])
    k_prev = float(k_line.iloc[-2])
    d_prev = float(d_line.iloc[-2])

    if k_val < 20 and d_val < 20:
        zone = "oversold"
    elif k_val > 80 and d_val > 80:
        zone = "overbought"
    else:
        zone = "neutral"

    cross = None
    if k_prev < d_prev and k_val > d_val:
        cross = "up"
    elif k_prev > d_prev and k_val < d_val:
        cross = "down"

    return {"k": round(k_val, 2), "d": round(d_val, 2), "signal": zone, "cross": cross}


def compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> float | None:
    """ATR (Average True Range)."""
    if len(close) < period + 1:
        return None
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    if atr.empty or atr.isna().all():
        return None
    return float(atr.iloc[-1])
