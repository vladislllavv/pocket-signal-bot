"""Premium Router — управление подписками через Telegram Stars и ЮKassa."""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.config import config
from app.db.base import async_session_factory
from app.db.models import Subscription, User
from app.services.user_service import UserService

logger = logging.getLogger(__name__)
router = Router(name="premium")

STAR_PLANS = {
    "weekly": {"stars": 25, "days": 7, "label": "Неделя", "discount": ""},
    "monthly": {"stars": 65, "days": 30, "label": "Месяц", "discount": "🔥 -13%"},
    "yearly": {"stars": 250, "days": 365, "label": "Год", "discount": "🔥🔥 -67%"},
}

USD_PLANS = {
    "weekly": {"price": 9.99, "days": 7, "label": "Неделя", "discount": ""},
    "monthly": {"price": 24.99, "days": 30, "label": "Месяц", "discount": "🔥 -13%"},
    "yearly": {"price": 99.99, "days": 365, "label": "Год", "discount": "🔥🔥 -67%"},
}


def premium_plans_kb() -> InlineKeyboardMarkup:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐ Купить за Telegram Stars", callback_data="pay_method:stars"))
    builder.row(InlineKeyboardButton(text="💳 Купить за USD (карта/крипта)", callback_data="pay_method:youkassa"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))
    return builder.as_markup()


def plan_selector_kb(payment_method: str) -> InlineKeyboardMarkup:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    plans = STAR_PLANS if payment_method == "stars" else USD_PLANS
    currency_symbol = "⭐" if payment_method == "stars" else "$"
    for plan_id, info in plans.items():
        price_str = f"{info['stars']} Stars" if payment_method == "stars" else f"${info['price']}"
        label = f"{currency_symbol} {info['label']} — {price_str} {info['discount']}"
        builder.row(InlineKeyboardButton(text=label, callback_data=f"plan:{payment_method}:{plan_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="premium_info"))
    return builder.as_markup()


@router.message(Command("premium"))
async def cmd_premium(message: Message) -> None:
    await message.answer(
        "💎 Premium Подписка\n\nПолучи неограниченные сигналы и VIP-аналитику.\n\nСпособы оплаты:\n⭐ Telegram Stars\n💳 ЮKassa / Crypto",
        parse_mode=ParseMode.HTML,
        reply_markup=premium_plans_kb(),
    )


@router.callback_query(F.data == "premium_info")
async def premium_info(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "💎 Premium Подписка\n\nСпособы оплаты:\n⭐ Telegram Stars\n💳 ЮKassa / Crypto",
        parse_mode=ParseMode.HTML,
        reply_markup=premium_plans_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_method:"))
async def pay_method_selected(callback: CallbackQuery) -> None:
    method = callback.data.split(":")[1]
    method_label = "Telegram Stars ⭐" if method == "stars" else "USD (карта/крипта) 💳"
    await callback.message.edit_text(
        f"Выбери тариф\n\nСпособ оплаты: {method_label}",
        parse_mode=ParseMode.HTML,
        reply_markup=plan_selector_kb(method),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("plan:"))
async def plan_selected(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    payment_method = parts[1]
    plan_id = parts[2]
    if payment_method == "stars":
        await _handle_stars_payment(callback, plan_id)
    elif payment_method == "youkassa":
        await _handle_youkassa_payment(callback, plan_id)


async def _handle_stars_payment(callback: CallbackQuery, plan_id: str) -> None:
    plan = STAR_PLANS.get(plan_id)
    if not plan:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    user_id = callback.from_user.id
    prices = [LabeledPrice(label=f"Premium {plan['label']}", amount=plan["stars"])]
    try:
        await callback.message.delete()
        await callback.message.answer_invoice(
            title="💎 Premium Подписка",
            description=f"Тариф: {plan['label']}\nДлительность: {plan['days']} дней",
            payload=f"premium:{plan_id}:{user_id}:stars",
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter=f"premium_{plan_id}",
            need_email=False,
            need_phone_number=False,
            is_flexible=False,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data="premium_info")]
            ]),
        )
        await callback.answer()
    except Exception as exc:
        logger.error("Ошибка создания Stars инвойса: %s", exc)
        await callback.answer("Ошибка создания платежа", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_q: PreCheckoutQuery) -> None:
    await pre_checkout_q.answer(ok=True)


@router.message(lambda msg: msg.successful_payment is not None)
async def successful_payment(message: Message) -> None:
    payment = message.successful_payment
    payload = payment.invoice_payload
    try:
        parts = payload.split(":")
        if len(parts) < 4:
            await message.answer("Ошибка обработки платежа")
            return
        plan_id = parts[1]
        user_id = int(parts[2])
        method = parts[3]
        plans = STAR_PLANS if method == "stars" else USD_PLANS
        plan = plans.get(plan_id)
        if not plan:
            await message.answer("Неизвестный тариф")
            return
        days = plan["days"]
        tg_id = message.from_user.id
        async with async_session_factory() as session:
            service = UserService(session)
            user = await service.get_by_telegram_id(tg_id)
            if not user:
                await message.answer("Напиши /start")
                return
            await service.add_premium_days(user, days)
            now = datetime.now(timezone.utc)
            sub = Subscription(
                user_id=user.id, plan=plan_id, amount=payment.total_amount,
                currency="XTR", payment_provider="telegram_stars",
                payment_id=payment.telegram_payment_charge_id, status="completed",
                started_at=now, expires_at=now + timedelta(days=days),
            )
            session.add(sub)
            await session.commit()
        await message.answer(
            f"🎉 Premium активирован!\nТариф: {plan['label']}\nДлительность: {days} дней",
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        logger.exception("Ошибка: %s", exc)
        await message.answer("Ошибка активации Premium")


async def _handle_youkassa_payment(callback: CallbackQuery, plan_id: str) -> None:
    import secrets
    plan = USD_PLANS.get(plan_id)
    if not plan:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    user_id = callback.from_user.id
    payment_id = f"yk_{secrets.token_hex(8)}"
    payment_url = f"https://yoomoney.ru/quickpay/confirm?receiver=&sum={plan['price']}&label={payment_id}"
    await callback.message.edit_text(
        f"Оплата через ЮKassa\nТариф: {plan['label']}\nСумма: ${plan['price']:.2f}\n\nСсылка: {payment_url}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_payment:{payment_id}:{plan_id}:{user_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="premium_info")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_payment:"))
async def check_payment(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    payment_id = parts[1]
    plan_id = parts[2]
    user_id = int(parts[3])
    tg_id = callback.from_user.id
    plan = USD_PLANS.get(plan_id)
    if not plan:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    days = plan["days"]
    try:
        async with async_session_factory() as session:
            service = UserService(session)
            user = await service.get_by_telegram_id(tg_id)
            if not user:
                await callback.answer("Напиши /start", show_alert=True)
                return
            await service.add_premium_days(user, days)
            now = datetime.now(timezone.utc)
            sub = Subscription(
                user_id=user.id, plan=plan_id, amount=plan["price"],
                currency="USD", payment_provider="youkassa",
                payment_id=payment_id, status="completed",
                started_at=now, expires_at=now + timedelta(days=days),
            )
            session.add(sub)
            await session.commit()
        await callback.message.edit_text(
            f"🎉 Premium активирован!\nТариф: {plan['label']}\nДлительность: {days} дней",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer("Premium активирован!")
    except Exception as exc:
        logger.exception("Ошибка: %s", exc)
        await callback.answer("Ошибка", show_alert=True)
