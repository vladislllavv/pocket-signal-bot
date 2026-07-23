"""
pocket_signal_bot — Конфигурация приложения.
Загрузка из .env с валидацией типов.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Config:
    # --- Telegram ---
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # --- Pocket Option ---
    PO_EMAIL: str = os.getenv("PO_EMAIL", "")
    PO_PASSWORD: str = os.getenv("PO_PASSWORD", "")
    PO_SSID: str = os.getenv("PO_SSID", "")

    # --- Database ---
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{DATA_DIR}/bot.db",
    )

    # --- Лимиты подписок ---
    FREE_SIGNALS_PER_DAY: int = int(os.getenv("FREE_SIGNALS_PER_DAY", "5"))
    PREMIUM_SIGNALS_PER_DAY: int = int(os.getenv("PREMIUM_SIGNALS_PER_DAY", "999"))
    REFERRAL_BONUS_DAYS: int = 3  # дней Premium за реферала

    # --- Аналитика ---
    MIN_CONFLUENCE_SCORE: float = 0.35       # мин. схождение индикаторов для сигнала
    SIGNAL_CONFIDENCE_THRESHOLD: float = 0.45  # порог уверенности

    # --- Планировщик ---
    SIGNAL_CHECK_INTERVAL_SEC: int = 180  # проверка каждые 3 минуты

    # --- Логирование ---
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", str(DATA_DIR / "bot.log"))

    # --- Webhook (TradingView) ---
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8080"))

    # --- Платежи ---
    PAYMENT_PROVIDER: str = os.getenv("PAYMENT_PROVIDER", "stub")

    # --- Прочее ---
    DEEPLINK_PO_BASE: str = "https://pocketoption.com/en/trading"


config = Config()
