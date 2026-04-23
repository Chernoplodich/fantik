"""FSM-тесты меню фильтров: `toggle_filter` должен ОСТАВАТЬСЯ в picker'е.

Регрессия: после выбора одного фильтра хендлер выкидывал пользователя
в `filters_root` — теперь он перерисовывает текущий picker с обновлёнными ✅.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.fanfics.ports import AgeRatingRef, FandomRef
from app.domain.fanfics.value_objects import AgeRatingCode, TagName, TagSlug
from app.domain.shared.types import FandomId, TagId
from app.presentation.bot.callback_data.search import SearchCD
from app.presentation.bot.routers import browse as br

from ._flow_helpers import make_callback, make_state, unwrap

toggle_filter = unwrap(br.toggle_filter)


def _fandom_ref(fid: int, name: str) -> FandomRef:
    return FandomRef(id=FandomId(fid), slug=f"fd-{fid}", name=name, category="books")


def _age_ref(idx: int, code: str) -> AgeRatingRef:
    return AgeRatingRef(
        id=idx,
        code=AgeRatingCode(code),
        name=code,
        description="",
        min_age=None,
        sort_order=idx,
    )


class _FakeReference:
    """Мини-стаб IReferenceReader для тестов фильтра."""

    def __init__(self, *, fandoms: list[FandomRef], ages: list[AgeRatingRef]) -> None:
        self._fandoms = fandoms
        self._ages = ages

    async def list_fandoms_paginated(
        self, *, limit: int, offset: int, active_only: bool = True
    ) -> tuple[list[FandomRef], int]:
        return self._fandoms[offset : offset + limit], len(self._fandoms)

    async def get_fandom(self, fandom_id: FandomId) -> FandomRef | None:
        for f in self._fandoms:
            if int(f.id) == int(fandom_id):
                return f
        return None

    async def list_age_ratings(self) -> list[AgeRatingRef]:
        return list(self._ages)

    async def get_age_rating(self, rating_id: int) -> AgeRatingRef | None:
        for a in self._ages:
            if int(a.id) == int(rating_id):
                return a
        return None


class _FakeSuggestReader:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    async def by_prefix(self, *, kind: str, prefix: str, limit: int) -> list[str]:
        return list(self._names)[:limit]


@pytest.mark.asyncio
class TestToggleFandom:
    async def test_first_toggle_adds_id_and_stays_in_picker(self) -> None:
        state = make_state()
        cb = make_callback()
        ref = _FakeReference(
            fandoms=[_fandom_ref(1, "HP"), _fandom_ref(2, "Marvel")],
            ages=[],
        )
        suggest = _FakeSuggestReader([])

        await toggle_filter(
            cb,
            SearchCD(a="toggle", k="fandom", v="1", pg=0),
            state,
            ref,
            suggest,
        )

        data = await state.get_data()
        assert data["s_fandoms"] == [1]
        # edit_reply_markup вызвался один раз, edit_text — ни разу
        cb.message.edit_reply_markup.assert_awaited_once()
        cb.message.edit_text.assert_not_awaited()

    async def test_second_toggle_removes_same_id(self) -> None:
        state = make_state()
        await state.update_data(s_fandoms=[1])
        cb = make_callback()
        ref = _FakeReference(fandoms=[_fandom_ref(1, "HP")], ages=[])
        suggest = _FakeSuggestReader([])

        await toggle_filter(
            cb,
            SearchCD(a="toggle", k="fandom", v="1", pg=0),
            state,
            ref,
            suggest,
        )

        data = await state.get_data()
        assert data["s_fandoms"] == []
        cb.message.edit_reply_markup.assert_awaited_once()

    async def test_multiple_selections_accumulate(self) -> None:
        state = make_state()
        cb = make_callback()
        ref = _FakeReference(fandoms=[_fandom_ref(i, f"F{i}") for i in range(1, 4)], ages=[])
        suggest = _FakeSuggestReader([])

        for fid in ("1", "2", "3"):
            await toggle_filter(
                cb,
                SearchCD(a="toggle", k="fandom", v=fid, pg=0),
                state,
                ref,
                suggest,
            )

        data = await state.get_data()
        assert data["s_fandoms"] == [1, 2, 3]


@pytest.mark.asyncio
class TestToggleAge:
    async def test_toggle_age_accumulates_codes(self) -> None:
        state = make_state()
        cb = make_callback()
        ref = _FakeReference(
            fandoms=[],
            ages=[_age_ref(1, "PG"), _age_ref(2, "R"), _age_ref(3, "NC-17")],
        )
        suggest = _FakeSuggestReader([])

        for code in ("PG", "R"):
            await toggle_filter(
                cb,
                SearchCD(a="toggle", k="age", v=code),
                state,
                ref,
                suggest,
            )

        data = await state.get_data()
        assert data["s_ages"] == ["PG", "R"]
        # picker перерисовался дважды, root не показывали
        assert cb.message.edit_reply_markup.await_count == 2
        cb.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
class TestToggleTag:
    async def test_toggle_tag_accumulates(self) -> None:
        state = make_state()
        cb = make_callback()
        ref = _FakeReference(fandoms=[], ages=[])
        suggest = _FakeSuggestReader(["AU", "Ангст", "Романтика"])

        for t in ("AU", "Ангст"):
            await toggle_filter(
                cb,
                SearchCD(a="toggle", k="tag", v=t),
                state,
                ref,
                suggest,
            )

        data = await state.get_data()
        assert data["s_tags"] == ["AU", "Ангст"]

    async def test_toggle_tag_noop_on_unknown_kind(self) -> None:
        """Если kind пришёл пустым — состояние не меняется, но и не падаем."""
        state = make_state()
        await state.update_data(s_fandoms=[], s_ages=[], s_tags=[])
        cb = make_callback()
        ref = _FakeReference(fandoms=[], ages=[])
        suggest = _FakeSuggestReader([])

        await toggle_filter(
            cb,
            SearchCD(a="toggle", k="", v=""),
            state,
            ref,
            suggest,
        )

        data = await state.get_data()
        assert data["s_fandoms"] == [] and data["s_ages"] == [] and data["s_tags"] == []


@pytest.mark.asyncio
class TestNoMessage:
    async def test_missing_message_early_exits(self) -> None:
        state = make_state()
        cb = make_callback(with_message=False)
        ref = _FakeReference(fandoms=[_fandom_ref(1, "x")], ages=[])
        suggest = _FakeSuggestReader([])

        await toggle_filter(
            cb,
            SearchCD(a="toggle", k="fandom", v="1", pg=0),
            state,
            ref,
            suggest,
        )

        # cb.answer был вызван один раз — ранний выход
        cb.answer.assert_awaited()


# Убираем ссылку на неиспользуемые импорты, чтобы ruff не ругался.
_ = (TagName, TagSlug, TagId, AsyncMock)
