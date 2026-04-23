"""Integration: IndexFanficUseCase → Meili → search(); проверяем все ключевые поля.

Требует реальный PG (для ISearchDocSource) и Meili (для ISearchIndex).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from meilisearch_python_sdk import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.application.search.dto import SearchCommand
from app.application.search.index_fanfic import IndexFanficCommand, IndexFanficUseCase
from app.infrastructure.search.client import INDEX_NAME
from app.infrastructure.search.document_builder import PgSearchDocSource
from app.infrastructure.search.indexer import MeiliSearchIndex


async def _wait_for_index(client: AsyncClient, expected_docs: int = 1) -> None:
    for _ in range(20):
        info = await client.index(INDEX_NAME).get_stats()
        if int(info.number_of_documents or 0) >= expected_docs:
            return
        await asyncio.sleep(0.2)
    raise TimeoutError(f"Meili did not index {expected_docs} docs within timeout")


async def _seed_fic(engine: AsyncEngine, *, title: str, author_nick: str) -> tuple[int, int]:
    """Создаёт fic + chapter + tag + возвращает (fic_id, fandom_id)."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, timezone, author_nick) "
                "VALUES (1001, 'UTC', :nick) ON CONFLICT (id) DO UPDATE SET author_nick = :nick"
            ),
            {"nick": author_nick},
        )
        fandom_id = (await conn.execute(text("SELECT id FROM fandoms LIMIT 1"))).scalar_one()
        age_id = (
            await conn.execute(text("SELECT id FROM age_ratings WHERE code='R' LIMIT 1"))
        ).scalar_one()
        now = datetime.now(tz=UTC)
        fic_id = (
            await conn.execute(
                text(
                    "INSERT INTO fanfics (author_id, title, summary, fandom_id, age_rating_id, "
                    "status, first_published_at, updated_at) "
                    "VALUES (1001, :title, 'АУ summary', :f, :a, 'approved', :now, :now) "
                    "RETURNING id"
                ),
                {"title": title, "f": fandom_id, "a": age_id, "now": now},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO chapters (fic_id, number, title, text, chars_count, status) "
                "VALUES (:fid, 1, 'Пролог', 'Это пролог про магов.', 21, 'approved')"
            ),
            {"fid": fic_id},
        )
        # Создадим тег с уникальным slug на базе fic_id, чтобы тесты не конфликтовали
        slug = f"au-{int(fic_id)}"
        tag_id = (
            await conn.execute(
                text(
                    "INSERT INTO tags (name, slug, kind, usage_count, approved_at) "
                    "VALUES ('АУ', :slug, 'freeform', 1, :now) "
                    "ON CONFLICT (slug) DO UPDATE SET usage_count = tags.usage_count "
                    "RETURNING id"
                ),
                {"slug": slug, "now": now},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO fanfic_tags (fic_id, tag_id) VALUES (:fid, :tid) "
                "ON CONFLICT DO NOTHING"
            ),
            {"fid": fic_id, "tid": tag_id},
        )
    return int(fic_id), int(fandom_id)


@pytest.mark.integration
class TestMeiliRoundtrip:
    async def test_index_and_search_by_multiple_fields(
        self,
        meili_client: AsyncClient,
        pg_engine: AsyncEngine,
    ) -> None:
        fic_id, fandom_id = await _seed_fic(
            pg_engine, title="Тень директора", author_nick="mark_the_writer"
        )

        async with AsyncSession(pg_engine) as session:
            source = PgSearchDocSource(session)
            index = MeiliSearchIndex(meili_client)
            uc = IndexFanficUseCase(source, index)
            await uc(IndexFanficCommand(fic_id=fic_id))

        await _wait_for_index(meili_client)

        index = MeiliSearchIndex(meili_client)

        # По title
        res = await index.search(SearchCommand(q="Тень"))
        assert any(int(h.fic_id) == fic_id for h in res.hits), "не найдено по title"

        # По author_nick (без typo-tolerance)
        res = await index.search(SearchCommand(q="mark_the_writer"))
        assert any(int(h.fic_id) == fic_id for h in res.hits), "не найдено по author_nick"

        # По filter на fandom_id
        res = await index.search(SearchCommand(fandoms=[fandom_id]))
        assert any(int(h.fic_id) == fic_id for h in res.hits), "не найдено по fandom_id"

        # По tag filter
        res = await index.search(SearchCommand(tags=["АУ"]))
        assert any(int(h.fic_id) == fic_id for h in res.hits), "не найдено по тегу"
