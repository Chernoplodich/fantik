"""FSM добавления главы к существующему фику."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddChapterStates(StatesGroup):
    waiting_title = State()
    waiting_text = State()
