"""FSM профиля: /delete_me confirm."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class DeleteMeFlow(StatesGroup):
    confirming = State()
