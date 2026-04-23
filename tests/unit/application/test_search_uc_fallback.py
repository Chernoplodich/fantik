"""Unit: SearchUseCase fallback при circuit-open и при исключении primary."""

from __future__ import annotations

import pytest

from app.application.search.dto import (
    SearchCommand,
    SearchHit,
    SearchResult,
)
from app.application.search.ports import ISearchFallback, ISearchIndex
from app.application.search.search import SearchUseCase
from app.domain.shared.types import FandomId, FanficId


class _FakePrimary(ISearchIndex):
    def __init__(self, *, open_: bool = False, raise_: bool = False) -> None:
        self._open = open_
        self._raise = raise_
        self.search_calls = 0

    def is_open(self) -> bool:
        return self._open

    async def search(self, cmd: SearchCommand) -> SearchResult:
        self.search_calls += 1
        if self._raise:
            raise RuntimeError("meili down")
        return SearchResult(
            hits=[_make_hit(1, "primary hit")],
            total=1,
            facets={"fandom_name": {"HP": 1}},
            degraded=False,
        )

    async def upsert(self, doc: dict[str, object]) -> None: ...

    async def delete(self, fic_id: int) -> None: ...

    async def bulk_upsert(self, docs: list[dict[str, object]]) -> None: ...


class _FakeFallback(ISearchFallback):
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, q: str, *, limit: int, offset: int) -> list[SearchHit]:
        self.calls += 1
        return [_make_hit(42, "fallback hit")]


def _make_hit(fid: int, title: str) -> SearchHit:
    return SearchHit(
        fic_id=FanficId(fid),
        title=title,
        author_nick=None,
        fandom_id=FandomId(0),
        fandom_name=None,
        age_rating="",
        likes_count=0,
        chapters_count=0,
    )


@pytest.mark.asyncio
class TestSearchUseCaseFallback:
    async def test_primary_ok_returns_primary(self) -> None:
        primary = _FakePrimary()
        fb = _FakeFallback()
        uc = SearchUseCase(primary, fb)
        res = await uc(SearchCommand(q="x"))
        assert res.degraded is False
        assert primary.search_calls == 1
        assert fb.calls == 0
        assert res.hits[0].title == "primary hit"

    async def test_circuit_open_skips_primary(self) -> None:
        primary = _FakePrimary(open_=True)
        fb = _FakeFallback()
        uc = SearchUseCase(primary, fb)
        res = await uc(SearchCommand(q="x"))
        assert res.degraded is True
        assert primary.search_calls == 0
        assert fb.calls == 1
        assert res.hits[0].title == "fallback hit"

    async def test_primary_raises_goes_to_fallback(self) -> None:
        primary = _FakePrimary(raise_=True)
        fb = _FakeFallback()
        uc = SearchUseCase(primary, fb)
        res = await uc(SearchCommand(q="x"))
        assert res.degraded is True
        assert primary.search_calls == 1
        assert fb.calls == 1
