"""Integration: архивация фика (status=archived) убирает документ из индекса."""

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


async def _wait_stats(client: AsyncClient, expected: int) -> None:
    for _ in range(20):
        info = await client.index(INDEX_NAME).get_stats()
        if int(info.number_of_documents or 0) == expected:
            return
        await asyncio.sleep(0.2)


@pytest.mark.integration
class TestArchiveRemovesFromIndex:
    async def test_status_archived_deletes_document(
        self,
        meili_client: AsyncClient,
        pg_engine: AsyncEngine,
    ) -> None:
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, timezone, author_nick) "
                    "VALUES (2001, 'UTC', 'archivist') ON CONFLICT DO NOTHING"
                )
            )
            fandom_id = (await conn.execute(text("SELECT id FROM fandoms LIMIT 1"))).scalar_one()
            age_id = (await conn.execute(text("SELECT id FROM age_ratings LIMIT 1"))).scalar_one()
            now = datetime.now(tz=UTC)
            fic_id = (
                await conn.execute(
                    text(
                        "INSERT INTO fanfics (author_id, title, summary, fandom_id, "
                        "age_rating_id, status, first_published_at, updated_at) "
                        "VALUES (2001, 'На пенсии', 'summary', :f, :a, 'approved', :now, :now) "
                        "RETURNING id"
                    ),
                    {"f": fandom_id, "a": age_id, "now": now},
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO chapters (fic_id, number, title, text, chars_count, status) "
                    "VALUES (:fid, 1, 'Пролог', 'Текст', 5, 'approved')"
                ),
                {"fid": fic_id},
            )

        # 1. Индексируем approved-фик
        async with AsyncSession(pg_engine) as session:
            uc = IndexFanficUseCase(PgSearchDocSource(session), MeiliSearchIndex(meili_client))
            await uc(IndexFanficCommand(fic_id=int(fic_id)))

        await _wait_stats(meili_client, expected=1)

        idx = MeiliSearchIndex(meili_client)
        res = await idx.search(SearchCommand(q="пенсии"))
        assert any(int(h.fic_id) == int(fic_id) for h in res.hits)

        # 2. Меняем статус на archived + снова запускаем индексацию
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("UPDATE fanfics SET status='archived' WHERE id = :fid"),
                {"fid": fic_id},
            )

        async with AsyncSession(pg_engine) as session:
            uc = IndexFanficUseCase(PgSearchDocSource(session), MeiliSearchIndex(meili_client))
            await uc(IndexFanficCommand(fic_id=int(fic_id)))

        await _wait_stats(meili_client, expected=0)

        idx = MeiliSearchIndex(meili_client)
        res = await idx.search(SearchCommand(q="пенсии"))
        assert not any(int(h.fic_id) == int(fic_id) for h in res.hits)
