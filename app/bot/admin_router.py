"""Админ-роутер для выдачи Premium."""

import logging
import os

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from app.db.base import get_session
from app.db.models import User
from app.services.user_service import UserService

logger = logging.getLogger(__name__)
router = Router(name="admin")

ADMIN_IDS = []
raw = os.getenv("ADMIN_IDS", "")
if raw:
    for x in raw.split(","):
        x = x.strip()
        if x:
            ADMIN_IDS.append(int(x))


@router.message(Command("addpremium"))
async def cmd_add_premium(message: Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Нет прав администратора.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "Использование:\n/addpremium 30 @username\n/addpremium 30 123456789"
        )
        return

    try:
        days = int(args[1])
    except ValueError:
        await message.answer("Укажи число дней (например: 30)")
        return

    target = args[2]
    try:
        async with get_session() as session:
            service = UserService(session)
            if target.startswith("@"):
                result = await session.execute(
                    select(User).where(User.username == target[1:])
                )
                user = result.scalar_one_or_none()
            else:
                user = await service.get_by_telegram_id(int(target))

            if not user:
                await message.answer(f"Пользователь {target} не найден.")
                return

            await service.add_premium_days(user, days)
            await session.commit()
            await message.answer(
                f"Premium {days} дней выдано @{user.username or user.telegram_id}"
            )
    except Exception as exc:
        logger.exception("Ошибка: %s", exc)
        await message.answer(f"Ошибка: {exc}")


@router.message(Command("mypremium"))
async def cmd_my_premium(message: Message) -> None:
    tg_id = message.from_user.id
    async with get_session() as session:
        service = UserService(session)
        user = await service.get_by_telegram_id(tg_id)

    if not user:
        await message.answer("Сначала напиши /start")
        return

    if tg_id in ADMIN_IDS:
        status = "Администратор - безлимитный Premium"
    elif user.is_premium:
        until = user.premium_until.strftime("%d.%m.%Y")
        status = f"Premium до {until}"
    else:
        status = "Free - 5 сигналов в день"

    await message.answer(f"Твой статус: {status}")
