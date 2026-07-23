"""
SignalManager — управление жизненным циклом сигналов.
Генерация, рассылка, сохранение в БД.
АВТОМАТИЧЕСКИЙ ЦИКЛ — без нажатия кнопок.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.analyzer import SignalAnalyzer, SignalResult
from app.bot.messages import format_signal_message
from app.config import config
from app.data.po_provider import POProvider, ASSETS as DEFAULT_ASSETS
from app.db.models import Signal, User
from app.services.user_service import UserService

logger = logging.getLogger(__name__)


class SignalManager:
    """
    Менеджер сигналов.
    Запускает цикл анализа, сохраняет сигналы в БД
    и отправляет их пользователям через Telegram.

    Работает АВТОМАТИЧЕСКИ каждые 3 минуты.
    Не требует нажатия кнопок!
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bot_instance: Any,  # aiogram Bot
    ) -> None:
        self.session_factory = session_factory
        self.bot = bot_instance
        # Используем Yahoo Finance напрямую — надёжно и бесплатно
        self.provider = POProvider()
        self._running = False

    async def start_loop(self) -> None:
        """
        Запускает бесконечный цикл анализа рынков.
        Каждые 3 минуты проверяет все активы и рассылает сигналы.
        """
        self._running = True
        logger.info(
            "🚀 SignalManager: АВТО-ЦИКЛ запущен (интервал=%dс = %d мин)",
            config.SIGNAL_CHECK_INTERVAL_SEC,
            config.SIGNAL_CHECK_INTERVAL_SEC // 60,
        )
        logger.info("📡 Использую Yahoo Finance — как все топ-сигнальные боты")

        # Ждём 10 секунд при старте, чтобы бот успел инициализироваться
        await asyncio.sleep(10)

        while self._running:
            try:
                await self._analysis_cycle()
            except Exception as exc:
                logger.exception("💥 Ошибка в цикле анализа: %s", exc)

            logger.info(
                "⏳ Следующая проверка через %d сек...",
                config.SIGNAL_CHECK_INTERVAL_SEC,
            )
            await asyncio.sleep(config.SIGNAL_CHECK_INTERVAL_SEC)

        logger.info("SignalManager: цикл завершён")

    async def stop_loop(self) -> None:
        """Останавливает цикл анализа."""
        self._running = False
        await self.provider.close()
        logger.info("SignalManager: остановлен")

    async def _analysis_cycle(self) -> None:
        """Один цикл анализа — сканирование всех активов."""
        logger.debug("🔍 SignalManager: начало цикла анализа")

        # 1. Получаем данные через Yahoo Finance
        data_map = await self.provider.fetch_all(
            assets=DEFAULT_ASSETS,
            timeframe="1m",
            limit=100,
        )

        if not data_map:
            logger.warning("⚠️ Нет данных для анализа (Yahoo Finance не вернул данные)")
            return

        logger.info(
            "📊 Получены данные: %d активов",
            len(data_map),
        )

        # 2. Анализируем каждый актив
        valid_signals: list[tuple[str, SignalResult]] = []
        for asset, df in data_map.items():
            try:
                analyzer = SignalAnalyzer(
                    asset=asset,
                    expiry="3m",
                    min_confluence=config.MIN_CONFLUENCE_SCORE,
                )
                result = analyzer.analyze(df)
                if result.is_valid:
                    valid_signals.append((asset, result))
                    logger.info(
                        "✅ СИГНАЛ %s %s (conf=%.1f%%, score=%.2f)",
                        asset, result.direction,
                        result.confidence * 100, result.confluence_score,
                    )
                else:
                    logger.debug(
                        "➖ %s: нет сигнала (%s)", asset, result.reason
                    )
            except Exception as exc:
                logger.error("Ошибка анализа %s: %s", asset, exc)

        if not valid_signals:
            logger.info("📭 Нет валидных сигналов в этом цикле")
            return

        # 3. Сохраняем сигналы и рассылаем
        async with self.session_factory() as session:
            user_service = UserService(session)

            # Получаем ВСЕХ активных пользователей
            users_result = await session.execute(
                select(User).where(User.is_active == True)  # noqa: E712
            )
            users = users_result.scalars().all()

            if not users:
                logger.info("👤 Нет активных пользователей для рассылки")
                return

            logger.info(
                "📨 Рассылаю %d сигналов %d пользователям...",
                len(valid_signals), len(users),
            )

            sent_total = 0
            for asset, signal_result in valid_signals:
                for user in users:
                    try:
                        # Проверка лимитов (бесплатные не превысят лимит)
                        if not await user_service.check_signal_limit(user):
                            logger.debug(
                                "Пользователь %d превысил лимит",
                                user.telegram_id,
                            )
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

                        # Отправка в Telegram — АВТОМАТИЧЕСКИ!
                        msg = format_signal_message(signal_result)
                        await self.bot.send_message(
                            chat_id=user.telegram_id,
                            text=msg,
                            parse_mode="HTML",
                        )
                        sent_total += 1

                        # Небольшая задержка между отправками
                        await asyncio.sleep(0.05)

                    except Exception as exc:
                        logger.error(
                            "❌ Ошибка отправки сигнала пользователю %d: %s",
                            user.telegram_id, exc,
                        )

                await session.commit()

        logger.info(
            "✅ SignalManager: цикл завершён, отправлено %d сигналов",
            sent_total,
        )
