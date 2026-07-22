"""
Форматирование сообщений для Telegram.
Все сообщения используют HTML-разметку (parse_mode="HTML").
"""

from __future__ import annotations

from app.analytics.analyzer import SignalResult


# ---------------------------------------------------------------------------
# Главное меню
# ---------------------------------------------------------------------------

WELCOME_MESSAGE = (
    "🤖 <b>Pocket Signal Bot</b>\n\n"
    "Привет! Я анализирую рынки в реальном времени и "
    "генерирую торговые сигналы для Pocket Option.\n\n"
    "📊 <b>Мои возможности:</b>\n"
    "• Анализ 6+ индикаторов на каждом активе\n"
    "• Система Confluence — сигналы только при схождении индикаторов\n"
    "• Фильтр волатильности — никаких сигналов во флэте\n"
    "• Мгновенная отправка сигналов в Telegram\n\n"
    "👇 <b>Выбери раздел в меню ниже:</b>"
)

FREE_LIMIT_MESSAGE = (
    "⚠️ <b>Дневной лимит исчерпан</b>\n\n"
    "Сегодня ты получил {used}/{limit} бесплатных сигналов.\n\n"
    "💎 Оформи Premium-подписку для получения неограниченного "
    "количества сигналов + VIP аналитику с расширенными индикаторами!"
)

# ---------------------------------------------------------------------------
# Форматирование сигнала
# ---------------------------------------------------------------------------

def format_signal_message(signal: SignalResult) -> str:
    """
    Форматирует сигнал в красивое HTML-сообщение.

    Пример:
    ─────────────────────────────
    🚀 СИГНАЛ НА ПОКУПКУ
    ─────────────────────────────
    Актив:    BTC/USD
    Напр.:    🟢 UP (CALL)
    Экспирация: 3 мин
    Точка входа: 67543.21
    Уверенность: 82.5% 🔥
    ─────────────────────────────
    📊 Индикаторы:
    RSI:      32.4 (oversold) ✅
    MACD:     Бычье пересечение ✅
    BB:       Ниже нижней полосы ✅
    Stoch:    Перепроданность ✅
    ATR:      0.0015 (OK)
    """
    if not signal.is_valid:
        return (
            "⛔ <b>Нет валидного сигнала</b>\n"
            f"Причина: {signal.reason or 'неизвестна'}"
        )

    emoji_dir = "🟢" if signal.direction == "UP" else "🔴"
    label_dir = "UP (CALL)" if signal.direction == "UP" else "DOWN (PUT)"
    confidence_pct = signal.confidence * 100

    # Определяем иконку уверенности
    if confidence_pct >= 85:
        conf_icon = "🔥🔥🔥"
    elif confidence_pct >= 75:
        conf_icon = "🔥🔥"
    elif confidence_pct >= 65:
        conf_icon = "🔥"
    else:
        conf_icon = "📊"

    ind = signal.indicators

    # Строки индикаторов
    def rsi_str() -> str:
        if ind.rsi is None:
            return "❌ Нет данных"
        icon = "✅" if ind.rsi_signal in ("oversold", "overbought") else "➖"
        return f"{ind.rsi:.1f} ({ind.rsi_signal}) {icon}"

    def macd_str() -> str:
        if ind.macd_cross is None and ind.macd_signal is None:
            return "❌ Нет данных"
        if ind.macd_cross == "up":
            return f"Бычье пересечение ✅"
        elif ind.macd_cross == "down":
            return f"Медвежье пересечение ✅"
        elif ind.macd_signal:
            return f"{ind.macd_signal} ➖"
        return "Нейтрально ➖"

    def bb_str() -> str:
        if ind.bb_position is None:
            return "❌ Нет данных"
        pos_names = {
            "above_upper": "Выше верхней ✅",
            "below_lower": "Ниже нижней ✅",
            "inside": "Внутри канала ➖",
        }
        return pos_names.get(ind.bb_position, ind.bb_position)

    def stoch_str() -> str:
        if ind.stoch_signal is None:
            return "❌ Нет данных"
        icon = "✅" if ind.stoch_signal in ("oversold", "overbought") else "➖"
        return f"{ind.stoch_signal} ({ind.stoch_k}/{ind.stoch_d}) {icon}"

    def atr_str() -> str:
        if ind.atr is None:
            return "❌ Нет данных"
        status = "✅" if ind.atr_ratio and ind.atr_ratio >= 0.001 else "⚠️"
        return f"{ind.atr:.6f} (ratio: {ind.atr_ratio:.6f}) {status}"

    message = (
        f"╔══════════════════════════╗\n"
        f"     {emoji_dir} <b>СИГНАЛ {signal.direction}</b>\n"
        f"╚══════════════════════════╝\n\n"
        f"<b>Актив:</b>       <code>{signal.asset}</code>\n"
        f"<b>Направление:</b> {emoji_dir} {label_dir}\n"
        f"<b>Экспирация:</b>  ⏱ {signal.expiry}\n"
        f"<b>Точка входа:</b> 💰 <code>{signal.entry_price:.5f}</code>\n"
        f"<b>Уверенность:</b> {conf_icon} <b>{confidence_pct:.1f}%</b>\n"
        f"<b>Confluence:</b>  📐 {(signal.confluence_score * 100):.1f}%\n\n"
        f"─────────────────────────────\n"
        f"📊 <b>Индикаторы:</b>\n"
        f"RSI:        {rsi_str()}\n"
        f"MACD:       {macd_str()}\n"
        f"Bollinger:  {bb_str()}\n"
        f"Stochastic: {stoch_str()}\n"
        f"ATR:        {atr_str()}\n"
        f"─────────────────────────────\n"
        f"⚠️ <i>Управляй рисками. Не рискуй более 1-2% депозита.</i>"
    )

    return message


