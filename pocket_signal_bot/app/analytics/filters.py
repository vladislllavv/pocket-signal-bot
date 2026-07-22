"""
Фильтры для отсеивания ложных сигналов и шума.
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
    Возвращает True, если волатильность достаточна для торговли.

    Идея: если ATR / цена < min_atr_ratio — рынок во флэте,
    сигналы не надёжны.

    min_atr_ratio = 0.001 означает, что ATR должен быть не менее 0.1% от цены.
    Для BTC это ~$1-2, для мелких пар можно увеличить.
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
    Возвращает True, если спред приемлем для торговли.
    max_spread_pct = 0.5% по умолчанию.
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
    Возвращает True, если текущий объём > min_volume_ratio от среднего.
    Низкий объём = низкая ликвидность = ложные движения.
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
    adx_period: int = 14,
    min_adx: float = 20.0,
) -> bool:
    """
    Фильтр силы тренда через ADX (если доступен).
    ADX < 20 — рынок без тренда, сигналы не надёжны.
    """
    import pandas_ta as ta

    if len(close) < adx_period * 2:
        return True  # пропускаем, если данных мало

    # ADX требует high, low, close. Используем close как high/low (приближение)
    adx = ta.adx(close, close, close, length=adx_period)
    if adx is None or adx.empty:
        return True

    adx_val = float(adx.iloc[-1, 0])
    return adx_val >= min_adx


def confluence_filter(
    buy_signals: int,
    total_indicators: int,
    min_ratio: float = 0.6,
) -> bool:
    """
    Фильтр конъюнктуры (confluence).
    Возвращает True, если доля индикаторов, подтверждающих сигнал,
    достаточна.
    """
    if total_indicators == 0:
        return False
    ratio = buy_signals / total_indicators
    return ratio >= min_ratio
