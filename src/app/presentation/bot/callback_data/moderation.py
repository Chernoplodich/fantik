"""CallbackData для модерационной панели."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class ModCD(CallbackData, prefix="mod"):
    action: str  # pick / approve / reject / unlock / read_chapter / menu / release_stale
    case_id: int = 0
    chapter_id: int = 0


class ReasonCD(CallbackData, prefix="rsn"):
    action: str  # toggle / confirm
    case_id: int
    reason_id: int = 0
