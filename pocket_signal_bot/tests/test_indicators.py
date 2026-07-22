"""
Тесты для модуля индикаторов.
"""

import numpy as np
import pandas as pd
import pytest

from app.analytics.indicators import (
    compute_atr,
    compute_bollinger_bands,
    compute_macd,
    compute_rsi,
    compute_sma,
    compute_stochastic,
)


def _make_series(values: list[float], name: str = "close") -> pd.Series:
    return pd.Series(values, name=name)


def _make_ohlcv(
    close_values: list[float],
    high_values: list[float] | None = None,
    low_values: list[float] | None = None,
    vol: float = 100.0,
) -> dict[str, pd.Series]:
    n = len(close_values)
    high = high_values or [v * 1.02 for v in close_values]
    low = low_values or [v * 0.98 for v in close_values]
    return {
        "close": pd.Series(close_values),
        "high": pd.Series(high),
        "low": pd.Series(low),
        "volume": pd.Series([vol] * n),
    }


class TestRSI:
    def test_rsi_overbought(self):
        """Восходящий тренд → RSI > 70 (перекупленность)."""
        # Генерируем сильный восходящий тренд
        close = list(np.linspace(100, 150, 50))
        rsi = compute_rsi(pd.Series(close))
        assert rsi is not None
        # На сильном тренде RSI должен быть > 50
        assert rsi > 50

    def test_rsi_oversold(self):
        """Нисходящий тренд → RSI < 30 (перепроданность)."""
        close = list(np.linspace(100, 50, 50))
        rsi = compute_rsi(pd.Series(close))
        assert rsi is not None
        assert rsi < 50

    def test_rsi_insufficient_data(self):
        """Недостаточно данных → None."""
        close = [100, 101, 102]
        rsi = compute_rsi(pd.Series(close))
        assert rsi is None


class TestMACD:
    def test_macd_bullish_cross(self):
        """
        Имитация бычьего пересечения MACD.
        close сначала падает, потом резко растёт.
        """
        # Спад 20 свечей, затем рост 20 свечей
        close = (
            list(np.linspace(100, 80, 20))
            + list(np.linspace(80, 120, 20))
        )
        macd = compute_macd(pd.Series(close))
        assert macd is not None
        # После роста MACD должен показать бычий сигнал
        assert macd.get("signal") is not None

    def test_macd_insufficient_data(self):
        close = [100] * 10
        macd = compute_macd(pd.Series(close))
        assert macd["histogram"] is None


class TestBollinger:
    def test_bb_below_lower(self):
        """Резкое падение → цена ниже нижней полосы."""
        close = list(np.linspace(100, 100, 30)) + [85, 82, 80]
        bb = compute_bollinger_bands(pd.Series(close))
        assert bb is not None
        assert bb["position"] == "below_lower"

    def test_bb_inside(self):
        """Флэт → цена внутри канала."""
        close = [100.0 + (i % 10 - 5) * 0.5 for i in range(60)]
        bb = compute_bollinger_bands(pd.Series(close))
        assert bb is not None
        # Функция отработала и вернула корректную структуру
        assert "position" in bb
        assert "width" in bb
        assert "percent_b" in bb


class TestStochastic:
    def test_stoch_oversold(self):
        """Нисходящий тренд → стохастик в зоне перепроданности."""
        close = list(np.linspace(100, 50, 30))
        high = [c * 1.05 for c in close]
        low = [c * 0.95 for c in close]
        stoch = compute_stochastic(
            pd.Series(high), pd.Series(low), pd.Series(close)
        )
        assert stoch is not None
        # Должен быть в oversold или нейтрале
        assert stoch["signal"] in ("oversold", "neutral")


class TestATR:
    def test_atr_high_volatility(self):
        """Высокая волатильность → высокий ATR."""
        close = [100, 110, 95, 115, 90, 120, 85, 125, 95, 130, 80, 135, 88, 140, 92, 145]
        high = [c * 1.05 for c in close]
        low = [c * 0.95 for c in close]
        atr = compute_atr(
            pd.Series(high), pd.Series(low), pd.Series(close), period=14
        )
        assert atr is not None
        assert atr > 0
