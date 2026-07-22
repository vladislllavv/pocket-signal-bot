"""
Вспомогательные функции.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any


def generate_tx_id() -> str:
    """Генерация уникального ID транзакции."""
    ts = int(datetime.now(timezone.utc).timestamp())
    rand = secrets.token_hex(4)
    return f"TX-{ts}-{rand}"


def truncate_price(price: float, decimals: int = 5) -> float:
    """Обрезать цену до указанного количества знаков."""
    return round(price, decimals)


def format_timestamp(dt: datetime | None) -> str:
    """Форматировать timestamp для вывода."""
    if dt is None:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M UTC")


def safe_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """
    Безопасный доступ к вложенным ключам словаря.
    safe_get(data, "a", "b", "c") → data["a"]["b"]["c"] или default.
    """
    for key in keys:
        try:
            data = data[key]
        except (KeyError, TypeError, IndexError):
            return default
    return data
