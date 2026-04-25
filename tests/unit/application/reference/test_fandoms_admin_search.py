"""Use cases админ-фандомов: list_by_category, search, category_stats."""

from __future__ import annotations

from typing import Any

import pytest

from app.application.reference.fandoms_crud import (
    CategoryStatsAdminUseCase,
    ListFandomsByCategoryAdminUseCase,
    SearchFandomsAdminUseCase,
)
from app.application.reference.ports import FandomAdminRow, IFandomAdminRepository
from app.domain.shared.types import FandomId


class FakeRepo(IFandomAdminRepository):
    """Минимальный fake для read-only сценариев."""

    def __init__(self, rows: list[FandomAdminRow]) -> None:
        self._rows = list(rows)

    async def list_all(self, *, active_only: bool = False) -> list[FandomAdminRow]:
        return [r for r in self._rows if (not active_only or r.active)]

    async def get(self, fandom_id: FandomId) -> FandomAdminRow | None:
        return next((r for r in self._rows if int(r.id) == int(fandom_id)), None)

    async def create(self, **kwargs: Any) -> FandomAdminRow:
        raise NotImplementedError

    async def update(self, **kwargs: Any) -> FandomAdminRow:
        raise NotImplementedError

    async def list_by_category(
        self, *, category: str, limit: int, offset: int
    ) -> tuple[list[FandomAdminRow], int]:
        filtered = sorted(
            (r for r in self._rows if r.category == category),
            key=lambda r: r.name,
        )
        return filtered[offset : offset + limit], len(filtered)

    async def search(
        self,
        *,
        query: str,
        limit: int = 30,
        category: str | None = None,
    ) -> list[FandomAdminRow]:
        q = query.lower()

        def matches(r: FandomAdminRow) -> bool:
            if category is not None and r.category != category:
                return False
            return q in r.name.lower() or any(q in a.lower() for a in r.aliases)

        # Имитируем prefix-priority как в SQL.
        filtered = [r for r in self._rows if matches(r)]
        filtered.sort(key=lambda r: (0 if r.name.lower().startswith(q) else 1, r.name.lower()))
        return filtered[:limit]

    async def count_by_category(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self._rows:
            if r.active:
                out[r.category] = out.get(r.category, 0) + 1
        return out


def _row(
    fid: int,
    name: str,
    category: str,
    *,
    active: bool = True,
    aliases: list[str] | None = None,
) -> FandomAdminRow:
    return FandomAdminRow(
        id=FandomId(fid),
        slug=f"f-{fid}",
        name=name,
        category=category,
        aliases=list(aliases or []),
        active=active,
    )


# ============================================================
# ListFandomsByCategoryAdminUseCase
# ============================================================


class TestListByCategory:
    @pytest.mark.asyncio
    async def test_returns_only_target_category_with_total(self) -> None:
        rows = [
            _row(1, "AAA", "anime"),
            _row(2, "BBB", "books"),
            _row(3, "CCC", "anime"),
        ]
        uc = ListFandomsByCategoryAdminUseCase(FakeRepo(rows))
        page, total = await uc(category="anime", limit=10, offset=0)
        assert total == 2
        names = [r.name for r in page]
        assert names == ["AAA", "CCC"]

    @pytest.mark.asyncio
    async def test_includes_inactive_for_admin(self) -> None:
        """Регрессия: админу должны быть видны и неактивные (в отличие от ReferenceReader)."""
        rows = [_row(1, "Active", "anime"), _row(2, "Disabled", "anime", active=False)]
        uc = ListFandomsByCategoryAdminUseCase(FakeRepo(rows))
        page, total = await uc(category="anime", limit=10, offset=0)
        assert total == 2
        assert {r.name for r in page} == {"Active", "Disabled"}

    @pytest.mark.asyncio
    async def test_pagination_offset(self) -> None:
        rows = [_row(i, f"F{i:02d}", "anime") for i in range(1, 26)]
        uc = ListFandomsByCategoryAdminUseCase(FakeRepo(rows))
        page2, total = await uc(category="anime", limit=10, offset=10)
        assert total == 25
        assert len(page2) == 10
        assert page2[0].name == "F11"


# ============================================================
# SearchFandomsAdminUseCase
# ============================================================


class TestSearch:
    @pytest.mark.asyncio
    async def test_finds_by_substring_in_name(self) -> None:
        rows = [
            _row(1, "Гарри Поттер", "books"),
            _row(2, "Властелин Колец", "books"),
        ]
        uc = SearchFandomsAdminUseCase(FakeRepo(rows))
        results = await uc(query="Гарри")
        assert [r.name for r in results] == ["Гарри Поттер"]

    @pytest.mark.asyncio
    async def test_finds_by_alias(self) -> None:
        rows = [_row(1, "Harry Potter", "books", aliases=["HP", "ГП"])]
        uc = SearchFandomsAdminUseCase(FakeRepo(rows))
        results = await uc(query="ГП")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_includes_inactive(self) -> None:
        rows = [
            _row(1, "Active Fic", "anime", active=True),
            _row(2, "Disabled Fic", "anime", active=False),
        ]
        uc = SearchFandomsAdminUseCase(FakeRepo(rows))
        results = await uc(query="Fic")
        names = {r.name for r in results}
        assert names == {"Active Fic", "Disabled Fic"}

    @pytest.mark.asyncio
    async def test_category_scope_limits_results(self) -> None:
        rows = [
            _row(1, "Naruto", "anime"),
            _row(2, "Naruto Movie", "films"),
        ]
        uc = SearchFandomsAdminUseCase(FakeRepo(rows))
        anime = await uc(query="Naruto", category="anime")
        assert [r.name for r in anime] == ["Naruto"]

    @pytest.mark.asyncio
    async def test_prefix_match_priority(self) -> None:
        rows = [
            _row(1, "Не Гарри", "books"),
            _row(2, "Гарри Поттер", "books"),
        ]
        uc = SearchFandomsAdminUseCase(FakeRepo(rows))
        results = await uc(query="Гарри")
        # Prefix-match идёт первым.
        assert results[0].name == "Гарри Поттер"


# ============================================================
# CategoryStatsAdminUseCase
# ============================================================


class TestCategoryStats:
    @pytest.mark.asyncio
    async def test_counts_only_active(self) -> None:
        rows = [
            _row(1, "A", "anime", active=True),
            _row(2, "B", "anime", active=False),
            _row(3, "C", "books", active=True),
        ]
        uc = CategoryStatsAdminUseCase(FakeRepo(rows))
        counts = await uc()
        assert counts == {"anime": 1, "books": 1}

    @pytest.mark.asyncio
    async def test_empty_when_nothing(self) -> None:
        uc = CategoryStatsAdminUseCase(FakeRepo([]))
        counts = await uc()
        assert counts == {}
