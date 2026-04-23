"""Integration: `facetDistribution` возвращается для запрошенных фасетов."""

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


async def _wait_count(client: AsyncClient, expected: int) -> None:
    for _ in range(25):
        info = await client.index(INDEX_NAME).get_stats()
        if int(info.number_of_documents or 0) >= expected:
            return
        await asyncio.sleep(0.2)


@pytest.mark.integration
class TestFacets:
    async def test_facet_distribution_returned(
        self,
        meili_client: AsyncClient,
        pg_engine: AsyncEngine,
    ) -> None:
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, timezone, author_nick) "
                    "VALUES (3001, 'UTC', 'facet_author') ON CONFLICT DO NOTHING"
                )
            )
            fandom_id = (await conn.execute(text("SELECT id FROM fandoms LIMIT 1"))).scalar_one()
            age_rows = (
                await conn.execute(
                    text("SELECT id, code FROM age_ratings ORDER BY sort_order LIMIT 2")
                )
            ).all()
            assert len(age_rows) >= 2

            now = datetime.now(tz=UTC)
            for i, age_row in enumerate(age_rows):
                for j in range(2):
                    await conn.execute(
                        text(
                            "INSERT INTO fanfics (author_id, title, summary, fandom_id, "
                            "age_rating_id, status, first_published_at, updated_at) "
                            "VALUES (3001, :title, 'summary', :f, :a, 'approved', :now, :now)"
                        ),
                        {
                            "title": f"Работа {age_row.code} №{j}",
                            "f": fandom_id,
                            "a": age_row.id,
                            "now": now,
                        },
                    )
            fic_ids = list(
                (await conn.execute(text("SELECT id FROM fanfics ORDER BY id"))).scalars().all()
            )

        async with AsyncSession(pg_engine) as session:
            uc = IndexFanficUseCase(PgSearchDocSource(session), MeiliSearchIndex(meili_client))
            for fid in fic_ids:
                await uc(IndexFanficCommand(fic_id=int(fid)))

        await _wait_count(meili_client, expected=len(fic_ids))

        idx = MeiliSearchIndex(meili_client)
        res = await idx.search(SearchCommand(q=""))
        # Фасеты должны содержать распределение по age_rating (2 значения × 2 фика)
        assert "age_rating" in res.facets
        for _code, cnt in res.facets["age_rating"].items():
            assert cnt >= 1
        # И сумма по фасету = количество документов
        assert sum(res.facets["age_rating"].values()) == len(fic_ids)
