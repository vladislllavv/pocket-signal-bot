#!/usr/bin/env python3
"""
Pocket Signal Bot — Точка входа для Railway.
Автоматическая рассылка сигналов каждые 3 минуты.
"""

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import select

from app.bot.main_router import router as main_router, init_ai_predictor
from app.bot.premium_router import router as premium_router
from app.bot.admin_router import router as admin_router
from app.config import config
from app.db.base import init_db, async_session_factory
from app.db.models import User, Signal
from app.services.scheduler import SignalScheduler
from app.services.user_service import UserService
from app.utils.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


async def auto_signal_cycle():
    """
    Автоматический цикл генерации и рассылки сигналов.
    Запускается каждые 3 минуты.
    Использует Yahoo Finance для реальных данных.
    """
    await asyncio.sleep(30)  # ждём 30 сек после старта бота
    logger.info("🔄 Авто-цикл сигналов запущен (каждые 3 мин)")

    while True:
        try:
            from app.analytics.analyzer import SignalAnalyzer
            from app.data.market_data import MarketDataAggregator, DEFAULT_ASSETS
            from app.bot.messages import format_signal_message
            from app.bot.keyboards import signal_actions_kb

            aggregator = MarketDataAggregator()
            data_map = await aggregator.fetch_all(assets=DEFAULT_ASSETS, limit=100)

            signals_sent = 0
            async with async_session_factory() as session:
                result = await session.execute(
                    select(User).where(User.is_active == True)
                )
                users = result.scalars().all()

                if not users:
                    logger.debug("Нет пользователей для рассылки")
                    await aggregator.close()
                    await asyncio.sleep(180)
                    continue

                for asset, df in data_map.items():
                    analyzer = SignalAnalyzer(asset=asset, expiry="3m")
                    signal_result = analyzer.analyze(df)

                    if not signal_result.is_valid:
                        continue

                    # Рассылаем сигнал всем пользователям
                    for user in users:
                        try:
                            svc = UserService(session)
                            if not await svc.check_signal_limit(user):
                                continue

                            # Отправляем сообщение
                            bot_temp = Bot(
                                token=config.BOT_TOKEN,
                                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                            )
                            msg = format_signal_message(signal_result)
                            await bot_temp.send_message(
                                chat_id=user.telegram_id,
                                text=msg,
                                parse_mode="HTML",
                                reply_markup=signal_actions_kb(
                                    asset, signal_result.direction, signal_result.expiry
                                ),
                            )
                            await bot_temp.session.close()

                            # Сохраняем сигнал в БД
                            db_signal = Signal(
                                user_id=user.id,
                                asset=asset,
                                direction=signal_result.direction,
                                expiry=signal_result.expiry,
                                entry_price=signal_result.entry_price,
                                confidence=signal_result.confidence,
                                confluence_score=signal_result.confluence_score,
                                result="pending",
                            )
                            session.add(db_signal)
                            await svc.increment_signals_today(user)
                            signals_sent += 1

                        except Exception as exc:
                            logger.error("Ошибка отправки пользователю %d: %s", user.telegram_id, exc)

                await session.commit()

            if signals_sent:
                logger.info("✅ Авто-цикл: отправлено %d сигналов", signals_sent)
            else:
                logger.debug("Авто-цикл: нет сигналов в этом цикле")

            await aggregator.close()

        except Exception as exc:
            logger.warning("Авто-цикл: ошибка %s", exc)

        await asyncio.sleep(180)  # каждые 3 минуты


async def main() -> None:
    """Главная функция запуска."""
    logger.info("=" * 54)
    logger.info("  Pocket Signal Bot — ЗАПУСК")
    logger.info("=" * 54)

    # Проверка токена
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN не задан! Добавь в Railway Variables")
        sys.exit(1)

    # База данных
    logger.info("Инициализация БД...")
    await init_db()
    logger.info("БД готова")

    # AI-модуль
    logger.info("Инициализация AI...")
    try:
        init_ai_predictor()
        logger.info("AI загружен")
    except Exception as exc:
        logger.warning("AI не загружен (продолжаем): %s", exc)

    # Telegram Bot
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.include_router(main_router)
    dp.include_router(premium_router)
    dp.include_router(admin_router)
    logger.info("Роутеры подключены")

    # Планировщик
    scheduler = SignalScheduler()
    scheduler.start()
    logger.info("Планировщик запущен")

    # Удаляем вебхук
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем авто-цикл сигналов в фоне
    asyncio.create_task(auto_signal_cycle())

    logger.info("=" * 54)
    logger.info("  🚀 Бот запущен! Иди в Telegram и пиши /start")
    logger.info("  📡 Авто-сигналы каждые 3 минуты")
    logger.info("=" * 54)

    try:
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message", "callback_query",
                "pre_checkout_query", "successful_payment",
                "chat_member", "my_chat_member",
            ],
        )
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка")
    except Exception as exc:
        logger.exception("Ошибка: %s", exc)
    finally:
        scheduler.stop()
        await bot.session.close()
        logger.info("Бот остановлен. До встречи!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
