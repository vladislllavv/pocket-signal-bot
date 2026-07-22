"""
Платёжная система (заглушка).
В реальном проекте здесь была бы интеграция с:
- Telegram Stars
- YooKassa
- CryptoCloud / NowPayments
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import config

logger = logging.getLogger(__name__)

# Планы подписок
PLANS = {
    "weekly": {
        "price": 9.99,
        "currency": "USD",
        "days": 7,
        "label": "Неделя",
    },
    "monthly": {
        "price": 24.99,
        "currency": "USD",
        "days": 30,
        "label": "Месяц",
    },
    "yearly": {
        "price": 99.99,
        "currency": "USD",
        "days": 365,
        "label": "Год",
    },
}


class PaymentService:
    """
    Сервис оплаты.
    В текущей реализации — заглушка, которая сразу подтверждает платеж.
    """

    def __init__(self) -> None:
        self.provider = config.PAYMENT_PROVIDER

    async def create_invoice(
        self,
        user_id: int,
        plan: str,
    ) -> dict[str, Any]:
        """
        Создать счёт на оплату.

        Returns:
            dict с ключами:
            - success: bool
            - payment_url: str (ссылка на оплату)
            - invoice_id: str
            - amount: float
        """
        plan_info = PLANS.get(plan)
        if not plan_info:
            return {"success": False, "error": "Неизвестный тариф"}

        if self.provider == "stub":
            return await self._stub_create_invoice(user_id, plan_info)
        elif self.provider == "youkassa":
            return await self._youkassa_create_invoice(user_id, plan_info)
        elif self.provider == "telegram_stars":
            return await self._stars_create_invoice(user_id, plan_info)
        else:
            return {"success": False, "error": "Неизвестный платёжный провайдер"}

    async def confirm_payment(self, payment_id: str) -> bool:
        """
        Подтвердить платеж.
        В заглушке — всегда True.
        """
        if self.provider == "stub":
            return True
        # TODO: real integration
        logger.info("Payment confirmed: %s", payment_id)
        return True

    # --- Провайдеры ---

    async def _stub_create_invoice(
        self, user_id: int, plan_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Заглушка."""
        import uuid

        invoice_id = f"stub_{uuid.uuid4().hex[:12]}"
        logger.info(
            "STUB: счёт создан user=%d, plan=%s, amount=%.2f, id=%s",
            user_id, plan_info["label"], plan_info["price"], invoice_id,
        )
        return {
            "success": True,
            "payment_url": f"https://example.com/pay/{invoice_id}",
            "invoice_id": invoice_id,
            "amount": plan_info["price"],
            "currency": plan_info["currency"],
        }

    async def _youkassa_create_invoice(
        self, user_id: int, plan_info: dict[str, Any]
    ) -> dict[str, Any]:
        """ЮKassa интеграция (заглушка)."""
        # TODO: реализовать через yookassa SDK
        return await self._stub_create_invoice(user_id, plan_info)

    async def _stars_create_invoice(
        self, user_id: int, plan_info: dict[str, Any]
    ) -> dict[str, Any]:
        """Telegram Stars (заглушка)."""
        # TODO: реализовать через Telegram Payments API
        return await self._stub_create_invoice(user_id, plan_info)
