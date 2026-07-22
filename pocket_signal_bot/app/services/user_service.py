"""
Сервис управления пользователями.
CRUD-операции, статистика, реферальная система.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.db.models import Referral, Signal, Subscription, TradeLog, User

logger = logging.getLogger(__name__)


class UserService:
    """Сервис для работы с пользователями."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        referrer_code: str | None = None,
    ) -> User:
        """Получить пользователя или создать нового."""
        # Ищем существующего
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if user is not None:
            # Обновляем данные при каждом входе
            if username:
                user.username = username
            if first_name:
                user.first_name = first_name
            if last_name:
                user.last_name = last_name
            await self.session.commit()
            return user

        # Создаём нового
        referral_code = self._generate_referral_code()

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            referral_code=referral_code,
            role="free",
        )
        self.session.add(user)
        await self.session.flush()

        # Обрабатываем реферальную ссылку
        if referrer_code:
            await self._process_referral(user, referrer_code)

        await self.session.commit()
        logger.info(
            "Новый пользователь: @%s (tg_id=%d, ref=%s)",
            username or "unknown", telegram_id, referral_code,
        )
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Найти пользователя по Telegram ID."""
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> User | None:
        """Найти пользователя по реферальному коду."""
        result = await self.session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    async def increment_signals_today(self, user: User) -> None:
        """Увеличить счётчик сигналов за день."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        if user.last_signal_date is None or user.last_signal_date < today_start:
            user.signals_today = 1
        else:
            user.signals_today += 1

        user.last_signal_date = datetime.now(timezone.utc)
        await self.session.commit()

    async def check_signal_limit(self, user: User) -> bool:
        """Проверить, может ли пользователь получить сигнал."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        if user.last_signal_date is None or user.last_signal_date < today_start:
            user.signals_today = 0
            await self.session.commit()
            return True

        if user.is_premium:
            return user.signals_today < config.PREMIUM_SIGNALS_PER_DAY

        return user.signals_today < config.FREE_SIGNALS_PER_DAY

    async def add_premium_days(self, user: User, days: int) -> None:
        """Добавить дни Premium подписки."""
        now = datetime.now(timezone.utc)

        if user.premium_until is None or user.premium_until < now:
            user.premium_until = now + timedelta(days=days)
        else:
            user.premium_until += timedelta(days=days)

        user.role = "premium"
        await self.session.commit()

        logger.info(
            "Premium продлён пользователю %d: +%d дней (до %s)",
            user.telegram_id, days, user.premium_until,
        )

    async def get_statistics(self, telegram_id: int) -> dict[str, Any] | None:
        """Получить статистику пользователя."""
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            return None

        # Агрегация сигналов
        signals_query = select(Signal).where(Signal.user_id == user.id)
        signals_result = await self.session.execute(signals_query)
        signals = signals_result.scalars().all()

        total = len(signals)
        wins = sum(1 for s in signals if s.result == "win")
        losses = sum(1 for s in signals if s.result == "loss")
        pending = sum(1 for s in signals if s.result is None or s.result == "pending")

        # Лучшая прибыль
        trades_query = (
            select(func.coalesce(func.max(TradeLog.profit), 0.0))
            .where(TradeLog.user_id == user.id)
        )
        best_profit_result = await self.session.execute(trades_query)
        best_profit = best_profit_result.scalar() or 0.0

        win_rate = (wins / total * 100) if total > 0 else 0.0

        return {
            "total_signals": total,
            "wins": wins,
            "losses": losses,
            "pending": pending,
            "win_rate": win_rate,
            "best_profit": best_profit,
            "is_premium": user.is_premium,
            "premium_until": user.premium_until,
        }

    async def _process_referral(self, new_user: User, referrer_code: str) -> None:
        """Обработать реферальный переход."""
        referrer = await self.get_by_referral_code(referrer_code)
        if referrer is None or referrer.id == new_user.id:
            return

        # Создаём запись о реферале
        referral = Referral(
            referrer_id=referrer.id,
            referred_id=new_user.id,
            bonus_granted=False,
        )
        self.session.add(referral)
        await self.session.flush()

        # Начисляем бонус рефереру
        await self.add_premium_days(referrer, config.REFERRAL_BONUS_DAYS)
        referral.bonus_granted = True

        # Новичок тоже получает 1 день Premium
        await self.add_premium_days(new_user, 1)

        logger.info(
            "Реферал: пользователь %d приглашён %d. Бонус начислен.",
            new_user.id, referrer.id,
        )

    @staticmethod
    def _generate_referral_code() -> str:
        """Генерирует уникальный реферальный код."""
        return secrets.token_hex(6)  # 12 символов
