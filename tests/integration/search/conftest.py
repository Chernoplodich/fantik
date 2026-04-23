"""Фикстуры для интеграционных тестов поиска.

Условие запуска: переменные `POSTGRES_HOST` и `MEILI_URL` должны быть установлены.
В CI подаются через `docker-compose` (services: postgres + meilisearch).
Локально — через `make up` либо `testcontainers` (см. roadmap).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from meilisearch_python_sdk import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_MEILI_REQUIRED = "MEILI_URL"
_POSTGRES_REQUIRED = "POSTGRES_HOST"


def _skip_if_no_meili() -> None:
    if not os.environ.get(_MEILI_REQUIRED) or not os.environ.get(_POSTGRES_REQUIRED):
        pytest.skip(f"Нужны {_MEILI_REQUIRED} и {_POSTGRES_REQUIRED} — запусти `make up` или CI")


@pytest_asyncio.fixture
async def meili_client() -> AsyncIterator[AsyncClient]:
    _skip_if_no_meili()
    from app.core.config import Settings
    from app.infrastructure.search.client import INDEX_NAME, build_meili_client
    from app.infrastructure.search.settings_bootstrap import apply as apply_settings

    s = Settings()  # type: ignore[call-arg]
    client = build_meili_client(s)
    try:
        await apply_settings(client)
        # Чистим индекс между тестами
        try:
            task = await client.index(INDEX_NAME).delete_all_documents()
            await client.wait_for_task(task.task_uid)
        except Exception:  # noqa: BLE001
            pass
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    _skip_if_no_meili()
    from app.core.config import Settings

    s = Settings()  # type: ignore[call-arg]
    engine = create_async_engine(s.postgres_url)
    try:
        async with engine.begin() as conn:
            # Очистка перед тестом (порядок важен из-за FK)
            await conn.execute(text("DELETE FROM chapter_pages WHERE TRUE"))
            await conn.execute(text("DELETE FROM fanfic_tags WHERE TRUE"))
            await conn.execute(text("DELETE FROM chapters WHERE TRUE"))
            await conn.execute(text("DELETE FROM outbox WHERE TRUE"))
            await conn.execute(text("DELETE FROM moderation_queue WHERE TRUE"))
            await conn.execute(text("DELETE FROM fanfic_versions WHERE TRUE"))
            await conn.execute(text("DELETE FROM fanfics WHERE TRUE"))
            await conn.execute(text("DELETE FROM tags WHERE TRUE"))
        yield engine
    finally:
        await engine.dispose()
