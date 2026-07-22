"""
AI Predictor — модуль машинного обучения для усиления сигналов.

Использует XGBoost для предсказания направления движения цены.
Обучается на синтетических данных при первом запуске,
затем дообучается на реальных результатах сделок.

Архитектура:
  1. Feature Engineering → индикаторы + их производные
  2. XGBoost Classifier → P(UP) / P(DOWN)
  3. Confidence Boost → корректировка финальной уверенности сигнала

Всё работает сразу после деплоя — предобученная модель на синтетике.
"""

from __future__ import annotations

import io
import logging
import os
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from app.analytics.analyzer import IndicatorSnapshot
from app.config import config

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "xgboost_model.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"


class AIPredictor:
    """
    AI-предсказатель направления цены.

    Использует XGBoost для анализа комбинации индикаторов
    и выдаёт вероятность движения UP/DOWN.

    Пример:
        predictor = AIPredictor()
        predictor.load_or_init()
        prob_up = predictor.predict(snapshot)  # 0.0 — 1.0
    """

    def __init__(self) -> None:
        self.model: Any = None
        self.scaler: StandardScaler | None = None
        self.is_trained = False
        self.feature_names: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_or_init(self) -> None:
        """
        Загрузить существующую модель или инициализировать на синтетике.
        Вызывается при старте бота.
        """
        if MODEL_PATH.exists() and SCALER_PATH.exists():
            try:
                self._load_model()
                logger.info("AI модель загружена из %s", MODEL_PATH)
                return
            except Exception as exc:
                logger.warning("Ошибка загрузки модели: %s. Обучаю заново.", exc)

        logger.info("AI: обучение на синтетических данных...")
        self._train_synthetic()
        self._save_model()
        logger.info("AI: синтетическая модель обучена и сохранена")

    def predict(self, snapshot: IndicatorSnapshot) -> float:
        """
        Предсказать вероятность UP движения.

        Args:
            snapshot: IndicatorSnapshot с показаниями индикаторов

        Returns:
            float 0.0 — 1.0 (вероятность UP)
        """
        if not self.is_trained or self.model is None:
            return 0.5  # нейтрально, если модель не готова

        features = self._extract_features(snapshot)
        if features is None:
            return 0.5

        try:
            # Масштабирование
            if self.scaler:
                features_scaled = self.scaler.transform(features.reshape(1, -1))
            else:
                features_scaled = features.reshape(1, -1)

            # Предсказание вероятности
            prob = self.model.predict_proba(features_scaled)[0]
            # prob[0] — P(DOWN), prob[1] — P(UP)
            prob_up = float(prob[1])
            return prob_up

        except Exception as exc:
            logger.debug("AI predict error: %s", exc)
            return 0.5

    def get_confidence_multiplier(self, snapshot: IndicatorSnapshot) -> float:
        """
        Возвращает множитель уверенности на основе AI.

        Returns:
            0.8 — 1.2 (умножается на confluence_score)
        """
        prob_up = self.predict(snapshot)

        # Определяем силу сигнала AI
        # Если AI сильно уверен — усиливаем сигнал
        if prob_up > 0.80:
            return 1.20
        elif prob_up > 0.65:
            return 1.10
        elif prob_up < 0.20:
            return 1.20  # сильная уверенность в DOWN
        elif prob_up < 0.35:
            return 1.10
        else:
            return 1.0  # нейтрально — не влияем

    def get_ai_direction(self, snapshot: IndicatorSnapshot) -> str | None:
        """
        Возвращает направление по мнению AI.
        'UP', 'DOWN' или None (неуверен).
        """
        prob_up = self.predict(snapshot)
        if prob_up > 0.65:
            return "UP"
        elif prob_up < 0.35:
            return "DOWN"
        return None

    def retrain(self, df_trades: pd.DataFrame) -> None:
        """
        Дообучение модели на реальных данных.

        Args:
            df_trades: DataFrame с колонками
                ['rsi', 'macd_hist', 'bb_position_enc', 'stoch_k',
                 'stoch_d', 'atr_ratio', 'result']
                result: 1 — UP выиграл, 0 — DOWN выиграл
        """
        if len(df_trades) < 50:
            logger.warning("AI: недостаточно данных для дообучения (%d < 50)", len(df_trades))
            return

        try:
            X = df_trades.drop(columns=["result"])
            y = df_trades["result"].values

            # Масштабирование
            if self.scaler is None:
                self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)

            # Дообучение
            if self.model is not None:
                self.model.fit(X_scaled, y, xgb_model=self.model)
            else:
                from xgboost import XGBClassifier
                self.model = XGBClassifier(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.1,
                    use_label_encoder=False,
                    eval_metric="logloss",
                    random_state=42,
                )
                self.model.fit(X_scaled, y)

            self.is_trained = True
            self._save_model()
            logger.info("AI: модель дообучена на %d примерах", len(df_trades))

        except Exception as exc:
            logger.error("AI: ошибка дообучения: %s", exc)

    # ------------------------------------------------------------------
    # Feature Engineering
    # ------------------------------------------------------------------

    def _extract_features(self, snap: IndicatorSnapshot) -> np.ndarray | None:
        """
        Преобразует IndicatorSnapshot в вектор признаков для модели.

        Признаки:
          - rsi (нормализованный)
          - macd_histogram
          - macd_cross_enc (0=none, 1=up, 2=down)
          - bb_position_enc (0=inside, 1=below, 2=above)
          - bb_percent_b
          - stoch_k
          - stoch_d
          - stoch_signal_enc (0=neutral, 1=oversold, 2=overbought)
          - stoch_cross_enc (0=none, 1=up, 2=down)
          - atr_ratio
        """
        if snap.last_close is None:
            return None

        # RSI — нормализуем к [0, 1]
        rsi_norm = (snap.rsi / 100.0) if snap.rsi is not None else 0.5

        # MACD histogram
        macd_hist = snap.macd_histogram if snap.macd_histogram is not None else 0.0

        # MACD cross encoding
        macd_cross_map = {None: 0, "up": 1, "down": 2}
        macd_cross_enc = macd_cross_map.get(snap.macd_cross, 0)

        # BB position encoding
        bb_pos_map = {"inside": 0, "below_lower": 1, "above_upper": 2}
        bb_pos_enc = bb_pos_map.get(snap.bb_position, 0)

        # BB %B
        bb_pct = snap.bb_percent_b if snap.bb_percent_b is not None else 0.5

        # Stochastic
        stoch_k = (snap.stoch_k / 100.0) if snap.stoch_k is not None else 0.5
        stoch_d = (snap.stoch_d / 100.0) if snap.stoch_d is not None else 0.5

        stoch_sig_map = {"neutral": 0, "oversold": 1, "overbought": 2}
        stoch_sig_enc = stoch_sig_map.get(snap.stoch_signal, 0)

        stoch_cross_map = {None: 0, "up": 1, "down": 2}
        stoch_cross_enc = stoch_cross_map.get(snap.stoch_cross, 0)

        # ATR ratio
        atr_ratio = snap.atr_ratio if snap.atr_ratio is not None else 0.001

        features = np.array([
            rsi_norm,
            macd_hist,
            macd_cross_enc,
            bb_pos_enc,
            bb_pct,
            stoch_k,
            stoch_d,
            stoch_sig_enc,
            stoch_cross_enc,
            atr_ratio,
        ], dtype=np.float32)

        self.feature_names = [
            "rsi_norm", "macd_hist", "macd_cross", "bb_pos",
            "bb_pct", "stoch_k", "stoch_d", "stoch_sig",
            "stoch_cross", "atr_ratio",
        ]

        return features

    # ------------------------------------------------------------------
    # Обучение на синтетике
    # ------------------------------------------------------------------

    def _train_synthetic(self) -> None:
        """
        Генерирует синтетический датасет и обучает XGBoost.

        Логика синтетики:
          - oversold RSI + бычий MACD → UP
          - overbought RSI + медвежий MACD → DOWN
          - +шум для реализма
        """
        np.random.seed(42)
        n_samples = 5000

        data = []
        labels = []

        for _ in range(n_samples):
            # Случайные показатели индикаторов
            rsi = np.random.uniform(10, 90)
            macd_hist = np.random.uniform(-2, 2)
            bb_pct = np.random.uniform(0, 1)
            stoch_k = np.random.uniform(5, 95)
            stoch_d = np.random.uniform(5, 95)
            atr_ratio = np.random.uniform(0.0005, 0.01)

            # Кодируем категориальные
            macd_cross = np.random.choice([0, 1, 2], p=[0.6, 0.2, 0.2])
            bb_pos = np.random.choice([0, 1, 2], p=[0.7, 0.15, 0.15])
            stoch_sig = np.random.choice([0, 1, 2], p=[0.6, 0.2, 0.2])
            stoch_cross = np.random.choice([0, 1, 2], p=[0.6, 0.2, 0.2])

            # Определяем метку на основе правил (с шумом)
            up_score = 0.5

            # RSI oversold → UP
            if rsi < 30:
                up_score += 0.20
            # RSI overbought → DOWN
            if rsi > 70:
                up_score -= 0.20

            # MACD бычье пересечение → UP
            if macd_cross == 1:
                up_score += 0.15
            elif macd_cross == 2:
                up_score -= 0.15

            # BB ниже нижней → UP (отскок)
            if bb_pos == 1:
                up_score += 0.10
            elif bb_pos == 2:
                up_score -= 0.10

            # Stochastic oversold + cross up → UP
            if stoch_sig == 1 and stoch_cross == 1:
                up_score += 0.15
            elif stoch_sig == 2 and stoch_cross == 2:
                up_score -= 0.15

            # Шум (±0.15)
            up_score += np.random.uniform(-0.15, 0.15)

            label = 1 if up_score > 0.5 else 0

            data.append([
                rsi / 100.0, macd_hist, macd_cross, bb_pos,
                bb_pct, stoch_k / 100.0, stoch_d / 100.0,
                stoch_sig, stoch_cross, atr_ratio,
            ])
            labels.append(label)

        X = np.array(data, dtype=np.float32)
        y = np.array(labels)

        # Масштабирование
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Обучение XGBoost
        from xgboost import XGBClassifier

        self.model = XGBClassifier(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
        )
        self.model.fit(X_scaled, y)

        self.is_trained = True
        self.feature_names = [
            "rsi_norm", "macd_hist", "macd_cross", "bb_pos",
            "bb_pct", "stoch_k", "stoch_d", "stoch_sig",
            "stoch_cross", "atr_ratio",
        ]

        # Оценка на синтетике
        y_pred = self.model.predict(X_scaled)
        accuracy = float((y_pred == y).mean())
        logger.info("AI: синтетическая модель accuracy=%.2f%%", accuracy * 100)

    # ------------------------------------------------------------------
    # Сохранение / загрузка
    # ------------------------------------------------------------------

    def _save_model(self) -> None:
        """Сохраняет модель и scaler в файлы."""
        try:
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(self.model, f)
            with open(SCALER_PATH, "wb") as f:
                pickle.dump(self.scaler, f)
            logger.info("AI модель сохранена: %s", MODEL_PATH)
        except Exception as exc:
            logger.error("Ошибка сохранения модели: %s", exc)

    def _load_model(self) -> None:
        """Загружает модель и scaler из файлов."""
        with open(MODEL_PATH, "rb") as f:
            self.model = pickle.load(f)
        with open(SCALER_PATH, "rb") as f:
            self.scaler = pickle.load(f)
        self.is_trained = True
