"""Async engine и sessionmaker."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Создать AsyncEngine с пулом.

    Для asyncio SQLAlchemy сама выбирает AsyncAdaptedQueuePool — настраивать driver-pool не нужно.
    """
    return create_async_engine(
        settings.postgres_url,
        echo=settings.postgres_echo,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout=settings.postgres_pool_timeout,
        pool_recycle=settings.postgres_pool_recycle,
        pool_pre_ping=True,
        future=True,
    )


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
