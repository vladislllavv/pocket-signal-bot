"""
Webhook-сервер для приёма алертов с TradingView и внешних систем.

Запускается вместе с ботом на том же процессе.
Эндпоинты:
  POST /webhook/tradingview — приём алертов с TradingView
  POST /webhook/custom     — приём кастомных webhook'ов
  GET  /health             — Healthcheck

После получения алерта:
  1. Парсим актив, цену, направление
  2. Отправляем сигнал в Telegram всем подписанным пользователям
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.analytics.analyzer import SignalAnalyzer, SignalResult
from app.bot.messages import format_signal_message
from app.config import config
from app.db.base import get_session, async_session_factory
from app.db.models import Signal, User

logger = logging.getLogger(__name__)

# Создаём FastAPI приложение
webhook_app = FastAPI(
    title="Pocket Signal Webhook",
    description="Webhook-сервер для TradingView и внешних алертов",
    version="1.0.0",
)

# Secret для проверки подписи TradingView webhook
# Устанавливается через .env: WEBHOOK_SECRET=your_secret
WEBHOOK_SECRET = config.WEBHOOK_SECRET or secrets.token_hex(16)


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Проверка HMAC-SHA256 подписи TradingView webhook.
    TradingView отправляет заголовок X-Tradingview-Signature.
    """
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# TradingView Webhook
# ---------------------------------------------------------------------------

@webhook_app.post("/webhook/tradingview")
async def tradingview_webhook(request: Request) -> JSONResponse:
    """
    Приём алерта с TradingView.

    Ожидаемый формат POST (JSON):
    {
        "ticker": "BTCUSD",
        "exchange": "PO",
        "close": 67543.21,
        "high": 67800.00,
        "low": 67200.00,
        "volume": 1234.5,
        "signal": "buy",          // buy / sell
        "strategy": "RSI_MACD"
    }

    Также поддерживает кастомный формат TradingView:
    {{ticker}}, {{close}}, {{signal}}
    """
    try:
        body = await request.body()
        data = await request.json()
    except Exception as exc:
        logger.error("Webhook: неверный JSON: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Проверка подписи (если настроено)
    signature = request.headers.get("X-Tradingview-Signature", "")
    secret = getattr(config, "WEBHOOK_SECRET", "") or WEBHOOK_SECRET
    if signature and not verify_signature(body, signature, secret):
        logger.warning("Webhook: неверная подпись")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Извлекаем данные
    ticker = data.get("ticker", data.get("symbol", data.get("asset", "UNKNOWN")))
    close_price = float(data.get("close", data.get("price", 0)))
    signal_type = data.get("signal", data.get("direction", data.get("action", ""))).lower()

    logger.info(
        "Webhook TradingView: %s price=%.5f signal=%s",
        ticker, close_price, signal_type,
    )

    if not close_price or not signal_type:
        raise HTTPException(status_code=400, detail="Missing price or signal")

    # Определяем направление
    if signal_type in ("buy", "up", "call"):
        direction = "UP"
    elif signal_type in ("sell", "down", "put"):
        direction = "DOWN"
    else:
        logger.warning("Webhook: неизвестный сигнал '%s'", signal_type)
        raise HTTPException(status_code=400, detail=f"Unknown signal: {signal_type}")

    # Создаём SignalResult из webhook
    signal_result = SignalResult(
        asset=ticker,
        direction=direction,
        expiry="3m",
        entry_price=close_price,
        confidence=0.75,  # доверие к TradingView сигналу
        confluence_score=0.70,
        is_valid=True,
    )

    # Рассылаем Signal всем пользователям
    sent_count = await _broadcast_signal(signal_result)

    return JSONResponse(
        content={
            "status": "ok",
            "asset": ticker,
            "direction": direction,
            "price": close_price,
            "sent_to": sent_count,
        },
        status_code=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Кастомный Webhook
# ---------------------------------------------------------------------------

@webhook_app.post("/webhook/custom")
async def custom_webhook(request: Request) -> JSONResponse:
    """
    Кастомный webhook для внешних систем.
    Принимает тот же формат, что и TradingView.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Просто логируем и возвращаем успех
    logger.info("Custom webhook received: %s", json.dumps(data, default=str)[:200])
    return JSONResponse(
        content={"status": "ok", "received": True},
        status_code=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------

@webhook_app.get("/health")
async def health() -> JSONResponse:
    """Проверка здоровья сервиса."""
    return JSONResponse(
        content={
            "status": "alive",
            "service": "pocket-signal-webhook",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        status_code=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Broadcast сигнала всем пользователям
# ---------------------------------------------------------------------------

async def _broadcast_signal(signal_result: SignalResult, bot_instance=None) -> int:
    """
    Рассылает сигнал всем активным пользователям.

    Args:
        signal_result: SignalResult для отправки
        bot_instance: aiogram Bot (если None, импортирует глобальный)

    Returns:
        количество пользователей, получивших сигнал
    """
    sent_count = 0

    try:
        # Импортируем Bot здесь, чтобы избежать циклического импорта
        if bot_instance is None:
            from aiogram import Bot
            bot_instance = Bot(token=config.BOT_TOKEN)

        async with async_session_factory() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.is_active == True)  # noqa: E712
            )
            users = result.scalars().all()

            message_text = format_signal_message(signal_result)
            from app.bot.keyboards import signal_actions_kb

            for user in users:
                try:
                    # Проверка лимитов
                    from app.services.user_service import UserService
                    service = UserService(session)

                    if not await service.check_signal_limit(user):
                        continue

                    # Сохраняем в БД
                    db_signal = Signal(
                        user_id=user.id,
                        asset=signal_result.asset,
                        direction=signal_result.direction,
                        expiry=signal_result.expiry,
                        entry_price=signal_result.entry_price,
                        confidence=signal_result.confidence,
                        confluence_score=signal_result.confluence_score,
                        result="pending",
                    )
                    session.add(db_signal)

                    # Инкремент счётчика
                    await service.increment_signals_today(user)

                    # Отправка
                    await bot_instance.send_message(
                        chat_id=user.telegram_id,
                        text=message_text,
                        parse_mode="HTML",
                        reply_markup=signal_actions_kb(
                            signal_result.asset,
                            signal_result.direction,
                            signal_result.expiry,
                        ),
                    )
                    sent_count += 1

                except Exception as exc:
                    logger.error("Ошибка отправки webhook-сигнала %d: %s", user.telegram_id, exc)
                    continue

            await session.commit()

    except Exception as exc:
        logger.exception("Ошибка broadcast сигнала: %s", exc)

    logger.info("Webhook: сигнал отправлен %d пользователям", sent_count)
    return sent_count
