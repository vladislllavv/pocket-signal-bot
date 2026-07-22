#!/usr/bin/env python3
"""
Pocket Signal Bot — Точка входа для Railway.
"""

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.main_router import router as main_router, init_ai_predictor
from app.bot.premium_router import router as premium_router
from app.bot.admin_router import router as admin_router
from app.config import config
from app.db.base import init_db
from app.services.scheduler import SignalScheduler
from app.utils.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("=" * 54)
    logger.info("  Pocket Signal Bot — ЗАПУСК")
    logger.info("=" * 54)

    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN не задан! Добавь в Railway Variables")
        sys.exit(1)

    logger.info("Инициализация БД...")
    await init_db()
    logger.info("БД готова")

    logger.info("Инициализация AI...")
    try:
        init_ai_predictor()
        logger.info("AI загружен")
    except Exception as exc:
        logger.warning("AI не загружен (продолжаем): %s", exc)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.include_router(main_router)
    dp.include_router(premium_router)
    logger.info("Роутеры подключены")

    scheduler = SignalScheduler()
    scheduler.start()
    logger.info("Планировщик запущен")

    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("=" * 54)
    logger.info("  Бот запущен! Иди в Telegram и пиши /start")
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
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
