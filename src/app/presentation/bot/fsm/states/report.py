"""FSM жалобы: выбор причины → коммент → подтверждение."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ReportFlow(StatesGroup):
    waiting_reason = State()
    waiting_comment = State()
