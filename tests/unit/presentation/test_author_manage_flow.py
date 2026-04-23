"""FSM-тесты управления уже созданным фиком: add_chapter / edit_chapter-title.

Валидация длины названия главы — той же природы, что в author_create:
пастинг большого текста в поле заголовка должен остановиться сразу.
"""

from __future__ import annotations

import pytest

from app.domain.fanfics.value_objects import CHAPTER_TITLE_MAX
from app.presentation.bot.fsm.states.add_chapter import AddChapterStates
from app.presentation.bot.fsm.states.edit_chapter import EditChapterStates
from app.presentation.bot.routers import author_manage as am

from ._flow_helpers import answer_texts, make_message, make_state, unwrap

add_chapter_title = unwrap(am.add_chapter_title)
chapter_edit_title = unwrap(am.chapter_edit_title)


@pytest.mark.asyncio
class TestAddChapterTitle:
    async def test_too_long_title_stays(self) -> None:
        state = make_state()
        await state.set_state(AddChapterStates.waiting_title)
        await state.update_data(fic_id=1)
        msg = make_message("X" * (CHAPTER_TITLE_MAX + 100))

        await add_chapter_title(msg, state)

        assert await state.get_state() == AddChapterStates.waiting_title.state
        data = await state.get_data()
        assert data.get("chapter_title") is None
        texts = await answer_texts(msg.answer)
        assert texts and "128" in texts[0]

    async def test_happy_path_advances_to_text(self) -> None:
        state = make_state()
        await state.set_state(AddChapterStates.waiting_title)
        await state.update_data(fic_id=1)
        msg = make_message("Глава 3")

        await add_chapter_title(msg, state)

        assert await state.get_state() == AddChapterStates.waiting_text.state
        data = await state.get_data()
        assert data["chapter_title"] == "Глава 3"

    async def test_empty_message_stays(self) -> None:
        state = make_state()
        await state.set_state(AddChapterStates.waiting_title)
        msg = make_message(None)

        await add_chapter_title(msg, state)

        assert await state.get_state() == AddChapterStates.waiting_title.state


@pytest.mark.asyncio
class TestChapterEditTitle:
    async def test_too_long_title_stays(self) -> None:
        state = make_state()
        await state.set_state(EditChapterStates.waiting_title)
        await state.update_data(chapter_id=5, fic_id=1)
        msg = make_message("Z" * (CHAPTER_TITLE_MAX + 10))

        await chapter_edit_title(msg, state)

        assert await state.get_state() == EditChapterStates.waiting_title.state

    async def test_happy_path_advances_to_text(self) -> None:
        state = make_state()
        await state.set_state(EditChapterStates.waiting_title)
        await state.update_data(chapter_id=5, fic_id=1)
        msg = make_message("Новое название")

        await chapter_edit_title(msg, state)

        assert await state.get_state() == EditChapterStates.waiting_text.state
