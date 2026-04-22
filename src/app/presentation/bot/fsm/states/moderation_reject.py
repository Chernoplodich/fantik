"""FSM отклонения работы модератором: причины → комментарий → подтверждение."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ModerationRejectStates(StatesGroup):
    picking_reasons = State()
    waiting_comment = State()
    confirming = State()
