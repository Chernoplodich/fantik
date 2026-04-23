"""FSM создания трекинг-кода: имя → описание."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class TrackingCodeFlow(StatesGroup):
    waiting_name = State()
    waiting_description = State()
