"""Smoke-тест подключения к реальному PostgreSQL (поднимается docker compose в CI).

Запускается только если доступен POSTGRES_HOST — в CI это всегда true.
Локально: `make up`, затем `uv run pytest tests/integration -v`.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="Нет реального PG — запусти make up или CI",
)
class TestDatabaseSmoke:
    async def test_connects_and_has_users_table(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.connect() as conn:
                # Миграции должны быть применены до запуска тестов (CI делает alembic upgrade head)
                res = await conn.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_name='users');"
                    )
                )
                assert res.scalar_one() is True
        finally:
            await engine.dispose()

    async def test_age_ratings_seeded(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.connect() as conn:
                res = await conn.execute(text("SELECT count(*) FROM age_ratings"))
                assert res.scalar_one() == 5
                res = await conn.execute(text("SELECT count(*) FROM fandoms"))
                assert res.scalar_one() >= 5
        finally:
            await engine.dispose()
