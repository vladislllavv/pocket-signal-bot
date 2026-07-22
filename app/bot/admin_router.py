"""
Админ-роутер для управления подписками.
Команды только для ADMIN_IDS.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from app.db.base import get_session
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = Router(name="admin")

# ID админов (из переменной окружения или задать вручную)
import os
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS


@router.message(Command("addpremium"))
async def cmd_add_premium(message: Message) -> None:
    """Выдать Premium пользователю.
    
    Использование: /addpremium 30 @username
    или: /addpremium 30 123456789
    """
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У тебя нет прав администратора.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "📝 <b>Как использовать:</b>\n\n"
            "По username:\n"
            "<code>/addpremium 30 @username</code>\n\n"
            "По Telegram ID:\n"
            "<code>/addpremium 30 123456789</code>\n\n"
            "Где 30 — количество дней Premium.",
            parse_mode=ParseMode.HTML,
        )
        return

    days_str = args[1]
    target = args[2]

    try:
        days = int(days_str)
    except ValueError:
        await message.answer("❌ Укажи число дней (например: 30)")
        return

    # Ищем пользователя
    async with get_session() as session:
        service = UserService(session)

        if target.startswith("@"):
            # По username
            username = target[1:]
            from sqlalchemy import select
            from app.db.models import User
            result = await session.execute(
                select(User).where(User.username == username)
            )
            user = result.scalar_one_or_none()
        else:
            # По Telegram ID
            try:
                tg_id = int(target)
                user = await service.get_by_telegram_id(tg_id)
            except ValueError:
                await message.answer("❌ Неверный формат ID")
                return

        if not user:
            await message.answer(f"❌ Пользователь {target} не найден.")
            return

        # Выдаём Premium
        await service.add_premium_days(user, days)
        await session.commit()

        await message.answer(
            f"✅ <b>Premium выдан!</b>\n\n"
            f"👤 Пользователь: @{user.username or user.telegram_id}\n"
            f"📅 Дней: {days}\n"
            f"📆 Действует до: {user.premium_until.strftime('%d.%m.%Y') if user.premium_until else 'навсегда'}\n\n"
            f"🔥 Теперь у пользователя безлимитные сигналы!",
            parse_mode=ParseMode.HTML,
        )

    except Exception as exc:
        logger.exception("Ошибка выдачи Premium: %s", exc)
        await message.answer(f"❌ Ошибка: {exc}")


@router.message(Command("mypremium"))
async def cmd_my_premium(message: Message) -> None:
    """Проверить свой статус Premium."""
    tg_id = message.from_user.id

    async with get_session() as session:
        service = UserService(session)
        user = await service.get_by_telegram_id(tg_id)

        if not user:
            await message.answer("Напиши /start")
            return

        if is_admin(tg_id):
            status = "👑 <b>Администратор</b> — безлимитный Premium навсегда"
        elif user.is_premium:
            until = user.premium_until.strftime("%d.%m.%Y") if user.premium_until else "неизвестно"
            status = f"💎 <b>Premium</b> — до {until}"
        else:
            status = "🆓 <b>Free</b> — 5 сигналов в день"

        await message.answer(
            f"👤 <b>Твой статус:</b>\n\n"
            f"{status}\n\n"
            f"📊 Сигналов сегодня: {user.signals_today}/{user.signals_remaining_today + user.signals_today}",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("allusers"))
async def cmd_all_users(message: Message) -> None:
    """Показать всех пользователей (только админ)."""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав.")
        return

    async with get_session() as session:
        from sqlalchemy import select
        from app.db.models import User

        result = await session.execute(select(User).order_by(User.id.desc()).limit(20))
        users = result.scalars().all()

        text = "📋 <b>Последние 20 пользователей:</b>\n\n"
        for u in users:
            premium_status = "💎" if u.is_premium else "🆓"
            text += f"{u.id}. {premium_status} @{u.username or '—'} (ID: {u.telegram_id})\n"

        await message.answer(text, parse_mode=ParseMode.HTML)
