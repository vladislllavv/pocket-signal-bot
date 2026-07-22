"""
Фильтры для отсеивания ложных сигналов и шума.
Без pandas-ta — только numpy/pandas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def volatility_filter(
    close: pd.Series,
    atr_value: float | None,
    atr_period: int = 14,
    min_atr_ratio: float = 0.001,
) -> bool:
    """
    Фильтр волатильности.
    True = волатильность достаточна для торговли.
    False = рынок во флэте, сигналы не генерируем.
    """
    if atr_value is None or len(close) < 2:
        return False

    last_price = float(close.iloc[-1])
    if last_price == 0:
        return False

    atr_ratio = atr_value / last_price
    return atr_ratio >= min_atr_ratio


def spread_filter(bid: float, ask: float, max_spread_pct: float = 0.005) -> bool:
    """
    Фильтр спреда.
    True = спред приемлем.
    """
    if bid <= 0 or ask <= 0:
        return False
    spread_pct = abs(ask - bid) / ((ask + bid) / 2)
    return spread_pct <= max_spread_pct


def volume_filter(
    volume: pd.Series,
    volume_ma_period: int = 20,
    min_volume_ratio: float = 0.5,
) -> bool:
    """
    Фильтр объёмов.
    True = объём достаточен (не ниже 50% от среднего).
    """
    if len(volume) < volume_ma_period + 1:
        return False

    current_volume = float(volume.iloc[-1])
    avg_volume = float(volume.iloc[-volume_ma_period:].mean())

    if avg_volume == 0:
        return False

    return current_volume >= avg_volume * min_volume_ratio


def trend_strength_filter(
    close: pd.Series,
    period: int = 20,
    min_strength: float = 0.005,
) -> bool:
    """
    Фильтр силы тренда через наклон SMA.
    True = тренд есть. False = флэт.
    """
    if len(close) < period:
        return True

    sma_short = close.tail(period).mean()
    sma_long = close.tail(period * 2).mean() if len(close) >= period * 2 else close.mean()

    if sma_long == 0:
        return True

    slope = abs(sma_short - sma_long) / sma_long
    return slope >= min_strength


def confluence_filter(
    buy_signals: int,
    total_indicators: int,
    min_ratio: float = 0.6,
) -> bool:
    """
    Фильтр конъюнктуры (confluence).
    True = достаточно индикаторов подтверждают сигнал.
    """
    if total_indicators == 0:
        return False
    ratio = buy_signals / total_indicators
    return ratio >= min_ratio
