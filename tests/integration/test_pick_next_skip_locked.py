"""Integration test: pick_next с FOR UPDATE SKIP LOCKED работает между двумя сессиями."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.infrastructure.db.repositories.moderation import ModerationRepository
from app.domain.shared.types import UserId


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="Нет реального PG — запусти make up или CI",
)
class TestPickNextSkipLocked:
    async def _setup_queue(self, conn) -> list[int]:
        """Создаёт пользователей, 2 фика и 2 открытых задания в БД, возвращает case_ids."""
        await conn.execute(text("INSERT INTO users (id, timezone) VALUES (1, 'UTC') ON CONFLICT DO NOTHING"))
        await conn.execute(text("INSERT INTO users (id, timezone) VALUES (2, 'UTC') ON CONFLICT DO NOTHING"))

        fandom_id = (await conn.execute(text("SELECT id FROM fandoms LIMIT 1"))).scalar_one()
        age_id = (await conn.execute(text("SELECT id FROM age_ratings LIMIT 1"))).scalar_one()

        ids = []
        for i in range(2):
            fic_id = (
                await conn.execute(
                    text(
                        "INSERT INTO fanfics (author_id, title, summary, fandom_id, age_rating_id, status) "
                        "VALUES (1, :title, 's', :fid, :ar, 'pending') RETURNING id"
                    ),
                    {"title": f"T{i}", "fid": fandom_id, "ar": age_id},
                )
            ).scalar_one()
            case_id = (
                await conn.execute(
                    text(
                        "INSERT INTO moderation_queue (fic_id, kind, submitted_by) "
                        "VALUES (:fid, 'fic_first_publish', 1) RETURNING id"
                    ),
                    {"fid": fic_id},
                )
            ).scalar_one()
            ids.append(case_id)
        return ids

    async def test_two_moderators_get_different_cases(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            # подготавливаем данные в отдельной транзакции
            async with engine.begin() as setup_conn:
                # очистим очередь от предыдущих прогонов
                await setup_conn.execute(text("DELETE FROM moderation_queue WHERE TRUE"))
                await setup_conn.execute(text("DELETE FROM fanfics WHERE TRUE"))
                await self._setup_queue(setup_conn)

            # две параллельных сессии, каждая со своей транзакцией
            async with engine.connect() as conn_a, engine.connect() as conn_b:
                from sqlalchemy.ext.asyncio import AsyncSession

                sa = AsyncSession(bind=conn_a, expire_on_commit=False)
                sb = AsyncSession(bind=conn_b, expire_on_commit=False)
                await sa.begin()
                await sb.begin()

                repo_a = ModerationRepository(sa)
                repo_b = ModerationRepository(sb)
                now = datetime.now(tz=UTC)
                case_a = await repo_a.pick_next(moderator_id=UserId(100), now=now)
                # после того как M1 взял строку и держит её под lock,
                # M2 через SKIP LOCKED возьмёт другую
                case_b = await repo_b.pick_next(moderator_id=UserId(200), now=now)

                assert case_a is not None
                assert case_b is not None
                assert case_a.id != case_b.id

                await sa.commit()
                await sb.commit()
                await sa.close()
                await sb.close()
        finally:
            await engine.dispose()

    async def test_own_work_excluded(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(text("DELETE FROM moderation_queue WHERE TRUE"))
                await setup_conn.execute(text("DELETE FROM fanfics WHERE TRUE"))
                case_ids = await self._setup_queue(setup_conn)
                assert len(case_ids) == 2

            async with engine.connect() as conn:
                from sqlalchemy.ext.asyncio import AsyncSession

                s_ = AsyncSession(bind=conn, expire_on_commit=False)
                await s_.begin()
                repo = ModerationRepository(s_)
                # submitted_by = 1; модератор тоже 1 → не должно вернуть ничего
                case = await repo.pick_next(moderator_id=UserId(1), now=datetime.now(tz=UTC))
                assert case is None
                await s_.commit()
                await s_.close()
        finally:
            await engine.dispose()
