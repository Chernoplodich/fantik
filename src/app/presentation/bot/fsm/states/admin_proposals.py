"""FSM админ-флоу заявок на фандом."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class FandomProposalReviewFlow(StatesGroup):
    waiting_reject_reason = State()
