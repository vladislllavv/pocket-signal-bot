"""
Тесты для SignalAnalyzer.
"""

import numpy as np
import pandas as pd
import pytest

from app.analytics.analyzer import SignalAnalyzer, SignalResult


def _make_ohlcv_data(
    n: int = 100,
    trend: str = "up",
    volatility: float = 0.02,
) -> pd.DataFrame:
    """
    Генерирует синтетические OHLCV данные для тестов.

    Args:
        n: количество свечей
        trend: 'up' | 'down' | 'flat' | 'bounce'
        volatility: волатильность (доля от цены)
    """
    np.random.seed(42)

    if trend == "up":
        prices = np.linspace(100, 120, n) + np.random.randn(n) * 2
    elif trend == "down":
        prices = np.linspace(120, 100, n) + np.random.randn(n) * 2
    elif trend == "flat":
        prices = np.ones(n) * 100 + np.random.randn(n) * 1
    elif trend == "bounce":
        # Резкое падение, затем отскок
        prices = np.concatenate([
            np.linspace(100, 80, 15),
            np.linspace(80, 95, 25),
        ])
        n = len(prices)
    else:
        prices = np.random.randn(n) * 5 + 100

    close = prices
    high = prices * (1 + volatility * abs(np.random.randn(n)))
    low = prices * (1 - volatility * abs(np.random.randn(n)))
    open_prices = prices + np.random.randn(n) * 1
    volume = np.ones(n) * 1000 + np.random.randn(n) * 100

    return pd.DataFrame({
        "open": open_prices,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestSignalAnalyzer:
    def test_up_trend_signal(self):
        """Восходящий тренд → должен быть UP сигнал."""
        df = _make_ohlcv_data(n=100, trend="up")
        analyzer = SignalAnalyzer(asset="EURUSD", expiry="3m", min_confluence=0.5)
        result = analyzer.analyze(df)
        # Должен быть сигнал UP (может быть NONE если индикаторы не сошлись)
        assert result.direction in ("UP", "NONE")
        if result.is_valid:
            assert result.direction == "UP"
            assert result.confidence > 0.5

    def test_down_trend_signal(self):
        """Нисходящий тренд → должен быть DOWN сигнал."""
        df = _make_ohlcv_data(n=100, trend="down")
        analyzer = SignalAnalyzer(asset="EURUSD", expiry="3m", min_confluence=0.5)
        result = analyzer.analyze(df)
        assert result.direction in ("DOWN", "NONE")
        if result.is_valid:
            assert result.direction == "DOWN"

    def test_flat_market_no_signal(self):
        """Флэт → не должно быть сигнала (фильтр волатильности)."""
        df = _make_ohlcv_data(n=100, trend="flat")
        analyzer = SignalAnalyzer(asset="EURUSD", expiry="3m", min_confluence=0.5)
        result = analyzer.analyze(df)
        # Во флэте сигнал должен быть невалидным
        assert not result.is_valid or result.direction == "NONE"

    def test_insufficient_data(self):
        """Мало данных → невалидный сигнал."""
        df = _make_ohlcv_data(n=5, trend="up")
        analyzer = SignalAnalyzer(asset="EURUSD")
        result = analyzer.analyze(df)
        assert not result.is_valid
        assert result.reason is not None

    def test_missing_columns(self):
        """Нет нужных колонок → невалидный сигнал."""
        df = pd.DataFrame({"a": [1, 2, 3]})
        analyzer = SignalAnalyzer(asset="EURUSD")
        result = analyzer.analyze(df)
        assert not result.is_valid

    def test_bounce_signal(self):
        """Отскок от низа → UP сигнал."""
        df = _make_ohlcv_data(trend="bounce")
        analyzer = SignalAnalyzer(asset="EURUSD", expiry="3m", min_confluence=0.4)
        result = analyzer.analyze(df)
        # После падения и начала отскока вероятность UP сигнала выше
        assert result.direction in ("UP", "NONE")

    def test_batch_analysis(self):
        """Пакетный анализ нескольких активов."""
        data_map = {
            "EURUSD": _make_ohlcv_data(trend="up"),
            "BTCUSD": _make_ohlcv_data(trend="down"),
            "FLAT": _make_ohlcv_data(trend="flat"),
        }
        analyzer = SignalAnalyzer(asset="dummy", expiry="3m")
        results = analyzer.analyze_batch(data_map)
        assert len(results) == 3
        for asset, result in results.items():
            assert isinstance(result, SignalResult)
            assert result.asset == asset
