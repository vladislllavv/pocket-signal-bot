"""
Главный роутер Telegram бота (aiogram 3.x).
Интегрирует AI, премиум, статистику-чарты и управление лимитами.
Добавлен обработчик PO сигналов (демо-счёт).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.analytics.ai_predictor import AIPredictor
from app.analytics.analyzer import SignalAnalyzer, SignalResult
from app.bot.keyboards import (
    back_to_main_kb,
    main_menu_kb,
    settings_kb,
    signal_actions_kb,
    subscription_kb,
    timeframe_kb,
)
from app.bot.messages import (
    FREE_LIMIT_MESSAGE,
    PREMIUM_INFO_MESSAGE,
    REFERRAL_MESSAGE,
    STATISTICS_MESSAGE,
    WELCOME_MESSAGE,
    format_signal_message,
)
from app.bot.statistics_charts import (
    pnl_chart,
    win_loss_chart,
    win_rate_gauge,
)
from app.config import config
from app.data.market_data import DEFAULT_ASSETS, MarketDataAggregator
from app.db.base import async_session_factory
from app.db.models import Signal, TradeLog, User
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = Router(name="main")

ai_predictor = AIPredictor()


def init_ai_predictor() -> None:
    try:
        ai_predictor.load_or_init()
    except Exception as exc:
        logger.error("Ошибка инициализации AI: %s", exc)


# ═══════════════════════════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════════════════════════

@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(message: Message, state: FSMContext) -> None:
    await state.clear()
    args = message.text.split()
    referrer_code = None
    if len(args) > 1:
        ref_param = args[1]
        if ref_param.startswith("ref_"):
            referrer_code = ref_param[4:]
    await _register_and_welcome(message, referrer_code)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _register_and_welcome(message)


async def _register_and_welcome(message: Message, referrer_code: str | None = None) -> None:
    tg_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    try:
        async with async_session_factory() as session:
            service = UserService(session)
            user = await service.get_or_create(
                telegram_id=tg_id, username=username,
                first_name=first_name, last_name=last_name,
                referrer_code=referrer_code,
            )
            is_premium = user.is_premium
            limit_info = "♾️ Безлимит" if is_premium else f"{config.FREE_SIGNALS_PER_DAY} сигналов/день"
    except Exception as exc:
        logger.error("Регистрация %d: %s", tg_id, exc)
        is_premium = False
        limit_info = f"{config.FREE_SIGNALS_PER_DAY} сигналов/день"

    welcome_extended = f"{WELCOME_MESSAGE}\n\n👤 Статус: {'💎 Premium' if is_premium else '🆓 Free'}\n📊 Лимит: {limit_info}"

    await message.answer(
        welcome_extended, parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_premium=is_premium),
    )


# ═══════════════════════════════════════════════════════════════════════
# Навигация
# ═══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    try:
        async with async_session_factory() as session:
            service = UserService(session)
            user = await service.get_by_telegram_id(tg_id)
            is_premium = user.is_premium if user else False
    except Exception:
        is_premium = False
    await callback.message.edit_text(
        WELCOME_MESSAGE, parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_premium=is_premium),
    )
    await callback.answer()


@router.message(Command("menu"))
async def show_menu(message: Message) -> None:
    tg_id = message.from_user.id
    try:
        async with async_session_factory() as session:
            service = UserService(session)
            user = await service.get_by_telegram_id(tg_id)
            is_premium = user.is_premium if user else False
    except Exception:
        is_premium = False
    await message.answer(
        WELCOME_MESSAGE, parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_premium=is_premium),
    )


# ═══════════════════════════════════════════════════════════════════════
# 📊 Аналитика рынка (Yahoo Finance)
# ═══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "market_analysis")
async def market_analysis(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id

    async with async_session_factory() as session:
        service = UserService(session)
        user = await service.get_by_telegram_id(tg_id)
        if not user:
            await callback.answer("Напиши /start", show_alert=True)
            return
        if not user.is_premium and user.signals_today >= config.FREE_SIGNALS_PER_DAY:
            await callback.message.edit_text(
                FREE_LIMIT_MESSAGE.format(used=user.signals_today, limit=config.FREE_SIGNALS_PER_DAY),
                parse_mode=ParseMode.HTML, reply_markup=subscription_kb(),
            )
            await callback.answer()
            return

    await callback.message.edit_text(
        "📊 Сканирую рынки...", parse_mode=ParseMode.HTML,
        reply_markup=back_to_main_kb(),
    )
    await callback.answer()

    try:
        aggregator = MarketDataAggregator()
        data_map = await aggregator.fetch_all(assets=DEFAULT_ASSETS, limit=100)
        if not data_map:
            await callback.message.edit_text("❌ Нет данных.", parse_mode=ParseMode.HTML, reply_markup=back_to_main_kb())
            return

        sent_signals = []
        for asset, df in data_map.items():
            analyzer = SignalAnalyzer(asset=asset, expiry="3m")
            result = analyzer.analyze(df)
            if result.is_valid:
                try:
                    ai_mult = ai_predictor.get_confidence_multiplier(result.indicators)
                    result.confidence = min(1.0, result.confidence * ai_mult)
                    ai_dir = ai_predictor.get_ai_direction(result.indicators)
                    if ai_dir and ai_dir != result.direction:
                        result.confidence *= 0.7
                    elif ai_dir == result.direction:
                        result.confidence = min(1.0, result.confidence * 1.1)
                except Exception:
                    pass
                if result.confidence >= config.SIGNAL_CONFIDENCE_THRESHOLD:
                    sent_signals.append(result)

        await callback.message.delete()

        if not sent_signals:
            await callback.message.answer(
                "📊 Аналитика рынка\n\n✅ Все активы просканированы.\n❌ Нет сигналов.",
                parse_mode=ParseMode.HTML, reply_markup=main_menu_kb(is_premium=user.is_premium),
            )
        else:
            for sig in sent_signals:
                msg = format_signal_message(sig)
                await callback.message.answer(
                    msg, parse_mode=ParseMode.HTML,
                    reply_markup=signal_actions_kb(sig.asset, sig.direction, sig.expiry),
                )
            await callback.message.answer(
                f"📊 Найдено {len(sent_signals)} сигналов.",
                parse_mode=ParseMode.HTML, reply_markup=main_menu_kb(is_premium=user.is_premium),
            )

            async with async_session_factory() as session:
                svc = UserService(session)
                for sig in sent_signals:
                    db_signal = Signal(
                        user_id=user.id, asset=sig.asset, direction=sig.direction,
                        expiry=sig.expiry, entry_price=sig.entry_price,
                        confidence=sig.confidence, confluence_score=sig.confluence_score,
                        result="pending",
                    )
                    session.add(db_signal)
                    await svc.increment_signals_today(user)
                await session.commit()

    except Exception as exc:
        logger.exception("Ошибка анализа: %s", exc)
        await callback.message.edit_text(f"❌ Ошибка: {exc}", parse_mode=ParseMode.HTML, reply_markup=back_to_main_kb())
    finally:
        try:
            await aggregator.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════
# 📡 PO Сигналы (демо) — через WebSocket Pocket Option
# ═══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "po_signals")
async def po_signals_handler(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id

    async with async_session_factory() as session:
        service = UserService(session)
        user = await service.get_by_telegram_id(tg_id)
        if not user:
            await callback.answer("Напиши /start", show_alert=True)
            return
        if not user.is_premium and user.signals_today >= config.FREE_SIGNALS_PER_DAY:
            await callback.message.edit_text(
                FREE_LIMIT_MESSAGE.format(used=user.signals_today, limit=config.FREE_SIGNALS_PER_DAY),
                parse_mode=ParseMode.HTML, reply_markup=subscription_kb(),
            )
            await callback.answer()
            return

    if not config.PO_SSID:
        await callback.message.edit_text(
            "📡 PO Сигналы (демо)\n\n"
            "❌ SSID не настроен!\n\n"
            "Для получения сигналов напрямую с Pocket Option:\n"
            "1. Скачай github.com/A11ksa/API-Pocket-Option\n"
            "2. pip install .\n"
            "3. python test1.py (введи email/пароль PO)\n"
            "4. Скопируй SSID из sessions/session.json\n"
            "5. Добавь в Railway Variables: PO_SSID",
            parse_mode=ParseMode.HTML, reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📡 PO Сигналы (демо)\n\nПодключаюсь к Pocket Option...",
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()

    try:
        from app.data.po_provider import POProvider

        provider = POProvider()
        connected = await provider.connect()

        if not connected:
            await callback.message.edit_text(
                "❌ Не удалось подключиться к PO. Проверь PO_SSID.",
                parse_mode=ParseMode.HTML, reply_markup=back_to_main_kb(),
            )
            return

        data_map = await provider.fetch_all(limit=100)
        balance = await provider.get_balance()

        if not data_map:
            await callback.message.edit_text(
                "❌ Нет данных с PO. Возможно SSID истёк.",
                parse_mode=ParseMode.HTML, reply_markup=back_to_main_kb(),
            )
            await provider.close()
            return

        balance_text = ""
        if balance:
            balance_text = f"💰 Баланс: {balance['balance']:.2f} {balance['currency']}\n"

        sent_signals = []
        for asset, df in data_map.items():
            analyzer = SignalAnalyzer(asset=asset, expiry="3m")
            result = analyzer.analyze(df)
            if result.is_valid:
                try:
                    ai_mult = ai_predictor.get_confidence_multiplier(result.indicators)
                    result.confidence = min(1.0, result.confidence * ai_mult)
                    ai_dir = ai_predictor.get_ai_direction(result.indicators)
                    if ai_dir and ai_dir != result.direction:
                        result.confidence *= 0.7
                    elif ai_dir == result.direction:
                        result.confidence = min(1.0, result.confidence * 1.1)
                except Exception:
                    pass
                if result.confidence >= config.SIGNAL_CONFIDENCE_THRESHOLD:
                    sent_signals.append(result)

        await provider.close()
        await callback.message.delete()

        header = f"📡 PO Сигналы (демо)\n{balance_text}Источник: Pocket Option WebSocket\n\n"

        if not sent_signals:
            await callback.message.answer(
                header + "✅ Все активы просканированы.\n❌ Нет сигналов.",
                parse_mode=ParseMode.HTML, reply_markup=main_menu_kb(is_premium=user.is_premium),
            )
        else:
            await callback.message.answer(
                header + f"🔔 Найдено {len(sent_signals)} сигналов:",
                parse_mode=ParseMode.HTML,
            )
            for sig in sent_signals:
                msg = format_signal_message(sig)
                await callback.message.answer(
                    msg, parse_mode=ParseMode.HTML,
                    reply_markup=signal_actions_kb(sig.asset, sig.direction, sig.expiry),
                )
            await callback.message.answer(
                "✅ Сигналы с реальных котировок PO!",
                reply_markup=main_menu_kb(is_premium=user.is_premium),
            )

            async with async_session_factory() as session:
                svc = UserService(session)
                for sig in sent_signals:
                    db_signal = Signal(
                        user_id=user.id, asset=sig.asset, direction=sig.direction,
                        expiry=sig.expiry, entry_price=sig.entry_price,
                        confidence=sig.confidence, confluence_score=sig.confluence_score,
                        result="pending",
                    )
                    session.add(db_signal)
                    await svc.increment_signals_today(user)
                await session.commit()

    except Exception as exc:
        logger.exception("Ошибка PO сигналов: %s", exc)
        await callback.message.edit_text(
            f"❌ Ошибка: {exc}",
            parse_mode=ParseMode.HTML, reply_markup=back_to_main_kb(),
        )


# ═══════════════════════════════════════════════════════════════════════
# 🔔 Активные сигналы
# ═══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "active_signals")
async def active_signals(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    from sqlalchemy import select

    async with async_session_factory() as session:
        service = UserService(session)
        user = await service.get_by_telegram_id(tg_id)
        if not user:
            await callback.answer("Напиши /start", show_alert=True)
            return
        if not user.is_premium and user.signals_today >= config.FREE_SIGNALS_PER_DAY:
            await callback.message.edit_text(
                FREE_LIMIT_MESSAGE.format(used=user.signals_today, limit=config.FREE_SIGNALS_PER_DAY),
                parse_mode=ParseMode.HTML, reply_markup=subscription_kb(),
            )
            await callback.answer()
            return

        stmt = select(Signal).where(Signal.user_id == user.id).order_by(Signal.created_at.desc()).limit(5)
        result = await session.execute(stmt)
        signals = result.scalars().all()

    if not signals:
        await callback.message.edit_text(
            "Пока нет сигналов.", parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(is_premium=user.is_premium),
        )
        await callback.answer()
        return

    await callback.message.delete()
    for sig in signals:
        robj = SignalResult(
            asset=sig.asset, direction=sig.direction, expiry=sig.expiry,
            entry_price=sig.entry_price, confidence=sig.confidence,
            confluence_score=sig.confluence_score, is_valid=True,
        )
        await callback.message.answer(
            format_signal_message(robj), parse_mode=ParseMode.HTML,
            reply_markup=signal_actions_kb(sig.asset, sig.direction, sig.expiry),
        )
    await callback.message.answer("Последние 5 сигналов.", reply_markup=main_menu_kb(is_premium=user.is_premium))
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════
# 📈 Статистика
# ═══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_statistics")
async def my_statistics(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id

    async with async_session_factory() as session:
        service = UserService(session)
        stats = await service.get_statistics(tg_id)
        if stats is None:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        role_emoji = "💎" if stats["is_premium"] else "🆓"
        premium_until = stats["premium_until"].strftime("%d.%m.%Y") if stats["premium_until"] else "Нет"
        text_stats = STATISTICS_MESSAGE.format(
            role=f"{role_emoji} {'Premium' if stats['is_premium'] else 'Free'}",
            total_signals=stats["total_signals"], wins=stats["wins"],
            win_rate=stats["win_rate"], losses=stats["losses"],
            pending=stats["pending"], best_profit=stats["best_profit"],
            premium_until=premium_until,
        )

    await callback.message.edit_text(text_stats, parse_mode=ParseMode.HTML)

    if stats["is_premium"] and stats["total_signals"] > 0:
        try:
            pie = win_loss_chart(stats["wins"], stats["losses"], stats["pending"])
            await callback.message.answer_photo(BufferedInputFile(pie.read(), filename="winloss.png"), caption="Соотношение сделок")

            gauge = win_rate_gauge(stats["win_rate"])
            await callback.message.answer_photo(BufferedInputFile(gauge.read(), filename="winrate.png"), caption="Процент успешных сделок")
        except Exception as exc:
            logger.warning("Ошибка графиков: %s", exc)

    await callback.message.answer("Статистика загружена.", reply_markup=main_menu_kb(is_premium=stats["is_premium"]))
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════
# 💎 Premium
# ═══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "premium_info")
async def premium_info_handler(callback: CallbackQuery) -> None:
    from app.bot.premium_router import premium_plans_kb
    await callback.message.edit_text(
        PREMIUM_INFO_MESSAGE, parse_mode=ParseMode.HTML, reply_markup=premium_plans_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "vip_analysis")
async def vip_analysis_handler(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id

    async with async_session_factory() as session:
        service = UserService(session)
        user = await service.get_by_telegram_id(tg_id)
        if not user or not user.is_premium:
            await callback.message.edit_text(
                "Эта функция только для Premium.", parse_mode=ParseMode.HTML, reply_markup=subscription_kb(),
            )
            await callback.answer()
            return

    await callback.message.edit_text("Загружаю VIP данные...", parse_mode=ParseMode.HTML)
    await callback.answer()

    try:
        aggregator = MarketDataAggregator()
        data_map = await aggregator.fetch_all(assets=DEFAULT_ASSETS, timeframe="5m")

        lines = ["💎 VIP Аналитика рынка\n"]
        for asset, df in data_map.items():
            close = df["close"].astype(float)
            high = df["high"].astype(float)
            low = df["low"].astype(float)
            analyzer = SignalAnalyzer(asset=asset, expiry="5m")
            result = analyzer.analyze(df)
            prob_up = ai_predictor.predict(result.indicators) * 100
            ai_dir = ai_predictor.get_ai_direction(result.indicators)
            ai_icon = {"UP": "🟢", "DOWN": "🔴", None: "⚪"}.get(ai_dir, "⚪")
            recent_high = float(high.tail(20).max())
            recent_low = float(low.tail(20).min())
            mid = (recent_high + recent_low) / 2
            lines.append(
                f"<b>{asset}</b>\n"
                f"AI: {ai_icon} {ai_dir or 'Нейтрально'} (P={prob_up:.1f}%)\n"
                f"S/R: {recent_low:.5f} / {mid:.5f} / {recent_high:.5f}\n"
            )

        await callback.message.edit_text(
            "\n".join(lines), parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(is_premium=True),
        )
    except Exception as exc:
        logger.exception("VIP ошибка: %s", exc)
        await callback.message.edit_text(f"Ошибка: {exc}", parse_mode=ParseMode.HTML, reply_markup=back_to_main_kb())


# ═══════════════════════════════════════════════════════════════════════
# ⚙️ Настройки
# ═══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "settings")
async def settings_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "⚙️ Настройки", parse_mode=ParseMode.HTML, reply_markup=settings_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "set_timeframe")
async def set_timeframe(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "⏱ Выбери таймфрейм:", parse_mode=ParseMode.HTML, reply_markup=timeframe_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tf:"))
async def timeframe_selected(callback: CallbackQuery) -> None:
    tf = callback.data.split(":")[1]
    names = {"1m": "1 минута", "3m": "3 минуты", "5m": "5 минут"}
    await callback.answer(f"Таймфрейм: {names.get(tf, tf)}", show_alert=True)
    await callback.message.edit_text(
        f"Таймфрейм: {names.get(tf, tf)}", parse_mode=ParseMode.HTML, reply_markup=settings_kb(),
    )


@router.callback_query(F.data == "favorite_assets")
async def favorite_assets(callback: CallbackQuery) -> None:
    assets = "\n".join(f"• {a}" for a in DEFAULT_ASSETS)
    await callback.message.edit_text(
        f"📊 Избранные активы\n\n{assets}", parse_mode=ParseMode.HTML, reply_markup=settings_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(callback: CallbackQuery) -> None:
    await callback.answer("Заглушка", show_alert=True)


@router.callback_query(F.data == "referrals")
async def referrals_menu(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    async with async_session_factory() as session:
        service = UserService(session)
        user = await service.get_by_telegram_id(tg_id)
        if not user:
            await callback.answer("Напиши /start", show_alert=True)
            return
        bot_username = (await callback.bot.me()).username
        link = f"https://t.me/{bot_username}?start=ref_{user.referral_code}"
        count = len(user.referrals) if user.referrals else 0
        bonus = count * config.REFERRAL_BONUS_DAYS

    await callback.message.edit_text(
        REFERRAL_MESSAGE.format(referral_link=link, count=count, bonus_days=bonus),
        parse_mode=ParseMode.HTML, reply_markup=back_to_main_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("trade_result:"))
async def trade_result_callback(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Ошибка", show_alert=True)
        return
    direction, asset = parts[1], parts[2]
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    await callback.message.edit_text(
        f"📝 Результат сделки\n\nАктив: {asset}\nНаправление: {direction}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Прибыль +80%", callback_data=f"trade_win:80:{asset}")],
            [InlineKeyboardButton(text="Прибыль +60%", callback_data=f"trade_win:60:{asset}")],
            [InlineKeyboardButton(text="Убыток", callback_data=f"trade_loss:{asset}")],
            [InlineKeyboardButton(text="Пропустить", callback_data="back_to_main")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("trade_win:"))
async def trade_win(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    profit_pct = float(parts[1])
    asset = parts[2]
    await callback.message.edit_text(
        f"Отлично! +{profit_pct}% на {asset}", parse_mode=ParseMode.HTML, reply_markup=back_to_main_kb(),
    )
    await callback.answer("✅", show_alert=True)


@router.callback_query(F.data.startswith("trade_loss:"))
async def trade_loss(callback: CallbackQuery) -> None:
    asset = callback.data.split(":")[1]
    await callback.message.edit_text(
        f"Не повезло на {asset}", parse_mode=ParseMode.HTML, reply_markup=back_to_main_kb(),
    )
    await callback.answer("❌", show_alert=True)


@router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    await callback.answer("Команда не распознана", show_alert=False)
