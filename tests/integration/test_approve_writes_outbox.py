"""Integration test: approve пишет fanfic.approved в outbox (idempotent decision)."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.domain.fanfics.value_objects import MqDecision
from app.domain.shared.types import ModerationCaseId, UserId
from app.infrastructure.db.repositories.moderation import ModerationRepository
from app.infrastructure.db.repositories.outbox import OutboxRepository


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="Нет реального PG — запусти make up или CI",
)
class TestApproveOutbox:
    async def test_save_decision_idempotent_and_outbox(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(text("DELETE FROM outbox WHERE TRUE"))
                await setup_conn.execute(text("DELETE FROM moderation_queue WHERE TRUE"))
                await setup_conn.execute(text("DELETE FROM fanfics WHERE TRUE"))
                await setup_conn.execute(
                    text("INSERT INTO users (id, timezone) VALUES (1, 'UTC') ON CONFLICT DO NOTHING")
                )
                fandom_id = (
                    await setup_conn.execute(text("SELECT id FROM fandoms LIMIT 1"))
                ).scalar_one()
                age_id = (
                    await setup_conn.execute(text("SELECT id FROM age_ratings LIMIT 1"))
                ).scalar_one()
                fic_id = (
                    await setup_conn.execute(
                        text(
                            "INSERT INTO fanfics (author_id, title, summary, fandom_id, age_rating_id, status) "
                            "VALUES (1, 'T', 'S', :f, :a, 'pending') RETURNING id"
                        ),
                        {"f": fandom_id, "a": age_id},
                    )
                ).scalar_one()
                case_id = (
                    await setup_conn.execute(
                        text(
                            "INSERT INTO moderation_queue (fic_id, kind, submitted_by) "
                            "VALUES (:fid, 'fic_first_publish', 1) RETURNING id"
                        ),
                        {"fid": fic_id},
                    )
                ).scalar_one()

            async with engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                await session.begin()
                repo = ModerationRepository(session)
                outbox = OutboxRepository(session)
                now = datetime.now(tz=UTC)

                # берём в работу через pick_next
                case = await repo.pick_next(moderator_id=UserId(99), now=now)
                assert case is not None
                assert case.id == ModerationCaseId(case_id)

                # применяем решение
                case.approve(moderator_id=UserId(99), comment=None, entities=[], now=now)
                ok = await repo.save_decision_idempotent(case)
                assert ok
                await outbox.append(
                    event_type="fanfic.approved",
                    payload={"fic_id": int(fic_id), "case_id": int(case_id)},
                    now=now,
                )
                await session.commit()
                await session.close()

            async with engine.connect() as check_conn:
                cnt = (
                    await check_conn.execute(
                        text(
                            "SELECT count(*) FROM outbox WHERE event_type='fanfic.approved'"
                        )
                    )
                ).scalar_one()
                assert cnt == 1
                dec = (
                    await check_conn.execute(
                        text("SELECT decision FROM moderation_queue WHERE id = :id"),
                        {"id": case_id},
                    )
                ).scalar_one()
                assert dec == MqDecision.APPROVED.value
        finally:
            await engine.dispose()
