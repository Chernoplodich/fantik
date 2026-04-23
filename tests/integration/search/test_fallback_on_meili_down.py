"""Integration: при недоступном Meili circuit-breaker открывается,
SearchUseCase уходит в PG FTS-fallback, возвращает hits + degraded=True.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from meilisearch_python_sdk import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.application.search.dto import SearchCommand
from app.application.search.search import SearchUseCase
from app.infrastructure.search.fallback_pg import PgFtsSearch
from app.infrastructure.search.indexer import MeiliSearchIndex


@pytest.mark.integration
class TestFallback:
    async def test_primary_down_falls_back_to_pg_fts(
        self,
        pg_engine: AsyncEngine,
    ) -> None:
        # 1. Засеять approved-фик, который найдётся по PG FTS
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, timezone, author_nick) "
                    "VALUES (4001, 'UTC', 'fallback_author') ON CONFLICT DO NOTHING"
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
                        "VALUES (4001, 'Волшебник', 'ищет своё место', :f, :a, 'approved', :now, :now) "
                        "RETURNING id"
                    ),
                    {"f": fandom_id, "a": age_id, "now": now},
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO chapters (fic_id, number, title, text, chars_count, status) "
                    "VALUES (:fid, 1, 'Начало', 'Волшебник шёл по дороге', 10, 'approved')"
                ),
                {"fid": fic_id},
            )

        # 2. Поднять Primary с unreachable URL → circuit откроется после 3 fails.
        dead_client = AsyncClient(url="http://127.0.0.1:1", api_key="x")
        try:
            primary = MeiliSearchIndex(dead_client)

            # 3 отказа → открыть контур
            for _ in range(3):
                with pytest.raises(Exception):  # noqa: BLE001, PT011
                    await primary.search(SearchCommand(q="test"))
            assert primary.is_open() is True

            async with AsyncSession(pg_engine) as session:
                fallback = PgFtsSearch(session)
                uc = SearchUseCase(primary, fallback)
                res = await uc(SearchCommand(q="волшебник"))

            assert res.degraded is True
            assert any(int(h.fic_id) == int(fic_id) for h in res.hits)
        finally:
            await dead_client.aclose()
