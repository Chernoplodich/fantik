"""Integration smoke test: миграция 0006 создала таблицы и индексы, ON CONFLICT работает."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.domain.reports.value_objects import ReportTarget
from app.domain.shared.types import UserId
from app.infrastructure.db.repositories.notifications import NotificationRepository
from app.infrastructure.db.repositories.reports import ReportRepository
from app.infrastructure.db.repositories.subscriptions import SubscriptionRepository


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="Нет реального PG — запусти make up или CI",
)
class TestSocialSchema:
    async def test_subscription_is_idempotent_via_on_conflict(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(text("DELETE FROM subscriptions WHERE TRUE"))
                await setup_conn.execute(
                    text(
                        "INSERT INTO users (id, timezone) VALUES (1001, 'UTC') "
                        "ON CONFLICT DO NOTHING"
                    )
                )
                await setup_conn.execute(
                    text(
                        "INSERT INTO users (id, timezone) VALUES (1002, 'UTC') "
                        "ON CONFLICT DO NOTHING"
                    )
                )
            async with engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                await session.begin()
                repo = SubscriptionRepository(session)
                now = datetime.now(tz=UTC)
                inserted1 = await repo.add_if_absent(
                    subscriber_id=UserId(1001), author_id=UserId(1002), now=now
                )
                inserted2 = await repo.add_if_absent(
                    subscriber_id=UserId(1001), author_id=UserId(1002), now=now
                )
                assert inserted1 is True
                assert inserted2 is False
                assert await repo.exists(subscriber_id=UserId(1001), author_id=UserId(1002))
                await session.commit()
                await session.close()
        finally:
            await engine.dispose()

    async def test_reports_anti_dup_same_reporter_target(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(text("DELETE FROM reports WHERE TRUE"))
                await setup_conn.execute(
                    text(
                        "INSERT INTO users (id, timezone) VALUES (2001, 'UTC') "
                        "ON CONFLICT DO NOTHING"
                    )
                )
            async with engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                await session.begin()
                repo = ReportRepository(session)
                now = datetime.now(tz=UTC)

                r1 = await repo.create(
                    reporter_id=UserId(2001),
                    target_type=ReportTarget.FANFIC,
                    target_id=777,
                    reason_code="SPAM",
                    text="bad",
                    text_entities=[],
                    notify_reporter=True,
                    now=now,
                )
                existing = await repo.exists_open_from_reporter(
                    reporter_id=UserId(2001),
                    target_type=ReportTarget.FANFIC,
                    target_id=777,
                )
                assert existing == r1.id

                await session.commit()
                await session.close()
        finally:
            await engine.dispose()

    async def test_notification_create_and_mark_sent(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(text("DELETE FROM notifications WHERE TRUE"))
                await setup_conn.execute(
                    text(
                        "INSERT INTO users (id, timezone) VALUES (3001, 'UTC') "
                        "ON CONFLICT DO NOTHING"
                    )
                )
            async with engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                await session.begin()
                repo = NotificationRepository(session)
                now = datetime.now(tz=UTC)
                nid = await repo.create(
                    user_id=UserId(3001),
                    kind="new_work_from_author",
                    payload={"fic_id": 123, "fic_title": "X"},
                    now=now,
                )
                await repo.mark_sent(notification_id=nid, now=now)
                sent_at = (
                    await conn.execute(
                        text("SELECT sent_at FROM notifications WHERE id = :id"),
                        {"id": int(nid)},
                    )
                ).scalar_one()
                assert sent_at is not None
                await session.commit()
                await session.close()
        finally:
            await engine.dispose()
