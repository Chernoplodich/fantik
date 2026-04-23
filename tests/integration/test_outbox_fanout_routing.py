"""Integration test: outbox-диспетчер маршрутизирует notify_* в зависимости от kind."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="Нет реального PG — запусти make up или CI",
)
class TestOutboxFanout:
    async def test_chapter_add_triggers_notify_new_chapter(self) -> None:
        from app.core.config import Settings
        from app.infrastructure.tasks import outbox_dispatcher as od

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(text("DELETE FROM outbox WHERE TRUE"))
                await setup_conn.execute(
                    text(
                        "INSERT INTO outbox (event_type, payload, created_at) "
                        "VALUES (:t, CAST(:p AS jsonb), now())"
                    ),
                    {
                        "t": "fanfic.approved",
                        "p": (
                            '{"fic_id": 10, "author_id": 42, "case_id": 1, '
                            '"first_publish": false, "version_id": 0, '
                            '"chapter_ids": [100], "kind": "chapter_add", '
                            '"new_chapter_ids": [100]}'
                        ),
                    },
                )

            # Мокаем enqueue-helpers, чтобы они не требовали живой Redis/TaskIQ.
            calls: dict[str, list[Any]] = {
                "idx": [],
                "repag": [],
                "new_chapter": [],
                "new_work": [],
                "notif_mod": [],
            }

            async def fake_idx(fic_id: int) -> None:
                calls["idx"].append(fic_id)

            async def fake_repag(chapter_id: int) -> None:
                calls["repag"].append(chapter_id)

            async def fake_new_chapter(author_id: int, fic_id: int, chapter_id: int) -> None:
                calls["new_chapter"].append((author_id, fic_id, chapter_id))

            async def fake_new_work(author_id: int, fic_id: int) -> None:
                calls["new_work"].append((author_id, fic_id))

            async def fake_notif_mod(user_id: int, report_id: int) -> None:
                calls["notif_mod"].append((user_id, report_id))

            with (
                patch.object(od, "_enqueue_index", fake_idx),
                patch.object(od, "_enqueue_repaginate", fake_repag),
                patch.object(od, "_enqueue_notify_new_chapter", fake_new_chapter),
                patch.object(od, "_enqueue_notify_new_work", fake_new_work),
                patch.object(od, "_enqueue_notify_moderation_decision", fake_notif_mod),
            ):
                async with engine.connect() as conn:
                    session = AsyncSession(bind=conn, expire_on_commit=False)
                    async with session.begin():
                        processed = await od._process_batch(session)
                    await session.close()

            assert processed == 1
            assert calls["idx"] == [10]
            assert calls["repag"] == [100]
            assert calls["new_chapter"] == [(42, 10, 100)]
            assert calls["new_work"] == []

            async with engine.connect() as check_conn:
                published = (
                    await check_conn.execute(
                        text(
                            "SELECT count(*) FROM outbox "
                            "WHERE event_type='fanfic.approved' AND published_at IS NOT NULL"
                        )
                    )
                ).scalar_one()
            assert int(published) == 1
        finally:
            await engine.dispose()

    async def test_fic_edit_does_not_trigger_fanout(self) -> None:
        from app.core.config import Settings
        from app.infrastructure.tasks import outbox_dispatcher as od

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(text("DELETE FROM outbox WHERE TRUE"))
                await setup_conn.execute(
                    text(
                        "INSERT INTO outbox (event_type, payload, created_at) "
                        "VALUES (:t, CAST(:p AS jsonb), now())"
                    ),
                    {
                        "t": "fanfic.approved",
                        "p": (
                            '{"fic_id": 11, "author_id": 43, "case_id": 2, '
                            '"first_publish": false, "version_id": 0, '
                            '"chapter_ids": [200], "kind": "fic_edit"}'
                        ),
                    },
                )

            calls: list[Any] = []

            async def fake_new_chapter(*args: Any) -> None:
                calls.append(("new_chapter", *args))

            async def fake_new_work(*args: Any) -> None:
                calls.append(("new_work", *args))

            async def noop(*_: Any) -> None:
                pass

            with (
                patch.object(od, "_enqueue_index", noop),
                patch.object(od, "_enqueue_repaginate", noop),
                patch.object(od, "_enqueue_notify_new_chapter", fake_new_chapter),
                patch.object(od, "_enqueue_notify_new_work", fake_new_work),
                patch.object(od, "_enqueue_notify_moderation_decision", noop),
            ):
                async with engine.connect() as conn:
                    session = AsyncSession(bind=conn, expire_on_commit=False)
                    async with session.begin():
                        await od._process_batch(session)
                    await session.close()

            assert calls == []
        finally:
            await engine.dispose()
