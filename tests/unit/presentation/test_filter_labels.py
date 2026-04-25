"""Helper `_filter_labels`: человеческие лейблы фильтров вместо счётчиков «(N)»."""

from __future__ import annotations

from typing import Any

import pytest

from app.application.fanfics.ports import FandomRef
from app.domain.shared.types import FandomId
from app.presentation.bot.routers import browse as br


class _FakeReference:
    def __init__(self, fandom: FandomRef | None = None) -> None:
        self._fandom = fandom

    async def get_fandom(self, fandom_id: FandomId) -> FandomRef | None:
        if self._fandom is not None and self._fandom.id == fandom_id:
            return self._fandom
        return None

    async def list_fandoms_paginated(self, **_: Any) -> tuple[list[FandomRef], int]:
        return [], 0

    async def list_fandoms_by_category(self, **_: Any) -> tuple[list[FandomRef], int]:
        return [], 0

    async def search_fandoms(self, **_: Any) -> list[FandomRef]:
        return []

    async def list_age_ratings(self) -> list[Any]:
        return []

    async def get_age_rating(self, _: int) -> Any:
        return None


@pytest.mark.asyncio
class TestFilterLabels:
    async def test_empty_state_shows_friendly_defaults(self) -> None:
        s = {"fandoms": [], "ages": [], "tags": []}
        f, a, tg = await br._filter_labels(s, _FakeReference())  # type: ignore[arg-type]
        assert f == "🎭 Любой фандом"
        assert a == "🔞 Любой возраст"
        assert tg == "🏷 Без тегов"

    async def test_one_fandom_shows_its_name(self) -> None:
        ref = _FakeReference(
            FandomRef(id=FandomId(7), slug="hp", name="Гарри Поттер", category="books")
        )
        s = {"fandoms": [7], "ages": [], "tags": []}
        f, _, _ = await br._filter_labels(s, ref)  # type: ignore[arg-type]
        assert f == "🎭 Гарри Поттер"

    async def test_many_fandoms_show_count(self) -> None:
        ref = _FakeReference()
        s = {"fandoms": [1, 2, 3], "ages": [], "tags": []}
        f, _, _ = await br._filter_labels(s, ref)  # type: ignore[arg-type]
        assert f == "🎭 Выбрано: 3"

    async def test_one_age_shows_code(self) -> None:
        ref = _FakeReference()
        s = {"fandoms": [], "ages": ["R"], "tags": []}
        _, a, _ = await br._filter_labels(s, ref)  # type: ignore[arg-type]
        assert a == "🔞 R"

    async def test_one_tag_shows_name(self) -> None:
        ref = _FakeReference()
        s = {"fandoms": [], "ages": [], "tags": ["Ангст"]}
        _, _, tg = await br._filter_labels(s, ref)  # type: ignore[arg-type]
        assert tg == "🏷 Ангст"

    async def test_many_tags_show_count(self) -> None:
        ref = _FakeReference()
        s = {"fandoms": [], "ages": [], "tags": ["AU", "Ангст", "Романтика"]}
        _, _, tg = await br._filter_labels(s, ref)  # type: ignore[arg-type]
        assert tg == "🏷 Выбрано: 3"

    async def test_long_tag_is_truncated(self) -> None:
        ref = _FakeReference()
        s = {"fandoms": [], "ages": [], "tags": ["оченьдлинноеназваниетегапревышающеелимит"]}
        _, _, tg = await br._filter_labels(s, ref)  # type: ignore[arg-type]
        assert tg.startswith("🏷 ")
        assert tg.endswith("…")
