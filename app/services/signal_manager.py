"""
SignalManager — управление жизненным циклом сигналов.
Генерация, рассылка, сохранение в БД.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.analyzer import SignalAnalyzer, SignalResult
from app.bot.messages import format_signal_message
from app.config import config
from app.data.market_data import DEFAULT_ASSETS, MarketDataAggregator
from app.db.models import Signal, User
from app.services.user_service import UserService

logger = logging.getLogger(__name__)


class SignalManager:
    """
    Менеджер сигналов.
    Запускает цикл анализа, сохраняет сигналы в БД
    и отправляет их пользователям через Telegram.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bot_instance: Any,  # aiogram Bot
    ) -> None:
        self.session_factory = session_factory
        self.bot = bot_instance
        self.aggregator = MarketDataAggregator()
        self._running = False

    async def start_loop(self) -> None:
        """
        Запускает бесконечный цикл анализа рынков.
        Каждые SIGNAL_CHECK_INTERVAL_SEC секунд проверяет
        все активы и рассылает сигналы.
        """
        self._running = True
        logger.info(
            "SignalManager: запущен цикл (интервал=%dс)",
            config.SIGNAL_CHECK_INTERVAL_SEC,
        )

        while self._running:
            try:
                await self._analysis_cycle()
            except Exception as exc:
                logger.exception("Ошибка в цикле анализа: %s", exc)

            await asyncio.sleep(config.SIGNAL_CHECK_INTERVAL_SEC)

        logger.info("SignalManager: цикл завершён")

    async def stop_loop(self) -> None:
        """Останавливает цикл анализа."""
        self._running = False
        await self.aggregator.close()
        logger.info("SignalManager: остановлен")

    async def _analysis_cycle(self) -> None:
        """Один цикл анализа — сканирование всех активов."""
        logger.debug("SignalManager: начало цикла анализа")

        # 1. Получаем данные
        data_map = await self.aggregator.fetch_all(
            assets=DEFAULT_ASSETS,
            timeframe="1m",
            limit=100,
        )

        if not data_map:
            logger.warning("Нет данных для анализа")
            return

        # 2. Анализируем каждый актив
        valid_signals: list[tuple[str, SignalResult]] = []
        for asset, df in data_map.items():
            analyzer = SignalAnalyzer(asset=asset, expiry="3m")
            result = analyzer.analyze(df)
            if result.is_valid:
                valid_signals.append((asset, result))

        if not valid_signals:
            logger.debug("Нет валидных сигналов в этом цикле")
            return

        # 3. Сохраняем сигналы и рассылаем
        async with self.session_factory() as session:
            user_service = UserService(session)

            # Получаем всех активных пользователей
            users_result = await session.execute(
                select(User).where(User.is_active == True)  # noqa: E712
            )
            users = users_result.scalars().all()

            for asset, signal_result in valid_signals:
                logger.info(
                    "Сигнал %s %s (conf=%.2f) — рассылка %d пользователям",
                    asset, signal_result.direction,
                    signal_result.confidence, len(users),
                )

                for user in users:
                    try:
                        # Проверка лимитов
                        if not await user_service.check_signal_limit(user):
                            continue

                        # Сохраняем сигнал в БД
                        db_signal = Signal(
                            user_id=user.id,
                            asset=asset,
                            direction=signal_result.direction,
                            expiry=signal_result.expiry,
                            entry_price=signal_result.entry_price,
                            confidence=signal_result.confidence,
                            confluence_score=signal_result.confluence_score,
                            rsi_value=signal_result.indicators.rsi,
                            macd_signal=signal_result.indicators.macd_signal,
                            bb_position=signal_result.indicators.bb_position,
                            stoch_signal=signal_result.indicators.stoch_signal,
                            atr_value=signal_result.indicators.atr,
                            volatility_filter=True,
                            result="pending",
                        )
                        session.add(db_signal)
                        await session.flush()

                        # Инкремент счётчика
                        await user_service.increment_signals_today(user)

                        # Отправка в Telegram
                        msg = format_signal_message(signal_result)
                        await self.bot.send_message(
                            chat_id=user.telegram_id,
                            text=msg,
                            parse_mode="HTML",
                        )

                        # Небольшая задержка между отправками
                        await asyncio.sleep(0.05)

                    except Exception as exc:
                        logger.error(
                            "Ошибка отправки сигнала пользователю %d: %s",
                            user.telegram_id, exc,
                        )

                await session.commit()

        logger.info(
            "SignalManager: цикл завершён, отправлено %d сигналов",
            len(valid_signals),
        )
