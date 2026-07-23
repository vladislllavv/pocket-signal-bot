"""
ORM-модели SQLAlchemy (async) для всех сущностей бота.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    role: Mapped[str] = mapped_column(String(16), default="free", nullable=False)
    premium_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    signals_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_signal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    referrer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    signals = relationship("Signal", back_populates="user", lazy="selectin")
    referrals = relationship("Referral", back_populates="referrer", foreign_keys="Referral.referrer_id")
    trades = relationship("TradeLog", back_populates="user", lazy="selectin")

    @property
    def is_premium(self) -> bool:
        if self.role == "admin":
            return True
        if self.premium_until is None:
            return False
        # SQLite не хранит timezone, проверяем
        if self.premium_until.tzinfo is not None:
            return self.premium_until > datetime.now(timezone.utc)
        else:
            return self.premium_until > datetime.utcnow()

    @property
    def signals_remaining_today(self) -> int:
        from app.config import config
        if self.is_premium:
            return config.PREMIUM_SIGNALS_PER_DAY
        return max(0, config.FREE_SIGNALS_PER_DAY - self.signals_today)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, tg={self.telegram_id}, role={self.role})>"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    payment_provider: Mapped[str] = mapped_column(String(32), default="stub")
    payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, user={self.user_id}, plan={self.plan})>"


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    expiry: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confluence_score: Mapped[float] = mapped_column(Float, nullable=False)
    rsi_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bb_position: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stoch_signal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    atr_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility_filter: Mapped[bool] = mapped_column(Boolean, default=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    closed_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="signals")

    def __repr__(self) -> str:
        return f"<Signal(id={self.id}, asset={self.asset}, dir={self.direction}, conf={self.confidence:.2f})>"


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    referred_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    bonus_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    referrer = relationship("User", back_populates="referrals", foreign_keys=[referrer_id])
    referred = relationship("User", foreign_keys=[referred_id])

    def __repr__(self) -> str:
        return f"<Referral({self.referrer_id} -> {self.referred_id})>"


class TradeLog(Base):
    __tablename__ = "trade_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    signal_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("signals.id"), nullable=True)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    profit: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="trades")

    def __repr__(self) -> str:
        return f"<TradeLog(user={self.user_id}, {self.asset} {self.direction} {self.result})>"
