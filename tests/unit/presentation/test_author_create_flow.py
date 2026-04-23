"""FSM-тесты мастера создания фика (`author_create.py`).

Проверяем ВАЛИДАЦИЮ НА ВХОДЕ в ключевых шагах: title / summary / chapter_title / tags.
Багу «при вставке главы с большим кол-вом символов — ошибка 1–128» — ровно
сценарий для `on_chapter_title` в этом файле.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.fanfics.value_objects import (
    CHAPTER_TITLE_MAX,
    MAX_TAGS_PER_FIC,
    SUMMARY_MAX,
    TITLE_MAX,
)
from app.presentation.bot.fsm.states.create_fanfic import CreateFanficStates
from app.presentation.bot.routers import author_create as ac

from ._flow_helpers import answer_texts, make_message, make_state, unwrap

on_title = unwrap(ac.on_title)
on_summary = unwrap(ac.on_summary)
on_chapter_title = unwrap(ac.on_chapter_title)
on_tags = unwrap(ac.on_tags)


@pytest.mark.asyncio
class TestOnTitle:
    async def test_happy_path_advances_state(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_title)
        msg = make_message("Новая работа")

        await on_title(msg, state)

        assert await state.get_state() == CreateFanficStates.waiting_summary.state
        data = await state.get_data()
        assert data["title"] == "Новая работа"

    async def test_empty_message_stays_and_shows_expect_text(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_title)
        msg = make_message(None)

        await on_title(msg, state)

        assert await state.get_state() == CreateFanficStates.waiting_title.state
        texts = await answer_texts(msg.answer)
        assert texts and "текст" in texts[0].lower()

    async def test_too_long_title_stays_and_shows_error(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_title)
        msg = make_message("x" * (TITLE_MAX + 10))

        await on_title(msg, state)

        # Остались в том же состоянии (НЕ ушли в waiting_summary)
        assert await state.get_state() == CreateFanficStates.waiting_title.state
        data = await state.get_data()
        assert data.get("title") is None
        texts = await answer_texts(msg.answer)
        assert texts and "2" in texts[0] and "128" in texts[0]

    async def test_too_short_title_stays(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_title)
        msg = make_message("x")  # < TITLE_MIN (2)

        await on_title(msg, state)

        assert await state.get_state() == CreateFanficStates.waiting_title.state


@pytest.mark.asyncio
class TestOnSummary:
    async def test_too_long_summary_stays(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_summary)
        await state.update_data(title="t")
        msg = make_message("y" * (SUMMARY_MAX + 1))

        reference = AsyncMock()
        await on_summary(msg, state, reference)

        assert await state.get_state() == CreateFanficStates.waiting_summary.state
        data = await state.get_data()
        assert data.get("summary") is None

    async def test_empty_summary_stays(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_summary)
        msg = make_message(None)

        reference = AsyncMock()
        await on_summary(msg, state, reference)

        assert await state.get_state() == CreateFanficStates.waiting_summary.state


@pytest.mark.asyncio
class TestOnChapterTitle:
    """THE BUG: пользователь пастит главу в поле «название главы» — ошибка
    должна показаться сразу, а не на финише `add_chapter_uc`."""

    async def test_too_long_chapter_title_stays_and_shows_1_128_error(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_chapter_title)
        # Эмулируем паст большого куска текста в поле названия главы
        msg = make_message("A" * (CHAPTER_TITLE_MAX + 500))

        await on_chapter_title(msg, state)

        # ВАЖНО: остались в том же состоянии — не продвинулись к тексту
        assert await state.get_state() == CreateFanficStates.waiting_chapter_title.state
        data = await state.get_data()
        assert data.get("chapter_title") is None
        texts = await answer_texts(msg.answer)
        assert texts and "1" in texts[0] and "128" in texts[0]

    async def test_happy_path_advances_to_text(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_chapter_title)
        msg = make_message("Глава 1. Пролог")

        await on_chapter_title(msg, state)

        assert await state.get_state() == CreateFanficStates.waiting_chapter_text.state
        data = await state.get_data()
        assert data["chapter_title"] == "Глава 1. Пролог"


@pytest.mark.asyncio
class TestOnTags:
    async def test_happy_path_advances_to_cover(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_tags)
        msg = make_message("AU, Ангст, Драма")

        await on_tags(msg, state)

        assert await state.get_state() == CreateFanficStates.waiting_cover.state
        data = await state.get_data()
        assert data["tag_raws"] == ["AU", "Ангст", "Драма"]

    async def test_dash_means_no_tags(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_tags)
        msg = make_message("-")

        await on_tags(msg, state)

        assert await state.get_state() == CreateFanficStates.waiting_cover.state
        data = await state.get_data()
        assert data["tag_raws"] == []

    async def test_too_many_tags_stays(self) -> None:
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_tags)
        tags = ",".join(f"tag{i}" for i in range(MAX_TAGS_PER_FIC + 1))
        msg = make_message(tags)

        await on_tags(msg, state)

        assert await state.get_state() == CreateFanficStates.waiting_tags.state
        data = await state.get_data()
        assert data.get("tag_raws") is None

    async def test_invalid_tag_name_stays(self) -> None:
        """Одиночный символ — меньше TAG_NAME_MIN (2)."""
        state = make_state()
        await state.set_state(CreateFanficStates.waiting_tags)
        msg = make_message("ok, a, good")  # 'a' — один символ

        await on_tags(msg, state)

        assert await state.get_state() == CreateFanficStates.waiting_tags.state
        data = await state.get_data()
        assert data.get("tag_raws") is None
