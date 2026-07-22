"""
Inline-клавиатуры для Telegram бота.
aiogram 3.x — строго InlineKeyboardBuilder.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ---------------------------------------------------------------------------
# Главное меню
# ---------------------------------------------------------------------------

def main_menu_kb(is_premium: bool = False) -> InlineKeyboardMarkup:
    """
    Главное меню бота.
    Для premium-пользователей показывает расширенные возможности.
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="📊 Аналитика рынка",
            callback_data="market_analysis",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔔 Активные сигналы",
            callback_data="active_signals",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📈 Моя статистика",
            callback_data="my_statistics",
        ),
    )

    if is_premium:
        builder.row(
            InlineKeyboardButton(
                text="💎 VIP Аналитика",
                callback_data="vip_analysis",
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="💎 Премиум подписка",
                callback_data="premium_info",
            ),
        )

    builder.row(
        InlineKeyboardButton(
            text="⚙️ Настройки",
            callback_data="settings",
        ),
        InlineKeyboardButton(
            text="👥 Рефералы",
            callback_data="referrals",
        ),
    )

    return builder.as_markup()


# ---------------------------------------------------------------------------
# Сигнал — кнопки действий
# ---------------------------------------------------------------------------

def signal_actions_kb(
    asset: str,
    direction: str,
    expiry: str,
) -> InlineKeyboardMarkup:
    """
    Кнопки под сообщением с сигналом.
    """
    builder = InlineKeyboardBuilder()

    # Deeplink на Pocket Option
    po_url = (
        f"https://pocketoption.com/en/trading?symbol={asset}"
        f"&expiry={expiry}"
    )
    builder.row(
        InlineKeyboardButton(
            text="🚀 Торговать на Pocket Option",
            url=po_url,
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📊 Открыть график",
            url=f"https://www.tradingview.com/chart/?symbol={asset}",
        ),
        InlineKeyboardButton(
            text="✅ Сообщить о результате",
            callback_data=f"trade_result:{direction}:{asset}",
        ),
    )
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Подписка
# ---------------------------------------------------------------------------

def subscription_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора тарифа."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="📅 Неделя — $9.99",
            callback_data="subscribe:weekly",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📅 Месяц — $24.99",
            callback_data="subscribe:monthly",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📅 Год — $99.99 (🔥 -67%)",
            callback_data="subscribe:yearly",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_to_main",
        ),
    )
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------

def settings_kb() -> InlineKeyboardMarkup:
    """Клавиатура настроек."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🔔 Уведомления: Вкл/Выкл",
            callback_data="toggle_notifications",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⏱ Таймфрейм сигналов",
            callback_data="set_timeframe",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📊 Избранные активы",
            callback_data="favorite_assets",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_to_main",
        ),
    )
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Таймфреймы
# ---------------------------------------------------------------------------

def timeframe_kb() -> InlineKeyboardMarkup:
    """Выбор таймфрейма для сигналов."""
    builder = InlineKeyboardBuilder()

    for tf, label in [("1m", "1 минута"), ("3m", "3 минуты"), ("5m", "5 минут")]:
        builder.button(text=f"⏱ {label}", callback_data=f"tf:{tf}")

    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="settings",
        ),
    )
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Вспомогательные
# ---------------------------------------------------------------------------

def back_to_main_kb() -> InlineKeyboardMarkup:
    """Просто кнопка 'Назад'."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Главное меню",
            callback_data="back_to_main",
        ),
    )
    return builder.as_markup()
