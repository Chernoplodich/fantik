"""Integration smoke test: миграция 0008 создала таблицы, 16 hash-партиций, 4 MV."""

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
class TestBroadcastMigration:
    async def test_enums_created(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.connect() as conn:
                bc_values = (
                    (
                        await conn.execute(
                            text(
                                "SELECT enumlabel FROM pg_enum e "
                                "JOIN pg_type t ON t.oid = e.enumtypid "
                                "WHERE t.typname = 'bc_status' ORDER BY e.enumsortorder"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert set(bc_values) == {
                    "draft",
                    "scheduled",
                    "running",
                    "finished",
                    "cancelled",
                    "failed",
                }

                bcd_values = (
                    (
                        await conn.execute(
                            text(
                                "SELECT enumlabel FROM pg_enum e "
                                "JOIN pg_type t ON t.oid = e.enumtypid "
                                "WHERE t.typname = 'bcd_status' ORDER BY e.enumsortorder"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert set(bcd_values) == {"pending", "sent", "failed", "blocked"}
        finally:
            await engine.dispose()

    async def test_broadcast_deliveries_has_16_partitions(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.connect() as conn:
                count = (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM pg_inherits i "
                            "JOIN pg_class c ON c.oid = i.inhparent "
                            "WHERE c.relname = 'broadcast_deliveries'"
                        )
                    )
                ).scalar_one()
                assert int(count) == 16
        finally:
            await engine.dispose()

    async def test_all_materialized_views_exist(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.connect() as conn:
                views = (
                    (
                        await conn.execute(
                            text(
                                "SELECT matviewname FROM pg_matviews "
                                "WHERE matviewname LIKE 'mv_%' ORDER BY matviewname"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert set(views) >= {
                    "mv_daily_activity",
                    "mv_top_fandoms_7d",
                    "mv_author_stats",
                    "mv_moderator_load",
                }
        finally:
            await engine.dispose()

    async def test_broadcast_insert_and_delivery_upsert(self) -> None:
        from datetime import UTC, datetime

        from sqlalchemy.ext.asyncio import AsyncSession

        from app.core.config import Settings
        from app.domain.broadcasts.entities import Broadcast
        from app.domain.broadcasts.value_objects import BroadcastStatus
        from app.domain.shared.types import BroadcastId, UserId
        from app.infrastructure.db.repositories.broadcasts import (
            BroadcastRepository,
            DeliveryRepository,
        )

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(text("DELETE FROM broadcast_deliveries WHERE TRUE"))
                await setup_conn.execute(text("DELETE FROM broadcasts WHERE TRUE"))
                await setup_conn.execute(
                    text(
                        "INSERT INTO users (id, timezone, role) "
                        "VALUES (5001, 'UTC', 'admin') ON CONFLICT (id) DO NOTHING"
                    )
                )
                await setup_conn.execute(
                    text(
                        "INSERT INTO users (id, timezone) "
                        "VALUES (5002, 'UTC'), (5003, 'UTC') ON CONFLICT (id) DO NOTHING"
                    )
                )

            async with engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                await session.begin()

                bc_repo = BroadcastRepository(session)
                delivery_repo = DeliveryRepository(session)
                now = datetime.now(tz=UTC)
                draft = Broadcast.new_draft(
                    broadcast_id=BroadcastId(0),
                    created_by=UserId(5001),
                    source_chat_id=123,
                    source_message_id=45,
                    now=now,
                )
                draft.set_segment({"kind": "all"})
                new_id = await bc_repo.create(draft)
                assert int(new_id) > 0

                # 1) первая вставка даёт 2 строки
                inserted1 = await delivery_repo.upsert_pending(
                    broadcast_id=new_id, user_ids=[UserId(5002), UserId(5003)]
                )
                assert inserted1 == 2
                # 2) повторная — 0 (ON CONFLICT DO NOTHING)
                inserted2 = await delivery_repo.upsert_pending(
                    broadcast_id=new_id, user_ids=[UserId(5002), UserId(5003)]
                )
                assert inserted2 == 0

                counts = await delivery_repo.count_by_status(new_id)
                from app.domain.broadcasts.value_objects import DeliveryStatus

                assert counts[DeliveryStatus.PENDING] == 2
                assert counts[DeliveryStatus.SENT] == 0

                # scheduler scan — draft не берёт.
                picked_empty = await bc_repo.scan_ready_to_run(now=now, limit=10)
                assert picked_empty == []

                # Запланировать в прошлом и scan — забирает.
                from datetime import timedelta

                bc = await bc_repo.get(new_id)
                assert bc is not None
                bc.schedule(scheduled_at=now - timedelta(seconds=10))
                await bc_repo.save(bc)
                picked = await bc_repo.scan_ready_to_run(now=now, limit=10)
                assert int(picked[0]) == int(new_id)
                # После scan — статус running.
                bc2 = await bc_repo.get(new_id)
                assert bc2 is not None
                assert bc2.status == BroadcastStatus.RUNNING

                await session.commit()
                await session.close()
        finally:
            await engine.dispose()