# ---------------------------------------------------------------------------
# Прочие сообщения
# ---------------------------------------------------------------------------

PREMIUM_INFO_MESSAGE = (
    "💎 <b>Premium Подписка</b>\n\n"
    "🌟 <b>Что ты получишь:</b>\n"
    "• ♾️ Неограниченное количество сигналов\n"
    "• 📊 VIP-аналитика с расширенными индикаторами\n"
    "• 📈 Индекс силы тренда (ADX)\n"
    "• 🎯 Уровни поддержки/сопротивления\n"
    "• 🔔 Приоритетная отправка сигналов\n"
    "• 📱 Доступ к статистике и истории\n\n"
    "💰 <b>Тарифы:</b>\n"
    "• Неделя  — $9.99\n"
    "• Месяц   — $24.99\n"
    "• Год     — $99.99 🔥 (-67%)\n\n"
    "💳 <i>Оплата через Telegram Stars / ЮKassa</i>"
)

REFERRAL_MESSAGE = (
    "👥 <b>Реферальная программа</b>\n\n"
    "Пригласи друга и получи <b>+3 дня Premium</b> "
    "за каждого приведённого пользователя!\n\n"
    "🔗 Твоя реферальная ссылка:\n"
    "<code>{referral_link}</code>\n\n"
    "👥 Приглашено друзей: <b>{count}</b>\n"
    "🎁 Получено дней Premium: <b>{bonus_days}</b>"
)

STATISTICS_MESSAGE = (
    "📈 <b>Моя статистика</b>\n\n"
    "👤 Статус: <b>{role}</b>\n"
    "📊 Сигналов получено: <b>{total_signals}</b>\n"
    "✅ Успешных: <b>{wins}</b> ({win_rate:.1f}%)\n"
    "❌ Убыточных: <b>{losses}</b>\n"
    "🔄 Не закрыто: <b>{pending}</b>\n\n"
    "💰 Лучшая сделка: +{best_profit:.2f}$\n"
    "📅 Premium до: {premium_until}"
)
