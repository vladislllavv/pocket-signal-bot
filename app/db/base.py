"""
Асинхронный движок SQLAlchemy + фабрика сессий.
Поддерживает SQLite (aiosqlite) и PostgreSQL (asyncpg).
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import config


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""
    pass


engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Создаёт таблицы при первом запуске."""
    from app.db.models import (  # noqa: F401
        User,
        Signal,
        Subscription,
        Referral,
        TradeLog,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
