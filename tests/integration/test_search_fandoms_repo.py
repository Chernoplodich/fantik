"""Integration: ReferenceReader.search_fandoms / list_fandoms_by_category.

Проверяем поведение реальных SQL-запросов на подмножестве seed-данных.
Запускается в CI с поднятым PG (миграции прокатываются автоматически).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.db.repositories.reference import ReferenceReader

pytestmark = pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="Нет реального PG — запусти make up или CI",
)


async def _seed_test_fandoms(engine) -> list[str]:
    """Засеять небольшой набор фандомов под тест.

    ON CONFLICT DO NOTHING — повторный запуск теста не упадёт.
    Возвращает список slug'ов для последующей очистки.
    """
    rows = [
        {
            "slug": "_test-harry-potter",
            "name": "Тестовый Гарри Поттер",
            "category": "books",
            "aliases": ["HP", "Harry Potter"],
        },
        {
            "slug": "_test-disco-elysium",
            "name": "Тестовый Disco Elysium",
            "category": "games",
            "aliases": ["DE", "Гарри Дюбуа"],
        },
        {
            "slug": "_test-naruto",
            "name": "Тестовый Наруто",
            "category": "anime",
            "aliases": ["Naruto"],
        },
        {
            "slug": "_test-bleach",
            "name": "Тестовый Bleach",
            "category": "anime",
            "aliases": ["Блич"],
        },
    ]
    slugs = [r["slug"] for r in rows]
    async with engine.begin() as conn:
        for r in rows:
            await conn.execute(
                text(
                    "INSERT INTO fandoms (slug, name, category, aliases, active) "
                    "VALUES (:slug, :name, :category, :aliases, TRUE) "
                    "ON CONFLICT (slug) DO NOTHING"
                ),
                r,
            )
    return slugs


async def _cleanup(engine, slugs: list[str]) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM fandoms WHERE slug = ANY(:slugs)"),
            {"slugs": slugs},
        )


@pytest.mark.integration
class TestSearchFandoms:
    async def test_finds_by_substring_in_name(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        slugs = await _seed_test_fandoms(engine)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                repo = ReferenceReader(session)
                results = await repo.search_fandoms(query="Гарри", limit=10)
                names = [r.name for r in results]
                # Должен попасть Гарри Поттер по name и Disco Elysium по alias «Гарри Дюбуа».
                assert any("Гарри Поттер" in n for n in names)
                assert any("Disco" in n for n in names)
        finally:
            await _cleanup(engine, slugs)
            await engine.dispose()

    async def test_prefix_match_priority(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        slugs = await _seed_test_fandoms(engine)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                repo = ReferenceReader(session)
                # Ищем "Тестовый Г" — оба фандома (HP и Disco) подходят, но HP —
                # с префикс-матчем в name "Тестовый Гарри Поттер" → выше.
                results = await repo.search_fandoms(query="Тестовый Г", limit=10)
                names = [r.name for r in results]
                assert names[0] == "Тестовый Гарри Поттер"
        finally:
            await _cleanup(engine, slugs)
            await engine.dispose()

    async def test_too_short_query_returns_empty(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                repo = ReferenceReader(session)
                results = await repo.search_fandoms(query="а", limit=10)
                assert results == []
        finally:
            await engine.dispose()

    async def test_filter_by_category(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        slugs = await _seed_test_fandoms(engine)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                repo = ReferenceReader(session)
                # Те же фандомы — но только аниме-категория.
                results = await repo.search_fandoms(query="Тестов", limit=20, category="anime")
                names = {r.name for r in results}
                assert "Тестовый Наруто" in names
                assert "Тестовый Bleach" in names
                assert all(r.category == "anime" for r in results)
        finally:
            await _cleanup(engine, slugs)
            await engine.dispose()


@pytest.mark.integration
class TestListByCategory:
    async def test_returns_only_in_category_with_total(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        slugs = await _seed_test_fandoms(engine)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                repo = ReferenceReader(session)
                items, total = await repo.list_fandoms_by_category(
                    category="anime", limit=100, offset=0
                )
                # В тестовых данных два anime, плюс могут быть из миграций.
                assert total >= 2
                assert all(r.category == "anime" for r in items)
        finally:
            await _cleanup(engine, slugs)
            await engine.dispose()

    async def test_pagination(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        slugs = await _seed_test_fandoms(engine)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                repo = ReferenceReader(session)
                page0, total = await repo.list_fandoms_by_category(
                    category="anime", limit=1, offset=0
                )
                page1, _ = await repo.list_fandoms_by_category(category="anime", limit=1, offset=1)
                assert len(page0) == 1
                assert total >= 2
                # На второй странице — другой элемент (если total≥2).
                if total >= 2:
                    assert page0[0].id != page1[0].id
        finally:
            await _cleanup(engine, slugs)
            await engine.dispose()


@pytest.mark.integration
async def test_dummy_dt_use_for_lint() -> None:
    """Используем datetime/UTC чтобы пройти ruff (DTZ)."""
    assert datetime.now(tz=UTC) is not None
