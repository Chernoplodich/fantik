"""Unit: IndexFanficUseCase — ветвления upsert/delete по статусу."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.search.index_fanfic import IndexFanficCommand, IndexFanficUseCase
from app.application.search.ports import ISearchDocSource, ISearchIndex, SearchDocSource
from app.domain.shared.types import FanficId


class _FakeSource(ISearchDocSource):
    def __init__(self, doc: SearchDocSource | None) -> None:
        self._doc = doc

    async def load(self, fic_id: FanficId | int) -> SearchDocSource | None:
        return self._doc


class _FakeIndex(ISearchIndex):
    def __init__(self) -> None:
        self.upserted: list[dict[str, object]] = []
        self.deleted: list[int] = []

    def is_open(self) -> bool:
        return False

    async def search(self, cmd):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def upsert(self, doc: dict[str, object]) -> None:
        self.upserted.append(doc)

    async def delete(self, fic_id: int) -> None:
        self.deleted.append(int(fic_id))

    async def bulk_upsert(self, docs: list[dict[str, object]]) -> None:
        self.upserted.extend(docs)


def _make_doc(fic_id: int = 1) -> SearchDocSource:
    return SearchDocSource(
        fic_id=fic_id,
        title="Тень директора",
        summary="АУ",
        author_nick="mark",
        fandom_id=1,
        fandom_name="Гарри Поттер",
        fandom_aliases=["HP"],
        age_rating="R",
        age_rating_order=4,
        tags=["AU"],
        characters=["Снейп"],
        warnings=[],
        chapters_count=2,
        chars_count=5000,
        likes_count=10,
        views_count=100,
        reads_completed_count=3,
        first_published_at=datetime(2026, 4, 1, tzinfo=UTC),
        updated_at=datetime(2026, 4, 20, tzinfo=UTC),
        chapter_texts=["Пролог" * 100, "Глава 1" * 100],
    )


@pytest.mark.asyncio
class TestIndexFanficUseCase:
    async def test_approved_fic_is_upserted(self) -> None:
        idx = _FakeIndex()
        uc = IndexFanficUseCase(_FakeSource(_make_doc(1)), idx)
        await uc(IndexFanficCommand(fic_id=1))
        assert len(idx.upserted) == 1
        assert len(idx.deleted) == 0
        doc = idx.upserted[0]
        assert doc["id"] == 1
        assert doc["title"] == "Тень директора"
        assert doc["tags"] == ["AU"]
        assert doc["characters"] == ["Снейп"]
        # excerpt должен содержать данные из chapter_texts, обрезанных до 5k каждый
        assert isinstance(doc["chapters_text_excerpt"], str)
        assert len(str(doc["chapters_text_excerpt"])) <= 20_000

    async def test_missing_or_non_approved_fic_is_deleted(self) -> None:
        idx = _FakeIndex()
        uc = IndexFanficUseCase(_FakeSource(None), idx)
        await uc(IndexFanficCommand(fic_id=7))
        assert idx.deleted == [7]
        assert idx.upserted == []

    async def test_excerpt_budget_respected(self) -> None:
        idx = _FakeIndex()
        # 4 главы × 6000 символов каждая — лимит на главу 5000, суммарный 20000
        doc = _make_doc(2)
        doc = SearchDocSource(**{**doc.__dict__, "chapter_texts": ["x" * 6000] * 4})
        uc = IndexFanficUseCase(_FakeSource(doc), idx)
        await uc(IndexFanficCommand(fic_id=2))
        assert len(idx.upserted) == 1
        excerpt = str(idx.upserted[0]["chapters_text_excerpt"])
        assert len(excerpt) <= 20_000
