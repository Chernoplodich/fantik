"""FSM редактирования существующей главы."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class EditChapterStates(StatesGroup):
    waiting_title = State()
    waiting_text = State()
