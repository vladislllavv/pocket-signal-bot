#!/usr/bin/env python3
"""
Pocket Signal Bot — ТОЧКА ВХОДА.

Запускает одновременно:
  1. 🤖 Telegram бот (aiogram polling)
  2. 🌐 Webhook сервер (FastAPI на порту 8080)
  3. 🧠 AI-модуль (XGBoost — инициализация при старте)
  4. ⏱ Планировщик (APScheduler)

Всё работает сразу после:
  1. cp .env.example .env && заполнить BOT_TOKEN
  2. pip install -r requirements.txt
  3. python bot.py

Или:
  docker compose up -d --build

Production-ready!
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.main_router import router as main_router, init_ai_predictor
from app.bot.premium_router import router as premium_router
from app.config import config
from app.db.base import init_db
from app.services.scheduler import SignalScheduler
from app.utils.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# FastAPI Webhook Server (встроенный)
# ═══════════════════════════════════════════════════════════════════════

async def run_webhook_server() -> None:
    """Запуск FastAPI webhook-сервера на порту 8080."""
    try:
        import uvicorn
        from app.webhook.server import webhook_app

        webhook_host = "0.0.0.0"
        webhook_port = config.WEBHOOK_PORT

        logger.info(
            "🌐 Webhook сервер: http://%s:%d  |  POST /webhook/tradingview",
            webhook_host, webhook_port,
        )
        logger.info(
            "📝 Пример curl для TradingView:\n"
            f"  curl -X POST http://{webhook_host}:{webhook_port}/webhook/tradingview "
            '-H "Content-Type: application/json" '
            '-d \'{"ticker":"BTCUSD","close":67500,"signal":"buy"}\''
        )

        config_instance = uvicorn.Config(
            webhook_app,
            host=webhook_host,
            port=webhook_port,
            log_level="info",
            access_log=True,
        )
        server = uvicorn.Server(config_instance)
        await server.serve()
    except Exception as exc:
        logger.warning("Webhook сервер не запущен (опционально): %s", exc)


# ═══════════════════════════════════════════════════════════════════════
# Основная функция
# ═══════════════════════════════════════════════════════════════════════

async def main() -> None:
    """Главная функция запуска."""
    logger.info("=" * 54)
    logger.info("  🤖 Pocket Signal Bot v2.0 — ЗАПУСК")
    logger.info("=" * 54)

    # 1. Проверка токена
    if not config.BOT_TOKEN:
        logger.error(
            "❌ BOT_TOKEN не задан!\n"
            "  cp .env.example .env\n"
            "  nano .env  # вставь токен\n"
            "  python bot.py"
        )
        sys.exit(1)

    # 2. База данных
    logger.info("🗄️  Инициализация БД...")
    await init_db()
    logger.info("✅ База данных готова")

    # 3. AI-модуль (XGBoost)
    logger.info("🧠 Инициализация AI-модуля...")
    try:
        init_ai_predictor()
        logger.info("✅ AI-модуль загружен")
    except Exception as exc:
        logger.warning("⚠️ AI-модуль: %s (продолжаем без AI)", exc)

    # 4. Telegram Bot
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Подключаем роутеры
    dp.include_router(main_router)
    dp.include_router(premium_router)
    logger.info("✅ Роутеры подключены")

    # 5. Планировщик
    scheduler = SignalScheduler()
    scheduler.start()
    logger.info("✅ Планировщик запущен")

    # 6. Удаляем вебхук, стартуем polling
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("=" * 54)
    logger.info("  🚀 Бот запущен! Нажми Ctrl+C для остановки")
    logger.info("=" * 54)

    # Запускаем бот + webhook сервер конкурентно
    polling_task = asyncio.create_task(
        dp.start_polling(
            bot,
            allowed_updates=[
                "message", "callback_query",
                "pre_checkout_query", "successful_payment",
                "chat_member", "my_chat_member",
            ],
        )
    )
    webhook_task = asyncio.create_task(run_webhook_server())

    try:
        # Ждём любую из задач (если упадёт — перезапускаем)
        done, pending = await asyncio.wait(
            [polling_task, webhook_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            try:
                exc = task.exception()
                if exc:
                    logger.error("Задача завершилась с ошибкой: %s", exc)
            except asyncio.CancelledError:
                pass

        # Отменяем оставшиеся задачи
        for task in pending:
            task.cancel()

    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Получен сигнал остановки")
    except Exception as exc:
        logger.exception("💥 Критическая ошибка: %s", exc)
    finally:
        logger.info("🛑 Остановка...")
        scheduler.stop()
        await bot.session.close()
        logger.info("👋 Бот остановлен. До встречи!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
