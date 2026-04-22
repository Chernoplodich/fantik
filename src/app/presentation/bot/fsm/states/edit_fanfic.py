"""FSM редактирования meta фика (title/summary/fandom/rating/tags/cover)."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class EditFanficStates(StatesGroup):
    selecting_field = State()
    waiting_title = State()
    waiting_summary = State()
    waiting_fandom = State()
    waiting_age_rating = State()
    waiting_tags = State()
    waiting_cover = State()
