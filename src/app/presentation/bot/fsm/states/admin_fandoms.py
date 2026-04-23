"""FSM создания фандома: name → category → aliases (slug автогенерируется)."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class FandomCreateFlow(StatesGroup):
    waiting_name = State()
    waiting_category = State()
    waiting_aliases = State()
