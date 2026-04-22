"""FSM для создания нового фика (автор)."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CreateFanficStates(StatesGroup):
    waiting_title = State()
    waiting_summary = State()
    waiting_fandom = State()
    waiting_age_rating = State()
    waiting_tags = State()
    waiting_cover = State()
    chapter_or_submit = State()
    waiting_chapter_title = State()
    waiting_chapter_text = State()
