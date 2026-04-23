"""FSM создания рассылки: шаблон → клавиатура → сегмент → расписание → подтверждение."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class BroadcastFlow(StatesGroup):
    waiting_source = State()
    waiting_keyboard_choice = State()
    waiting_keyboard_input = State()
    waiting_segment = State()
    waiting_segment_param = State()
    waiting_schedule_choice = State()
    waiting_schedule_datetime = State()
    confirm = State()
