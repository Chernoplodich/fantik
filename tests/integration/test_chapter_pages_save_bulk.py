"""Integration: chapter_pages.save_bulk идемпотентна (ON CONFLICT DO NOTHING)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.domain.fanfics.services.paginator import Page
from app.domain.shared.types import ChapterId
from app.infrastructure.db.repositories.chapter_pages import (
    ChapterPagesRepository,
)


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="Нет реального PG — запусти make up или CI",
)
class TestChapterPagesBulk:
    async def test_save_bulk_idempotent(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(text("DELETE FROM chapter_pages WHERE TRUE"))
                await setup_conn.execute(text("DELETE FROM chapters WHERE TRUE"))
                await setup_conn.execute(text("DELETE FROM fanfics WHERE TRUE"))
                await setup_conn.execute(
                    text(
                        "INSERT INTO users (id, timezone) VALUES (1, 'UTC') ON CONFLICT DO NOTHING"
                    )
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
                            "INSERT INTO fanfics "
                            "(author_id, title, summary, fandom_id, age_rating_id, status) "
                            "VALUES (1, 'T', 'S', :f, :a, 'approved') RETURNING id"
                        ),
                        {"f": fandom_id, "a": age_id},
                    )
                ).scalar_one()
                chapter_id = (
                    await setup_conn.execute(
                        text(
                            "INSERT INTO chapters (fic_id, number, title, text, status) "
                            "VALUES (:f, 1, 'Ch1', 'text', 'approved') RETURNING id"
                        ),
                        {"f": fic_id},
                    )
                ).scalar_one()

            pages = [
                Page(page_no=1, text="p1", entities=[], chars_count=2),
                Page(page_no=2, text="p2", entities=[], chars_count=2),
            ]

            async with engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                await session.begin()
                repo = ChapterPagesRepository(session)
                await repo.save_bulk(ChapterId(chapter_id), pages)
                # Повтор с тем же набором — не должно дать дубли.
                await repo.save_bulk(ChapterId(chapter_id), pages)
                await session.commit()

            async with engine.connect() as check_conn:
                count = (
                    await check_conn.execute(
                        text("SELECT count(*) FROM chapter_pages WHERE chapter_id = :c"),
                        {"c": int(chapter_id)},
                    )
                ).scalar_one()
                assert int(count) == 2

            # Delete + save снова — 2 страницы, не 4.
            async with engine.connect() as conn2:
                session = AsyncSession(bind=conn2, expire_on_commit=False)
                await session.begin()
                repo = ChapterPagesRepository(session)
                await repo.delete_by_chapter(ChapterId(chapter_id))
                await repo.save_bulk(ChapterId(chapter_id), pages)
                await session.commit()

            async with engine.connect() as check_conn2:
                count = (
                    await check_conn2.execute(
                        text("SELECT count(*) FROM chapter_pages WHERE chapter_id = :c"),
                        {"c": int(chapter_id)},
                    )
                ).scalar_one()
                assert int(count) == 2
        finally:
            await engine.dispose()
